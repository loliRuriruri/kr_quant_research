import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from kr_quant.research import tier1_contract as contract
from kr_quant.research import approved_season_ai as approved
from kr_quant.research.season_ai_quality import validate_season_card

FREE = SimpleNamespace(provider='openrouter', model='test:free', configured=True)
PAID = SimpleNamespace(provider='xai', model='grok-test', configured=True)
FLASH = SimpleNamespace(provider='openrouter', model='deepseek/deepseek-v4-flash-0731', configured=True)
PRO = SimpleNamespace(provider='openrouter', model='deepseek/deepseek-v4-pro-0813', configured=True)
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
    assert calls==['openrouter','xai','openrouter']
    state=tmp_path/'data/cache/tier1_briefings/season-budget.json'
    value=json.loads(state.read_text()); value['next_try']=0; state.write_text(json.dumps(value))
    assert request(tmp_path,version=2)['error_code']=='AI_DAILY_LIMIT'
    assert calls.count('xai')==1
    assert calls.count('openrouter')==3

def test_corrupt_budget_fails_closed(monkeypatch, tmp_path):
    setup(tmp_path)
    folder=tmp_path/'data/cache/tier1_briefings'; folder.mkdir(parents=True)
    (folder/'season-budget.json').write_text('broken')
    monkeypatch.setattr(approved, 'bounded_chat', lambda *a: pytest.fail('no network'))
    assert request(tmp_path)['error_code']=='AI_BUDGET_UNREADABLE'

def test_flow_namespace_can_use_paid_fallback(monkeypatch, tmp_path):
    setup(tmp_path)
    calls=[]
    def chat(endpoint, *args):
        calls.append(endpoint.provider)
        if endpoint.provider == 'openrouter':
            raise TimeoutError()
        return json.dumps(CARD), {}
    monkeypatch.setattr(approved, 'bounded_chat', chat)
    result = contract.tier1_cached_chat_json(
        tmp_path, FREE, namespace='flow', prompt_version='test',
        evidence={'k': 1}, messages=[], evidence_count=1, as_of='2026-09-08',
        sources=['kis'], missing=['investor_flow_events'], fallback_endpoint=PAID)
    assert result['ok'] and result['provider'] == 'xai'
    assert calls == ['openrouter', 'xai']


def test_no_approval_uses_original_route(monkeypatch, tmp_path):
    from kr_quant.research import analyze
    monkeypatch.setattr(analyze, 'call_chat', lambda endpoint,*a,**k: (json.dumps(CARD), {}))
    assert request(tmp_path)['provider']=='openrouter'


def test_compatible_cache_skips_timeout_when_budget_spent(monkeypatch, tmp_path):
    setup(tmp_path, 1)
    folder = tmp_path / 'data/cache/tier1_briefings'
    folder.mkdir(parents=True)
    today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    (folder / 'season-budget.json').write_text(
        json.dumps({'day': today, 'attempts': 1, 'next_try': 0}), encoding='utf-8')
    cached = {
        **CARD,
        'ok': True, 'status': 'GENERATED', 'ai_generated': True,
        'provider': 'xai', 'model': 'grok-test', 'prompt_version': 'test',
        'evidence': {'as_of': today, 'missing': ['168360: 현재 확인 지표 미연결']},
        'cache': {'key': 'old', 'evidence_hash': 'old'},
    }
    (folder / 'seasonality_oldhash.json').write_text(json.dumps(cached), encoding='utf-8')
    monkeypatch.setattr(approved, 'bounded_chat', lambda *a: pytest.fail('network should not run'))
    result = contract.tier1_cached_chat_json(
        tmp_path, FREE, namespace='seasonality', prompt_version='test',
        evidence={'candidates': [{'ticker': '168360'}]}, messages=[],
        evidence_count=1, as_of=today, sources=['test'],
        missing=['168360: 현재 확인 지표 미연결'],
        payload_validator=validate_season_card, fallback_endpoint=PAID)
    assert result['ok'] and result['provider'] == 'xai'
    assert result['cache']['compatible_reuse'] is True


def test_daily_limit_still_tries_routine_but_skips_analysis(monkeypatch, tmp_path):
    setup(tmp_path, 1)
    folder = tmp_path / 'data/cache/tier1_briefings'
    folder.mkdir(parents=True)
    today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    (folder / 'season-budget.json').write_text(
        json.dumps({'day': today, 'attempts': 1, 'next_try': 0}), encoding='utf-8')
    calls = []
    def chat(endpoint, *args):
        calls.append(endpoint.provider)
        if endpoint.provider == 'openrouter':
            return json.dumps(CARD), {}
        raise AssertionError('analysis hop must not run when budget is spent')
    monkeypatch.setattr(approved, 'bounded_chat', chat)
    result = request(tmp_path)
    assert result['ok'] and result['provider'] == 'openrouter'
    assert calls == ['openrouter']


def test_daily_limit_without_cache_skips_grok(monkeypatch, tmp_path):
    setup(tmp_path, 1)
    folder = tmp_path / 'data/cache/tier1_briefings'
    folder.mkdir(parents=True)
    today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    (folder / 'season-budget.json').write_text(
        json.dumps({'day': today, 'attempts': 1, 'next_try': 0}), encoding='utf-8')
    calls = []
    def fail(endpoint, *args):
        calls.append(endpoint.provider)
        raise TimeoutError()
    monkeypatch.setattr(approved, 'bounded_chat', fail)
    result = request(tmp_path)
    assert result['error_code'] == 'AI_DAILY_LIMIT'
    assert calls == ['openrouter']


