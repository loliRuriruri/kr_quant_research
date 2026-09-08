from types import SimpleNamespace
from kr_quant.web import app as web


def test_season_card_supplies_candidate_facts_and_snapshot(monkeypatch, tmp_path):
    from kr_quant.research import providers
    monkeypatch.setattr(web, 'load_settings', lambda: SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(providers, 'resolve_tier1_endpoint', lambda s: object())
    monkeypatch.setattr(web, 'api_seasonality_highlights_get', lambda: {
        'snapshot': {'generation_id': 'g1', 'selection_date': '2026-09-08'},
        'data': {'glance_top3': [{'ticker': '105560', 'signal_id': 's1',
            'current_confirmation_missing': ['수급'],
            'remaining_peak': {'sample_count': 3, 'window_end_p50': -.1,
                               'window_end_positive_count': 0}}]}})
    captured = {}
    def chat(*args, **kwargs):
        captured.update(kwargs)
        return {'ok': True}
    monkeypatch.setattr(web, 'tier1_cached_chat_json', chat)
    assert web.api_seasonality_tier1_briefing_get()['ok']
    row = captured['evidence']['candidates'][0]
    assert row['ticker'] == '105560'
    assert row['sample_count'] == 3
    assert row['missing'] == ['수급']
    assert 'observed_window' not in row
    assert captured['evidence']['selection_date'] == '2026-09-08'
    assert 'snapshot' not in captured['evidence']
    assert 'next_check' in captured['messages'][1]['content']
    assert '+8%' in captured['messages'][1]['content']
    assert '식별자일 뿐' in captured['messages'][1]['content']
    assert '데이터 충돌이나 모순' in captured['messages'][1]['content']
    assert '올해 근거 없음' in captured['messages'][1]['content']
    assert captured['prompt_version'] == 'seasonality_tier1_v8_direct_verdict'
