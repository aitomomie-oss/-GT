import csv
import io
from decimal import Decimal
from pathlib import Path
import pytest
from src import api as c
from src.importers.trades import preview_rows, TRADE_FIELDS
from src.importers.sbi import SBIImporter
from src.importers.paypay import extract_pdf, candidates


@pytest.fixture
def db(tmp_path):
    conn=c.connect(tmp_path/'phase2.db')
    yield conn
    conn.close()


def trade(**values):
    r=dict(executed_at='2026-10-01',name='架空・取引株A',code='FAKE001',kind='buy',quantity='10',price='100',fee='10',tax='0',account='NISA',asset_type='日本株',currency='JPY',price_unit='1',fx='1',fx_as_of='',external_id='sample-1')
    r.update(values)
    return r


def register(db,rows,token='file1',complete=True,broker='SBI証券',**kwargs):
    return c.register_batch(db,token.encode(),'架空テスト',preview_rows(rows,broker),complete_history=complete,confirmed=True,**kwargs)


def test_duplicate_files_and_transactions_across_files(db):
    a=register(db,[trade()])
    assert a['added']==1
    assert register(db,[trade()])['status']=='already_imported'
    assert register(db,[trade()],token='different filename and bytes')['added']==0
    assert len(c.transaction_rows(db))==1
    assert len(c.ledger_positions(db))==1
    assert c.ledger_positions(db)[0]['cost_jpy']==1010


def test_natural_identity_without_trade_id_is_stable(db):
    a=trade(external_id='')
    register(db,[a])
    a['quantity']='10.000'
    assert register(db,[a],token='other')['duplicates']==1
    a['fee']='12'
    with pytest.raises(ValueError):
        register(db,[a],token='fee-conflict')
    assert len(c.transaction_rows(db))==1


def test_preview_errors_and_mid_import_failures_are_atomic(db):
    rows=[trade(),trade(external_id='sample2',quantity='-1')]
    with pytest.raises(ValueError): register(db,rows)
    assert c.transaction_rows(db)==[]
    assert c.batch_history(db)[0]['failure_count']==1
    assert db.execute('SELECT COUNT(*) FROM instruments').fetchone()[0]==0
    rows=[trade(),trade(external_id='oversell',kind='sell',executed_at='2026-10-02',quantity='100')]
    with pytest.raises(ValueError,match='売却数量'): register(db,rows,token='bad sequence')
    assert c.transaction_rows(db)==[]
    assert db.execute('SELECT COUNT(*) FROM instruments').fetchone()[0]==0


def test_moving_average_sale_and_current_valuation(db):
    rows=[trade(),trade(external_id='buy2',executed_at='2026-10-02',price='200'),trade(external_id='sell',kind='sell',executed_at='2026-10-03',quantity='5',price='300',fee='5')]
    register(db,rows)
    item=c.ledger_positions(db)[0]
    assert item['quantity']==15
    assert item['cost_jpy']==2265
    assert item['realized_jpy']==740
    assert item['value_jpy'] is None  # Transaction price is never passed off as a current quote.
    c.update_valuation(db,item['id'],'250','1','2026-10-10')
    item=c.holdings(db)[0]
    assert item['value_jpy']==3750
    assert item['profit_jpy']==1485


def test_usd_cost_fx_missing_and_fund_unit(db):
    register(db,[trade(asset_type='米国株',currency='USD',quantity='2',price='100',fee='1',fx='150')])
    item=c.holdings(db)[0]
    assert item['cost_jpy']==30150
    c.update_valuation(db,item['id'],'110','140','2026-10-10')
    assert c.holdings(db)[0]['profit_jpy']==650
    other=trade(name='架空・投信',code='FAKEFUND',asset_type='投資信託',quantity='10000',price='20000',price_unit='10000',fee='0',external_id='fund1')
    register(db,[other],token='fund')
    fund=next(r for r in c.holdings(db) if r['asset_type']=='投資信託')
    assert fund['cost_jpy']==20000
    missing=trade(name='架空・為替不明',code='FAKEX',asset_type='米国株',currency='USD',fx='',external_id='missing')
    register(db,[missing],token='missing')
    assert next(r for r in c.holdings(db) if r['code']=='FAKEX')['cost_jpy'] is None


