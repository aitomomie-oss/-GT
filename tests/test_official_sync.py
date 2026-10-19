import io
import json
import zipfile
import pytest
from src.db.session import connect
from src.market_data.official_lists import fetch_list,validate_url,parse_records,xlsx_rows
from src.market_data.base import MarketDataError
from src.services import official_sync as s
from src.services.discovery_budget import purchase
from src.utils.decimal_utils import today_jst

@pytest.fixture
def db(tmp_path):
    conn=connect(tmp_path/'sync.db');yield conn;conn.close()


def test_csv_identity_and_source_date():
    content='2026年10月19日現在\n銘柄コード,銘柄名\n1234,架空企業\n'.encode()
    data=fetch_list('https://www.jpx.co.jp/list.csv','nisa',fetch=lambda url:content)
    assert data['as_of']=='2026-10-19'
    assert data['records']==[dict(code='1234',name='架空企業',isin='')]


def test_official_html_link_to_revised_csv():
    page=b'<html><p>2026/10/19'+ '現在'.encode()+b'</p><a href="/new.csv">CSV</a></html>'
    values={'https://www.fsa.go.jp/products/':page,'https://www.fsa.go.jp/new.csv':'ファンド名\n架空投信\n'.encode()}
    result=fetch_list('https://www.fsa.go.jp/products/','nisa',fetch=values.__getitem__)
    assert result['source']=='https://www.fsa.go.jp/new.csv'
    assert result['records'][0]['name']=='架空投信'

@pytest.mark.parametrize('url',['https://example.com/a.csv','https://jpx.co.jp.evil.example/a','http://www.jpx.co.jp/a','https://www.jpx.co.jp:444/a','https://user:pass@www.jpx.co.jp/a','https://127.0.0.1/a','https://www.jpx.co.jp/a?token=abc'])
def test_restrict_official_network_targets(url):
    with pytest.raises(MarketDataError): validate_url(url)


def test_missing_date_and_unknown_headers_rejected():
    for value in ('銘柄名\n架空投信\n','2026/10/19現在\n価格,数量\n100,1\n'):
        with pytest.raises(MarketDataError): fetch_list('https://www.fsa.go.jp/a.csv','nisa',lambda url:value.encode())


def test_halt_and_resume_schedule_never_cleared():
    rows=[['コード','銘柄名','状態','再開日時'],['1234','架空','停止中','2099-01-01 10:00']]
    assert parse_records(rows,'halts')[0]['status']=='halted'
    rows[1][2]='売買再開'
    assert parse_records(rows,'halts')[0]['status']=='review'


def test_sync_match_and_failure_retains_stop(db):
    s.configure(db,'halts','https://www.jpx.co.jp/a.csv')
    def source(*args): return dict(records=[dict(code='12340',name='架空',status='halted')],as_of=str(today_jst()),source=args[0])
    assert s.sync(db,'halts',fetcher=source)=='updated'
    assert s.lookup(db,'1234','架空')['halt']=='取引停止'
    assert s.sync(db,'halts',fetcher=lambda *a:1)=='cached'
    def error(*args): raise MarketDataError('network')
    assert s.sync(db,'halts',force=True,fetcher=error)=='network'
    assert s.lookup(db,'1234','架空')['halt']=='過去に停止・再確認が必要'
    assert s.lookup(db,'9999','別企業')['halt']=='未確認'


def test_nisa_positive_only_and_exact_identity(db):
    for kind in ('nisa_tsumitate','nisa_growth'):
        s.configure(db,kind,'https://www.fsa.go.jp/a.csv')
        s.sync(db,kind,fetcher=lambda *a:dict(records=[dict(code='',name='架空 投信',isin='')],as_of=str(today_jst()),source=a[0]))
    assert s.lookup(db,'MY-FUND','架空投信')['nisa']=='両方'
    assert s.lookup(db,'MY-FUND','架空投信別クラス')['nisa']=='不明'
    with db: db.execute("UPDATE official_sources SET status='error' WHERE kind='nisa_growth'")
    assert s.lookup(db,'MY-FUND','架空投信')['nisa']=='つみたて'


