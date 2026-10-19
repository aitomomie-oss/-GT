"""Bounded official-source downloads; no credentials, redirects, or inferred negatives."""
import csv
import io
import re
import zipfile
import unicodedata
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin
from urllib.request import Request, build_opener
from src.market_data.jquants import NoRedirect
from src.market_data.base import MarketDataError

HOSTS=('jpx.co.jp','fsa.go.jp','toushin.or.jp')
MAX_BYTES=20*1024*1024


def validate_url(url):
    p=urlparse(url)
    if p.scheme!='https' or p.port not in (None,443) or p.username or p.password or p.query or p.fragment or not p.hostname or not any(p.hostname==h or p.hostname.endswith('.'+h) for h in HOSTS):
        raise MarketDataError('invalid_response')
    return url


def download(url):
    validate_url(url)
    try:
        with build_opener(NoRedirect()).open(Request(url,headers={'User-Agent':'MY-AI-ASSET/1.0'}),timeout=20) as response:
            data=response.read(MAX_BYTES+1)
            if len(data)>MAX_BYTES: raise MarketDataError('invalid_response')
            return data
    except MarketDataError: raise
    except Exception: raise MarketDataError('network') from None


def norm(text):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(text or ''))).casefold()


class Document(HTMLParser):
    def __init__(self,text):
        super().__init__();self.rows=[];self.links=[];self.text=[];self.row=None;self.cell=None
        self.feed(text)
    def handle_starttag(self,tag,attrs):
        if tag=='tr': self.row=[]
        if tag in ('td','th') and self.row is not None: self.cell=[]
        if tag=='a':
            href=dict(attrs).get('href')
            if href: self.links.append(href)
    def handle_data(self,data):
        self.text.append(data)
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(self.cell).strip());self.cell=None
        if tag=='tr' and self.row is not None:
            self.rows.append(self.row);self.row=None


def decode(data):
    for encoding in (('utf-16',) if data.startswith((b'\xff\xfe',b'\xfe\xff')) else ('utf-8-sig','cp932')):
        try: return data.decode(encoding)
        except UnicodeError: pass
    raise MarketDataError('invalid_response')


