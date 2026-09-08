import json
from types import SimpleNamespace
import pytest
from kr_quant.research import tier1_contract as contract
from kr_quant.research import approved_season_ai as approved
from kr_quant.research.season_ai_quality import validate_season_card

FREE = SimpleNamespace(provider='openrouter', model='test:free', configured=True)
PAID = SimpleNamespace(provider='xai', model='grok-test', configured=True)
CARD = dict(headline='관찰', seasonality_brief='과거 +8%', sample_caution='표본 제한', next_check='수급 확인', key_catalysts=[])

def setup(root, limit=6):
    (root/'config').mkdir()
    (root/'config/season_ai.json').write_text(json.dumps({'grok_fallback_enabled': True, 'daily_attempt_limit': limit}), encoding='utf-8')

def request(root, **extra):
    return contract.tier1_cached_chat_json(root, FREE, namespace='seasonality', prompt_version='test',
        evidence={'v':extra.pop('version',1)}, messages=[], evidence_count=1, as_of='2026-09-08',
        sources=['test'], missing=[], payload_validator=validate_season_card, fallback_endpoint=PAID, **extra)

def test_paid_fallback_and_cached_reuse(monkeypatch, tmp_path):
    setup(tmp_path)
    calls=[]
    def chat(endpoint, *args):
        calls.append(endpoint.provider)
        if endpoint.provider == 'openrouter': raise TimeoutError()
        return json.dumps(CARD), {}
    monkeypatch.setattr(approved, 'bounded_chat', chat)
    first=request(tmp_path)
    assert first['ok'] and first['provider']=='xai' and first['ai_generated']
    assert '무료' not in first['tier']
    second=request(tmp_path)
    assert second['cache']['hit'] and calls==['openrouter','xai']
    assert json.loads((tmp_path/'data/cache/tier1_briefings/season-budget.json').read_text())['attempts']==1

def test_free_success_does_not_spend_paid(monkeypatch, tmp_path):
    setup(tmp_path)
    monkeypatch.setattr(approved, 'bounded_chat', lambda *a: (json.dumps(CARD), {}))
    assert request(tmp_path)['provider']=='openrouter'
    assert not (tmp_path/'data/cache/tier1_briefings/season-budget.json').exists()

def test_failure_cooldown_and_persistent_budget(monkeypatch, tmp_path):
    setup(tmp_path, 1)
    calls=[]
    def fail(endpoint, *args):
        calls.append(endpoint.provider); raise TimeoutError()
    monkeypatch.setattr(approved, 'bounded_chat', fail)
    assert not request(tmp_path)['ok']
    assert request(tmp_path)['error_code']=='AI_RETRY_COOLDOWN'
    assert calls==['openrouter','xai']
    state=tmp_path/'data/cache/tier1_briefings/season-budget.json'
    value=json.loads(state.read_text()); value['next_try']=0; state.write_text(json.dumps(value))
    assert request(tmp_path,version=2)['error_code']=='AI_DAILY_LIMIT'
    assert calls.count('xai')==1

def test_corrupt_budget_fails_closed(monkeypatch, tmp_path):
    setup(tmp_path)
    folder=tmp_path/'data/cache/tier1_briefings'; folder.mkdir(parents=True)
    (folder/'season-budget.json').write_text('broken')
    monkeypatch.setattr(approved, 'bounded_chat', lambda *a: pytest.fail('no network'))
    assert request(tmp_path)['error_code']=='AI_BUDGET_UNREADABLE'

def test_no_approval_uses_original_route(monkeypatch, tmp_path):
    from kr_quant.research import analyze
    monkeypatch.setattr(analyze, 'call_chat', lambda endpoint,*a,**k: (json.dumps(CARD), {}))
    assert request(tmp_path)['provider']=='openrouter'