def test_duplicate_names_and_code_conflicts_are_unknown(db):
    s.configure(db,'nisa_growth','https://www.jpx.co.jp/a.csv')
    records=[dict(code='1234',name='同名'),dict(code='9999',name='同名')]
    s.sync(db,'nisa_growth',fetcher=lambda *a:dict(records=records,as_of=str(today_jst()),source=a[0]))
    assert s.lookup(db,'1111','同名')['nisa']=='不明'
    assert s.lookup(db,'12340','同名')['nisa']=='成長'
    assert s.lookup(db,'','同名')['nisa']=='不明'


def test_xlsx_bounded_reader_and_formulas():
    xml='''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="inlineStr"><is><t>銘柄名</t></is></c><c r="C1"><f>1+1</f><v>2</v></c></row><row><c r="A2" t="inlineStr"><is><t>架空投信</t></is></c></row></sheetData></worksheet>'''
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive: archive.writestr('xl/worksheets/sheet1.xml',xml)
    rows=xlsx_rows(buffer.getvalue())
    assert rows[0]==['銘柄名','','']
    assert parse_records(rows,'nisa')[0]['name']=='架空投信'


def test_stop_blocks_purchase(db):
    s.configure(db,'halts','https://www.jpx.co.jp/a.csv')
    s.sync(db,'halts',fetcher=lambda *a:dict(records=[dict(code='1234',name='架空',status='halted')],as_of=str(today_jst()),source=a[0]))
    result=dict(code='12340',name='架空',price={},reasons=[])
    assert any('取引停止' in r for r in purchase(db,result)['reasons'])
    assert db.execute('SELECT COUNT(*) FROM positions').fetchone()[0]==0


def test_migration_backup(tmp_path):
    path=tmp_path/'existing.db';db=connect(path)
    with db:
        db.execute('DROP TABLE official_sources')
        db.execute("INSERT INTO settings VALUES('keep','original')")
    db.close();db=connect(path)
    assert path.with_name('existing.db.pre-official-sync.bak').exists()
    assert db.execute("SELECT value FROM settings WHERE key='keep'").fetchone()[0]=='original'
    db.close()

def test_wrong_nisa_category_and_negative_list_rejected():
    for title in ('別の市場の銘柄一覧','成長投資枠 対象外商品一覧'):
        body=(title+'\n2026/10/19現在\n銘柄名\n架空投信\n').encode()
        with pytest.raises(MarketDataError): fetch_list('https://www.jpx.co.jp/list.csv','nisa_growth',lambda u:body)


def test_recognized_nisa_category():
    body='成長投資枠 対象商品一覧\n2026/10/19現在\n銘柄コード,銘柄名\n1234,架空\n'.encode()
    assert fetch_list('https://www.jpx.co.jp/list.csv','nisa_growth',lambda u:body)['records'][0]['code']=='1234'


def test_unreadable_pdf_does_not_create_eligibility():
    from pypdf import PdfWriter
    stream=io.BytesIO();writer=PdfWriter();writer.add_blank_page(width=100,height=100);writer.write(stream)
    with pytest.raises(MarketDataError): fetch_list('https://www.fsa.go.jp/list.pdf','nisa_tsumitate',lambda u:stream.getvalue())


def test_official_ui_with_configured_cached_source(tmp_path,monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    path=tmp_path/'ui.db';db=connect(path)
    s.configure(db,'nisa_tsumitate','https://www.fsa.go.jp/a.csv')
    s.sync(db,'nisa_tsumitate',fetcher=lambda *a:dict(records=[dict(code='',name='架空投信')],as_of=str(today_jst()),source=a[0]))
    db.close();monkeypatch.setenv('MY_AI_ASSET_DB',str(path))
    root=Path(__file__).resolve().parents[1]
    app=AppTest.from_file(str(root/'app.py')).run(timeout=30)
    app.switch_page('pages/7_AI銘柄探索.py').run(timeout=30)
    assert not app.exception
    assert any(e.key=='official_kind' for e in app.selectbox)
    assert any(e.key=='official_refresh' for e in app.button)