def test_incomplete_history_does_not_invent_initial_balance(db):
    register(db,[trade(kind='sell')],complete=False)
    item=c.holdings(db)[0]
    assert item['quantity'] is None and item['cost_jpy'] is None


def test_cancel_restore_and_dependency_protection(db):
    buy=register(db,[trade()])
    sell=register(db,[trade(executed_at='2026-10-02',kind='sell',quantity='5',external_id='sell')],token='sell')
    before=c.ledger_positions(db)[0]
    with pytest.raises(ValueError,match='売却数量'): c.change_batch_status(db,buy['batch_id'])
    assert c.batch_history(db)[1]['status']=='active'
    c.change_batch_status(db,sell['batch_id'])
    c.change_batch_status(db,buy['batch_id'])
    assert c.holdings(db)==[]
    with pytest.raises(ValueError,match='復元'): register(db,[trade()])
    c.change_batch_status(db,buy['batch_id'],restore=True)
    c.change_batch_status(db,sell['batch_id'],restore=True)
    assert c.ledger_positions(db)[0]['quantity']==before['quantity']
    assert c.ledger_positions(db)[0]['cost_jpy']==before['cost_jpy']
    assert db.execute('SELECT COUNT(*) FROM batch_events').fetchone()[0]==4


def test_correction_is_audited_and_old_rows_cannot_reappear(db):
    register(db,[trade()])
    item=c.transaction_rows(db)[0]
    updated=trade(price='200',executed_at=item['executed_at'])
    c.revise_transaction(db,item['id'],updated,confirmed=True)
    assert c.ledger_positions(db)[0]['cost_jpy']==2010
    assert db.execute('SELECT COUNT(*) FROM transaction_revisions').fetchone()[0]==1
    with pytest.raises(ValueError): register(db,[trade()],token='old-content')
    assert len(c.transaction_rows(db))==1
    bad={**updated,'quantity':'-1'}
    with pytest.raises(ValueError): c.revise_transaction(db,item['id'],bad,confirmed=True)
    assert c.ledger_positions(db)[0]['cost_jpy']==2010


def test_manual_balances_precede_ledger_and_survive_cancellation(db):
    a=register(db,[trade()])
    r=trade()
    c.add_holding(db,dict(broker='SBI証券',account=r['account'],name=r['name'],code=r['code'],asset_type=r['asset_type'],quantity=8,price=200,price_unit=1,currency='JPY',fx=1,cost_jpy=800,as_of='2026-10-10'))
    assert len(c.holdings(db))==1
    assert c.holdings(db)[0]['value_jpy']==1600
    assert c.reconciliation(db,c.manual_holdings(db))[0]['difference']==-2
    c.change_batch_status(db,a['batch_id'])
    assert c.holdings(db)[0]['value_jpy']==1600


def test_sbi_mapping_from_uploaded_headers(db):
    path=Path(__file__).resolve().parents[1]/'sample_data/phase2/sbi_fictional.csv'
    mapping={'executed_at':'架空約定日','name':'架空銘柄','code':'架空コード','kind':'架空売買','quantity':'架空数量','price':'架空単価','fee':'架空手数料','tax':'架空税額','account':'架空口座','external_id':'架空取引ID'}
    entries=SBIImporter().preview(path.read_bytes(),mapping,defaults={'asset_type':'日本株','currency':'JPY'},value_maps={'kind':{'買付':'buy','売却':'sell'}})
    assert len(entries)==3 and not any(e['errors'] for e in entries)
    c.register_batch(db,path.read_bytes(),'SBI架空CSV',entries,confirmed=True,complete_history=True)
    assert c.ledger_positions(db)[0]['realized_jpy']==740
    with pytest.raises(ValueError,match='存在しない列'):
        SBIImporter().preview(path.read_bytes(),{'name':'not present'})


def test_savings_import_does_not_double_count_positions_or_manual_records(db):
    register(db,[trade(price='500',quantity='10',fee='0')],is_savings=True)
    assert c.monthly(db,'2026-10')==5000
    assert c.holdings(db)[0]['quantity']==10
    c.add_contribution(db,'2026-10-02','SBI証券',5000)
    assert c.monthly(db,'2026-10')==10000
    with pytest.raises(ValueError,match='手入力積立実績'):
        register(db,[trade(executed_at='2026-10-02',external_id='manual-overlap',price='500',quantity='10',fee='0')],token='overlap',is_savings=True)


