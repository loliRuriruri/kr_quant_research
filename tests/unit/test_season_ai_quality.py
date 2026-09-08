import json
from types import SimpleNamespace
import pytest
from kr_quant.research.season_ai_quality import validate_season_card
from kr_quant.research.tier1_contract import tier1_cached_chat_json, tier1_success, tier1_deterministic_fallback

VALID = dict(headline='현재 근거 확인 필요', seasonality_brief='과거 관찰값입니다.',
             sample_caution='표본이 적습니다.', next_check='최신 수급 확인', key_catalysts=[])

@pytest.mark.parametrize('change', [{}, {'next_check': ''}, {'headline': None},
    {'seasonality_brief': '+nan%'}, {'key_catalysts': '가설'}, {'sample_caution': 'x'*701}])
def test_schema_gate(change):
    if not change:
        validate_season_card(VALID)
    else:
        with pytest.raises(ValueError):
            validate_season_card({**VALID, **change})

def test_invalid_output_not_cached(monkeypatch, tmp_path):
    from kr_quant.research import analyze
    endpoint = SimpleNamespace(provider='test', model='test')
    monkeypatch.setattr(analyze, 'call_chat', lambda *a, **k: (json.dumps({'headline':'only'}), {}))
    result = tier1_cached_chat_json(tmp_path, endpoint, namespace='seasonality', prompt_version='test',
        evidence={}, messages=[], payload_validator=validate_season_card)
    assert not result['ok'] and not result['ai_generated'] and not result['cache']['stored']
    assert not list(tmp_path.rglob('*.json'))

@pytest.mark.parametrize('factory,expected', [(tier1_success, True), (tier1_deterministic_fallback, False)])
def test_payload_cannot_override_provenance(factory, expected):
    result = factory(SimpleNamespace(provider='real', model='real'),
        {'ai_generated': not expected, 'provider': 'fake', 'used_in_quant': True}, prompt_version='test')
    assert result['ai_generated'] is expected
    assert result['provider'] == 'real' and result['used_in_quant'] is False
