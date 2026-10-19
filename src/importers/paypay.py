"""Text extraction assistance, not a verified PayPay report-layout parser."""
import io
import re
from pypdf import PdfReader
from src.importers.trades import preview_rows

LABELS={
    '取引日':'executed_at','約定日':'executed_at','Date':'executed_at','銘柄名':'name','Name':'name',
    '銘柄コード':'code','Code':'code','売買区分':'kind','Side':'kind','数量':'quantity','Quantity':'quantity',
    '単価':'price','Price':'price','手数料':'fee','Fee':'fee','税額':'tax','Tax':'tax','口座区分':'account','Account':'account',
    '商品種別':'asset_type','Asset':'asset_type','通貨':'currency','Currency':'currency','為替':'fx','FX':'fx',
    '取引ID':'external_id','TradeID':'external_id',
}


def extract_pdf(content):
    if not content or len(content)>5*1024*1024 or not content.startswith(b'%PDF-'):
        raise ValueError('PDF形式・サイズ（5MB以下）を確認してください')
    try:
        reader=PdfReader(io.BytesIO(content),strict=True)
        if reader.is_encrypted:
            raise ValueError('暗号化PDFは解析対象外です。手入力を利用してください')
        if len(reader.pages)>30:
            raise ValueError('PDFは30ページ以下に分割してください')
        text='\n'.join(page.extract_text() or '' for page in reader.pages)
        if len(text)>200000:
            raise ValueError('PDFの抽出文字数が上限を超えました')
    except ValueError:
        raise
    except Exception:
        raise ValueError('PDFを読み取れません。公式書面を確認して手入力してください') from None
    return text


def candidates(text):
    # Only literal, whole-line labels. Conflicting or repeated fields are not guessed.
    draft={}
    conflicts=set()
    for line in text.splitlines():
        match=re.fullmatch(r'\s*([^:：]+)[:：]\s*(.*?)\s*',line)
        if not match: continue
        key=LABELS.get(match.group(1).strip())
        if key:
            value=match.group(2).strip()
            if key in draft:
                conflicts.add(key)
            else:
                draft[key]=value
    for key in conflicts:
        draft[key]=''
    return draft


class PayPayImporter:
    def preview(self,rows,date_format='%Y-%m-%d'):
        return preview_rows(rows,'PayPay証券',date_format)

    def import_bytes(self,db,content,**kwargs):
        # No blind PDF/CSV auto-registration.
        raise ValueError('PayPay証券固有CSVは未対応: PDF抽出後の確認プレビューまたは手入力を使用してください')