def test_flash_before_grok_does_not_spend_analysis_budget(monkeypatch, tmp_path):
    setup(tmp_path)
    calls = []
    def chat(endpoint, *args):
        calls.append(endpoint.model)
        if str(endpoint.model).endswith(':free'):
            raise TimeoutError()
        return json.dumps(CARD), {}
    monkeypatch.setattr(approved, 'bounded_chat', chat)
    result = request(tmp_path, routine_endpoint=FLASH)
    assert result['ok'] and result['model'] == FLASH.model
    assert calls == ['test:free', FLASH.model]
    assert not (tmp_path / 'data/cache/tier1_briefings/season-budget.json').exists()


def test_analysis_hop_uses_configured_provider(monkeypatch, tmp_path):
    setup(tmp_path)
    ns = SimpleNamespace(openrouter_api_key=None, xai_api_key=None, deepseek_api_key=None,
        opencode_api_key=None, opencode_go_api_key='go-test', xai_base_url=None,
        tier1_analysis_provider='opencode_go', tier1_analysis_model='minimax-m3')
    monkeypatch.setattr('kr_quant.settings.load_settings', lambda: ns)
    calls = []
    def chat(endpoint, *args):
        calls.append((endpoint.provider, endpoint.model))
        if endpoint.provider == 'openrouter':
            raise TimeoutError()
        return json.dumps(CARD), {}
    monkeypatch.setattr(approved, 'bounded_chat', chat)
    result = contract.tier1_cached_chat_json(tmp_path, FREE, namespace='seasonality', prompt_version='test',
        evidence={'v': 9}, messages=[], evidence_count=1, as_of='2026-09-08',
        sources=['test'], missing=[], payload_validator=validate_season_card)
    assert result['ok'] and result['provider'] == 'opencode_go'
    assert ('opencode_go', 'minimax-m3') in calls


def test_analysis_pro_after_grok_failure(monkeypatch, tmp_path):
    setup(tmp_path)
    calls = []
    def chat(endpoint, *args):
        calls.append(endpoint.model)
        if endpoint.model == PRO.model:
            return json.dumps(CARD), {}
        raise TimeoutError()
    monkeypatch.setattr(approved, 'bounded_chat', chat)
    result = request(tmp_path, analysis_pro_endpoint=PRO)
    assert result['ok'] and result['model'] == PRO.model
    assert calls == ['test:free', 'grok-test', PRO.model]
    budget = json.loads((tmp_path / 'data/cache/tier1_briefings/season-budget.json').read_text(encoding='utf-8'))
    assert budget['attempts'] == 1
    assert budget['next_try'] == 0


def test_compatible_cache_without_tickers(monkeypatch, tmp_path):
    setup(tmp_path)
    folder = tmp_path / 'data/cache/tier1_briefings'
    folder.mkdir(parents=True)
    today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    cached = {
        **CARD,
        'ok': True, 'status': 'GENERATED', 'ai_generated': True,
        'provider': 'openrouter', 'model': 'test:free', 'prompt_version': 'test',
        'evidence': {'as_of': '2026-09-08', 'missing': []},
        'cache': {'key': 'old', 'evidence_hash': 'old'},
    }
    (folder / 'seasonality_notickers.json').write_text(json.dumps(cached), encoding='utf-8')
    monkeypatch.setattr(approved, 'bounded_chat', lambda *a: pytest.fail('network should not run'))
    result = request(tmp_path)
    assert result['ok'] and result['cache']['compatible_reuse'] is True


def test_last_generated_keeps_pane_when_live_fails(monkeypatch, tmp_path):
    setup(tmp_path, 1)
    folder = tmp_path / 'data/cache/tier1_briefings'
    folder.mkdir(parents=True)
    today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    (folder / 'season-budget.json').write_text(
        json.dumps({'day': today, 'attempts': 1, 'next_try': 0}), encoding='utf-8')
    cached = {
        **CARD,
        'ok': True, 'status': 'GENERATED', 'ai_generated': True,
        'provider': 'xai', 'model': 'grok-test', 'prompt_version': 'test',
        'evidence': {'as_of': '2026-09-08'},
        'cache': {'key': 'old', 'evidence_hash': 'old'},
    }
    (folder / 'seasonality_keep.json').write_text(json.dumps(cached), encoding='utf-8')
    def fail(*_args):
        raise TimeoutError()
    monkeypatch.setattr(approved, 'bounded_chat', fail)
    result = contract.tier1_cached_chat_json(
        tmp_path, FREE, namespace='seasonality', prompt_version='test',
        evidence={'candidates': [{'ticker': '005930'}]}, messages=[],
        evidence_count=1, as_of='2026-09-08', sources=['test'], missing=[],
        payload_validator=validate_season_card, fallback_endpoint=PAID)
    assert result['ok'] and result['provider'] == 'xai'
    assert result['cache']['last_good_reuse'] is True
