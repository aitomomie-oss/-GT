import json
from pathlib import Path
import pytest
import streamlit as st
from src.market_data import credentials as c
from src.market_data.jquants import JQuantsV2
from src.market_data.base import MarketDataError
from src.market_data.request_limits import RequestBudget

@pytest.fixture
def project(tmp_path,monkeypatch):
    folder=tmp_path/'app';(folder/'.streamlit').mkdir(parents=True)
    monkeypatch.setattr(c,'PROJECT_ROOT',folder)
    monkeypatch.setattr(st,'secrets',{})
    monkeypatch.delenv('JQUANTS_API_KEY',raising=False)
    return folder


def test_project_file_from_other_working_directory(project,tmp_path,monkeypatch):
    (project/'.streamlit/secrets.toml').write_text('JQUANTS_API_KEY="test-project-token"')
    other=tmp_path/'other';other.mkdir();monkeypatch.chdir(other)
    assert c.jquants_key()=='test-project-token'
    status=c.credential_status()
    assert status['source']=='project_secrets' and status['working_directory']==str(other)
    assert str(project/'.streamlit/secrets.toml')==status['project_file']
    assert 'test-project-token' not in json.dumps(status)


def test_project_priority_over_streamlit_and_environment(project,monkeypatch):
    (project/'.streamlit/secrets.toml').write_text('JQUANTS_API_KEY="test-project-token"')
    monkeypatch.setattr(st,'secrets',{'JQUANTS_API_KEY':'test-streamlit-token'})
    monkeypatch.setenv('JQUANTS_API_KEY','test-environment-token')
    assert c.jquants_key()=='test-project-token'


def test_nested_bom_and_reread_without_restart(project):
    path=project/'.streamlit/secrets.toml'
    path.write_text('[jquants]\napi_key="test-first-token"',encoding='utf-8-sig')
    assert c.jquants_key()=='test-first-token'
    path.write_text('JQUANTS_API_KEY="test-replaced-token"')
    assert c.jquants_key()=='test-replaced-token'


def test_streamlit_global_fallback(project,monkeypatch):
    monkeypatch.setattr(st,'secrets',{'jquants':{'api_key':'test-global-token'}})
    assert c.jquants_key()=='test-global-token'
    assert c.credential_status()['source']=='streamlit_secrets'


def test_broken_toml_falls_back_to_environment_without_leak(project,monkeypatch,capsys,caplog):
    (project/'.streamlit/secrets.toml').write_text('JQUANTS_API_KEY="sensitive-unclosed')
    monkeypatch.setenv('JQUANTS_API_KEY','test-fallback-token')
    assert c.jquants_key()=='test-fallback-token'
    status=c.credential_status()
    assert 'project_secrets_unreadable' in status['issues'] and status['source']=='environment'
    captured=capsys.readouterr()
    assert 'sensitive-unclosed' not in captured.out+captured.err+caplog.text+json.dumps(status)
    assert 'test-fallback-token' not in captured.out+captured.err+caplog.text+json.dumps(status)


def test_streamlit_exception_still_uses_env(project,monkeypatch):
    class Broken:
        def get(self,*args): raise RuntimeError('sensitive-error-content')
    monkeypatch.setattr(st,'secrets',Broken());monkeypatch.setenv('JQUANTS_API_KEY',' test-env-token ')
    assert c.jquants_key()=='test-env-token'
    assert 'sensitive-error-content' not in json.dumps(c.credential_status())

@pytest.mark.parametrize('value',['123','"test token"','"test\\nnewline"'])
def test_invalid_key_diagnosed_without_request(project,value):
    (project/'.streamlit/secrets.toml').write_text('JQUANTS_API_KEY='+value)
    calls=[]
    with pytest.raises(MarketDataError,match='未設定'):
        JQuantsV2(request=lambda *args:calls.append(args)).search('1234')
    assert calls==[] and not c.credential_status()['configured']


def test_master_search_resolves_file_and_preserves_v2_protocol(project):
    (project/'.streamlit/secrets.toml').write_text('JQUANTS_API_KEY="test-project-token"')
    def request(path,params,key):
        assert path=='/equities/master' and params=={'code':'1234','date':'2026-01-05'}
        assert key=='test-project-token'
        return {'data':[dict(Code='12340',CoName='架空企業',Date='2026-01-05')]}
    rows=JQuantsV2(request=request).search('1234','2026-01-05')
    assert rows[0]['name']=='架空企業' and rows[0]['delayed']


def test_shared_request_budget_and_retry_after():
    now=[0.0];budget=RequestBudget(clock=lambda:now[0])
    for _ in range(5): budget.acquire('test-secret')
    with pytest.raises(MarketDataError) as error: budget.acquire('test-secret')
    assert error.value.code=='rate_limit'
    budget.defer('test-secret','120');now[0]=61
    with pytest.raises(MarketDataError): budget.acquire('test-secret')
    now[0]=120;budget.acquire('test-secret')
    assert 'test-secret' not in repr(budget.states)


def test_transport_v2_header_and_429_cooldown(monkeypatch):
    from urllib.error import HTTPError
    from src.market_data import jquants,request_limits
    budget=RequestBudget(clock=lambda:0.0);monkeypatch.setattr(request_limits,'BUDGET',budget)
    seen=[]
    class Opener:
        def open(self,request,timeout):
            seen.append(request)
            assert request.get_header('X-api-key')=='test-v2-token'
            assert request.get_header('Authorization') is None
            raise HTTPError(request.full_url,429,'do-not-display',{'Retry-After':'120'},None)
    monkeypatch.setattr(jquants,'build_opener',lambda *args:Opener())
    for _ in range(2):
        with pytest.raises(MarketDataError) as error: jquants.transport('/equities/master',{},'test-v2-token')
        assert error.value.code=='rate_limit' and 'test-v2-token' not in str(error.value)
    assert len(seen)==1

def test_master_update_button_from_other_cwd_uses_project_key(project,tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src.market_data import jquants
    from src.db.session import connect
    from src.services.auto_discovery import universe
    root=Path(__file__).resolve().parents[1]
    (project/'.streamlit/secrets.toml').write_text('JQUANTS_API_KEY="test-ui-only-token"')
    db_path=tmp_path/'ui.db';monkeypatch.setenv('MY_AI_ASSET_DB',str(db_path))
    other=tmp_path/'other';other.mkdir();monkeypatch.chdir(other)
    calls=[]
    def request(path,params,key):
        calls.append(path)
        assert key=='test-ui-only-token'
        assert path=='/equities/master'
        return {'data':[dict(Code='12340',CoName='架空の確認企業',Date=params['date'],Mkt='0111',S33='5250',S33Nm='情報',MktNm='プライム')]}
    monkeypatch.setattr(jquants,'transport',request)
    app=AppTest.from_file(str(root/'app.py')).run(timeout=30)
    app.switch_page('pages/7_AI銘柄探索.py').run(timeout=30)
    next(b for b in app.button if b.key=='auto_master').click().run(timeout=30)
    assert not app.exception
    assert calls==['/equities/master']
    assert 'test-ui-only-token' not in str(app)
    db=connect(db_path)
    assert universe(db)[0]['code']=='12340'
    assert db.execute('SELECT COUNT(*) FROM positions').fetchone()[0]==0
    db.close()
    # Successful master cache is reused without a second API request.
    next(b for b in app.button if b.key=='auto_master').click().run(timeout=30)
    assert not app.exception and calls==['/equities/master']
