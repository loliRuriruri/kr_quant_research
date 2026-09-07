"""Lossless, offline public transport preparation. No collection or publication."""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from kr_quant.web.season_listing import EXPLANATION_FIELDS, pre_entry_card
from kr_quant.web.transport import pack_rows
from kr_quant.atomic_io import write_json_atomic


def write_public(path, payload):
    write_json_atomic(path, payload, compact=True)


def optimize(folder: Path):
    manifest_path = folder / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    changes = {}
    route = '/api/seasonality/discovery'
    if route in manifest['routes'] and not manifest.get('season_details'):
        path = folder / manifest['routes'][route]
        data = json.loads(path.read_text(encoding='utf-8'))
        if (data.get('ok') and isinstance(data.get('rows'), list)
                and (data.get('snapshot') or {}).get('generation_id')
                and all(row.get('signal_id') and row.get('generation_id') for row in data['rows'])):
            before = path.stat().st_size
            grouped = {}
            fields = EXPLANATION_FIELDS | {'event_hypothesis', 'confirmation_state', 'event_group_id',
                                         'group_id', 'avg_return', 'failure_observations'}
            for row in data['rows']:
                code = str(row.get('ticker', ''))
                if not re.fullmatch(r'[0-9A-Z]{6}', code):
                    raise ValueError('Invalid public season ticker')
                grouped.setdefault(code, []).append(row)
            for code, rows in grouped.items():
                write_public(folder / 'season-details' / f'{code}.json',
                                  {'ok': True, 'ticker': code, 'patterns': rows,
                                   'snapshot': data.get('snapshot'), 'public_snapshot': True})
            index = [{**{k: v for k, v in row.items() if k in fields},
                      'detail_required': True, 'lookback_years': data.get('lookback_years', 5)}
                     for row in data['rows']]
            # Details are written before replacing the index/manifest.
            write_public(path, {**data, 'rows': index})
            manifest['season_details'] = {'base': 'season-details', 'count': len(grouped),
                                          'lookback_years': data.get('lookback_years', 5),
                                          'horizon_days': data.get('horizon_days', 90)}
            changes['season_listing_bytes'] = [before, path.stat().st_size]
    if manifest.get('season_details') and not manifest.get('season_listing'):
        path = folder / manifest['routes']['/api/seasonality/discovery']
        data = json.loads(path.read_text(encoding='utf-8'))
        before = path.stat().st_size
        rows = data['rows']
        index_fields = {'ticker', 'company', 'window_name', 'grade', 'current_status', 'entry_stage',
                        'common_event_cluster', 'confirmation_state', 'event_group_id', 'group_id',
                        'win_rate', 'avg_return', 'median_return'}
        index = []
        files = []
        for start in range(0, len(rows), 50):
            filename = f'season-list/{start // 50}.json'
            write_public(folder / filename, {'rows': rows[start:start + 50]})
            files.append(filename)
            index.extend({**{k: v for k, v in row.items() if k in index_fields},
                          '_chunk': start // 50, '_index': offset}
                         for offset, row in enumerate(rows[start:start + 50]))
        write_public(path, {**data, 'rows': index})
        manifest['season_listing'] = {'chunks': files, 'page_size': 50}
        changes['season_filter_index_bytes'] = [before, path.stat().st_size]
    route = '/api/flow'
    if route in manifest['routes']:
        path = folder / manifest['routes'][route]
        data = json.loads(path.read_text(encoding='utf-8'))
        if '_row_transport' not in data and isinstance(data.get('rows'), list):
            before = path.stat().st_size
            write_public(path, pack_rows(data))
            changes['flow_bytes'] = [before, path.stat().st_size]
    route = '/api/seasonality/pre-entry'
    if manifest.get('season_details') and route in manifest['routes']:
        path = folder / manifest['routes'][route]
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('ok') and not data.get('compact'):
            index_path = folder / manifest['routes']['/api/seasonality/discovery']
            index = json.loads(index_path.read_text(encoding='utf-8'))
            if (data.get('snapshot') or {}).get('generation_id') == (index.get('snapshot') or {}).get('generation_id'):
                before = path.stat().st_size
                data['rows'] = [pre_entry_card(row, manifest['season_details']['lookback_years']) for row in data['rows']]
                data['compact'] = True
                write_public(path, data)
                changes['pre_entry_bytes'] = [before, path.stat().st_size]
    manifest['transport_version'] = 2
    write_public(manifest_path, manifest)
    return changes


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', required=True)
    print(json.dumps(optimize(Path(parser.parse_args().folder)), ensure_ascii=False))