def test_pdf_fixture_extraction_and_manual_preview():
    path=Path(__file__).resolve().parents[1]/'sample_data/phase2/paypay_fictional.pdf'
    text=extract_pdf(path.read_bytes())
    draft=candidates(text)
    assert draft['name']=='FICTIONAL_US_STOCK'
    draft.update(account='特定',asset_type='米国株')
    entries=preview_rows([draft],'PayPay証券')
    assert not entries[0]['errors']
    assert entries[0]['data']['broker']=='PayPay証券'
    with pytest.raises(ValueError): extract_pdf(b'not a PDF')
    assert candidates('Name: A\nName: B')['name']==''


def test_initial_manual_balance_without_code_still_prevents_double_count(db):
    r=trade()
    c.add_holding(db,dict(broker='SBI証券',account='NISA',name=r['name'],asset_type='日本株',quantity=10,price=200,price_unit=1,currency='JPY',fx=1,cost_jpy=1000,as_of='2026-10-10'))
    register(db,[r])
    assert len(c.holdings(db))==1
    assert c.totals(db)['value_jpy']==2000
    assert '可能性' in c.reconciliation(db,c.manual_holdings(db))[0]['note']


def test_cancel_updates_savings_totals_and_preserves_cash(db):
    for account in c.account_balances(db):
        c.set_account_balances(db,account['id'],'100','5000')
    result=register(db,[trade(quantity='10',price='500',fee='0')],is_savings=True)
    assert c.monthly(db,'2026-10')==5000
    c.change_batch_status(db,result['batch_id'])
    assert c.monthly(db,'2026-10')==0
    assert c.totals(db)['cash_jpy']==200
    assert c.totals(db)['external_net_jpy']==10000
    c.change_batch_status(db,result['batch_id'],restore=True)
    assert c.monthly(db,'2026-10')==5000
    with pytest.raises(ValueError,match='取込済み積立実績'):
        c.add_contribution(db,'2026-10-01','SBI証券',5000)


def test_confirmations_and_unknown_kind_are_not_bypassed(db):
    with pytest.raises(ValueError,match='プレビュー'):
        c.register_batch(db,b'new','manual',preview_rows([trade()],'SBI証券'))
    entries=preview_rows([trade()],'SBI証券')
    entries[0]['data']['quantity']=Decimal(-1)
    with pytest.raises(ValueError):
        c.register_batch(db,b'forged','manual',entries,confirmed=True)
    assert not c.transaction_rows(db)
    assert preview_rows([trade(kind='unknown')],'SBI証券')[0]['errors']


def test_correction_which_breaks_later_sale_is_rolled_back(db):
    register(db,[trade(),trade(kind='sell',quantity='5',executed_at='2026-10-02',external_id='sale')])
    original=c.transaction_rows(db)[0]
    bad=trade(quantity='1',executed_at=original['executed_at'])
    with pytest.raises(ValueError,match='売却数量'):
        c.revise_transaction(db,original['id'],bad,confirmed=True)
    assert c.transaction_rows(db)[0]['quantity']==10
    assert db.execute('SELECT COUNT(*) FROM transaction_revisions').fetchone()[0]==0


def test_same_day_order_ambiguity_never_invents_cost(db):
    register(db,[trade(),trade(kind='sell',quantity='5',external_id='same-day-sale')])
    item=c.ledger_positions(db)[0]
    assert item['quantity']==5
    assert item['cost_jpy'] is None
    assert item['ambiguous_order']


def test_analysis_explains_concentration_overlap_cost_and_missing_data(db):
    from src.services.analysis import analyze,set_instrument_metadata
    c.seed(db)
    row=c.sample_rows()[0]
    row.update(broker='PayPay証券',account='特定')
    c.add_holding(db,row)
    fund=next(r for r in c.holdings(db) if r['asset_type']=='投資信託')
    set_instrument_metadata(db,fund['instrument_id'],'全世界','1.5')
    findings=analyze(db,'0.3','1')
    by_id={f['rule_id']:f for f in findings}
    assert by_id['concentration']['verdict']=='確認推奨'
    assert by_id['overlap']['verdict']=='確認推奨'
    assert by_id['cost_compare']['verdict']=='確認推奨'
    assert by_id['cost_missing']['verdict']=='情報不足'
    assert all(f['evidence'] and f['limitation'] and f['evaluated_at'] for f in findings)
    with pytest.raises(ValueError): set_instrument_metadata(db,fund['instrument_id'],'全世界','-1')