def xlsx_rows(data):
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist())>MAX_BYTES*3 or len(z.infolist())>500: raise ValueError()
            strings=[]
            if 'xl/sharedStrings.xml' in z.namelist():
                root=ET.fromstring(z.read('xl/sharedStrings.xml'))
                strings=[''.join(n.itertext()) for n in root.findall('s:si',ns)]
            rows=[]
            for name in sorted(n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',n)):
                root=ET.fromstring(z.read(name))
                for r in root.findall('.//s:sheetData/s:row',ns):
                    row=[]
                    for c in r.findall('s:c',ns):
                        ref=c.get('r','');letters=re.sub('[^A-Z]','',ref)
                        column=0
                        for letter in letters: column=column*26+ord(letter)-64
                        if not 1<=column<=100: raise ValueError()
                        while len(row)<column: row.append('')
                        if c.find('s:f',ns) is not None: continue  # Do not trust formula caches.
                        value=c.findtext('s:v',default='',namespaces=ns)
                        if c.get('t')=='s': value=strings[int(value)]
                        elif c.get('t')=='inlineStr': value=''.join(c.find('s:is',ns).itertext())
                        row[column-1]=value
                    rows.append(row)
                    if len(rows)>30000: raise ValueError()
            return rows
    except Exception: raise MarketDataError('invalid_response') from None


def read_document(data,url):
    if data.startswith(b'PK'): return xlsx_rows(data),[],''
    if data.startswith(b'%PDF'):
        from pypdf import PdfReader
        try:
            reader=PdfReader(io.BytesIO(data))
            if reader.is_encrypted or len(reader.pages)>200: raise ValueError()
            text='\n'.join(p.extract_text(extraction_mode='layout') or '' for p in reader.pages)
            # Only layout-separated rows with recognized headers may become entries.
            rows=[re.split(r'\s{2,}|\t',line.strip()) for line in text.splitlines() if line.strip()]
            return rows,[],text
        except Exception: raise MarketDataError('invalid_response') from None
    text=decode(data)
    if '<html' in text.lower() or '<table' in text.lower():
        document=Document(text)
        return document.rows,document.links,' '.join(document.text)
    return list(csv.reader(io.StringIO(text))),[],text


def find_date(text):
    from datetime import date
    from src.utils.decimal_utils import today_jst
    # Require explicit provenance language, not arbitrary dates appearing in a product list.
    matches=re.findall(r'(20\d{2})[年/.-]\s*(\d{1,2})[月/.-]\s*(\d{1,2})日?\s*(?:現在|時点|更新)',text)
    dates=[]
    for y,m,d in matches:
        try:
            day=date(int(y),int(m),int(d))
            if day<=today_jst(): dates.append(day)
        except ValueError: continue
    return str(max(dates)) if dates else None


ALIASES={
 'code':('コード','銘柄コード','証券コード','code'),
 'name':('銘柄名','銘柄名称','ファンド名称','ファンド名','商品名','対象商品名'),
 'isin':('isin','isinコード','isinコード(12桁)'),
 'state':('状況','状態','売買停止状況','売買停止・再開','区分'),
 'stop':('売買停止日時','停止日時','売買停止時刻','停止時刻'),
 'resume':('売買再開日時','再開日時','売買再開時刻','再開時刻'),
}


def parse_records(rows,kind):
    header=None;out=[]
    for row in rows:
        normalized=[norm(c) for c in row]
        indexes={key:next((i for i,v in enumerate(normalized) if v in {norm(a) for a in labels}),None) for key,labels in ALIASES.items()}
        if indexes['name'] is not None and (kind=='nisa' or indexes['code'] is not None): header=indexes;continue
        if not header or not row or not any(str(c).strip() for c in row): continue
        def cell(key):
            i=header.get(key)
            return str(row[i]).strip() if i is not None and i<len(row) else ''
        code=unicodedata.normalize('NFKC',cell('code')).upper().strip()
        if code.endswith('.0'): code=code[:-2]
        name=cell('name');isin=cell('isin').upper()
        if not name: continue
        if code and not re.fullmatch('[0-9A-Z]{4,5}',code):
            # Footnotes are not securities; nonstandard identities are not matched by code.
            code=''
        if isin and not re.fullmatch('JP[0-9A-Z]{10}',isin): isin=''
        if kind=='halts':
            if not code: raise MarketDataError('invalid_response')
            state=norm(cell('state'))
            resume=cell('resume')
            if state in ('再開済','売買再開済','解除済'): status='resumed'
            elif state in ('停止','売買停止','停止中','売買停止中') or (cell('stop') and not resume): status='halted'
            else: status='review'  # An unrecognized row must block purchase, not clear a stop.
            out.append(dict(code=code,name=name,status=status,raw_state=cell('state'),resume=resume))
        else:
            out.append(dict(code=code,isin=isin,name=name))
    if not header or not out: raise MarketDataError('invalid_response')
    return out


def fetch_list(url,kind,fetch=download):
    validate_url(url)
    rows,links,text=read_document(fetch(url),url)
    expected={'nisa_tsumitate':'つみたて投資枠','nisa_growth':'成長投資枠'}.get(kind)
    context=text or ' '.join(' '.join(r) for r in rows)
    if expected and (expected not in context or any(label in context for label in ('対象外商品一覧','除外商品一覧','対象外銘柄一覧'))):
        raise MarketDataError('invalid_response')
    parse_kind='halts' if kind=='halts' else 'nisa'
    as_of=find_date(text or ' '.join(' '.join(r) for r in rows))
    try: records=parse_records(rows,parse_kind)
    except MarketDataError:
        # Official landing pages may link to a revised product file; follow at most 5 files.
        files=[]
        for href in links:
            child=urljoin(url,href)
            try: validate_url(child)
            except MarketDataError: continue
            if re.search(r'\.(csv|xlsx|pdf)$',urlparse(child).path,re.I) and child not in files: files.append(child)
        successful=[]
        for child in files[:5]:
            try:
                child_rows,_,child_text=read_document(fetch(child),child)
                child_context=child_text or ' '.join(' '.join(r) for r in child_rows)
                if expected and any(label in child_context for label in ('対象外商品一覧','除外商品一覧','対象外銘柄一覧')): continue
                other='成長投資枠' if expected=='つみたて投資枠' else 'つみたて投資枠'
                if expected and other in child_context and expected not in child_context: continue
                child_records=parse_records(child_rows,parse_kind)
                child_date=find_date(child_text or ' '.join(' '.join(r) for r in child_rows)) or as_of
                if child_date: successful.append((child_records,child_date,child))
            except MarketDataError: continue
        # Multiple documents require an explicit source choice, avoiding mixed eligibility categories.
        if len(successful)!=1: raise MarketDataError('invalid_response')
        records,as_of,url=successful[0]
    if not as_of: raise MarketDataError('invalid_response')
    return dict(records=records,as_of=as_of,source=url)