def test_csv_encoding_header_and_invalid_limits():
    from src.importers.trades import read_csv
    raw='前置き\n日付,銘柄\n2026-10-01,架空\n'.encode('cp932')
    headers,rows=read_csv(raw,1)
    assert headers==['日付','銘柄'] and rows[0]['銘柄']=='架空'
    for raw in [b'a,a\n1,2',b'a,b\n1,2,3',b'x'*(5*1024*1024+1)]:
        with pytest.raises(ValueError): read_csv(raw)


def test_image_only_pdf_falls_back_to_manual_input():
    from pypdf import PdfWriter
    writer=PdfWriter()
    writer.add_blank_page(width=100,height=100)
    stream=io.BytesIO()
    writer.write(stream)
    assert extract_pdf(stream.getvalue()).strip()==''
    writer.encrypt('not-a-real-password')
    stream=io.BytesIO()
    writer.write(stream)
    with pytest.raises(ValueError,match='暗号化PDF'):
        extract_pdf(stream.getvalue())


def test_phase1_schema_upgrade_preserves_balances(tmp_path):
    import sqlite3
    path=tmp_path/'phase1.db'
    old=sqlite3.connect(path)
    old.executescript('''CREATE TABLE transactions(id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, instrument_id INTEGER NOT NULL, executed_at TEXT NOT NULL, kind TEXT NOT NULL, quantity TEXT, price TEXT, tax TEXT, fee TEXT, amount TEXT NOT NULL, currency TEXT NOT NULL, source TEXT, external_id TEXT, UNIQUE(account_id,source,external_id));
    CREATE TABLE import_batches(id INTEGER PRIMARY KEY, file_hash TEXT UNIQUE, mapping_json TEXT, success_count INTEGER NOT NULL DEFAULT 0, failure_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL);
    ''')
    old.close()
    upgraded=c.connect(path)
    c.add_holding(upgraded,c.sample_rows()[0])
    assert c.holdings(upgraded)[0]['value_jpy']==50000
    assert 'batch_id' in {r[1] for r in upgraded.execute('PRAGMA table_info(transactions)')}
    upgraded.close()
    assert path.with_name('phase1.db.pre-phase2.bak').exists()


def test_new_external_id_does_not_duplicate_an_existing_natural_trade(db):
    register(db,[trade(external_id='')])
    with pytest.raises(ValueError):
        register(db,[trade(external_id='later-known-id')],token='later-document')
    assert len(c.transaction_rows(db))==1


def test_integer_zero_fees_remain_known_after_save(db):
    register(db,[trade(fee=0,tax=0)])
    item=c.transaction_rows(db)[0]
    assert item['fee']==0 and item['tax']==0
    assert item['amount']==1000
    assert c.ledger_positions(db)[0]['cost_jpy']==1000


def test_failure_log_cannot_deactivate_registered_file(db):
    from src.services.imports import record_failure
    register(db,[trade()])
    with pytest.raises(ValueError): record_failure(db,b'file1','error','bad')
    assert len(c.transaction_rows(db))==1


def test_corrected_natural_identity_is_retained_as_an_alias(db):
    register(db,[trade(external_id='')])
    old=c.transaction_rows(db)[0]
    edited=trade(external_id='',executed_at=old['executed_at'],fee='20')
    c.revise_transaction(db,old['id'],edited,confirmed=True)
    assert c.ledger_positions(db)[0]['cost_jpy']==1020
    with pytest.raises(ValueError):
        register(db,[trade(external_id='')],token='old-natural-row')
    assert len(c.transaction_rows(db))==1


def test_samples_cannot_be_mixed_into_a_transaction_only_portfolio(db):
    register(db,[trade()])
    with pytest.raises(ValueError,match='未登録'):
        c.seed(db)
    assert len(c.transaction_rows(db))==1
    assert c.manual_holdings(db)==[]
