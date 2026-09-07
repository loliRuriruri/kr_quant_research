"""Offline full staged-input replay of baseline vs corrected scoring.

Copies non-secret inputs to a new audit directory; never publishes production
outputs. The baseline swaps ONLY peers.py and freshness_component from the
specified Git revision. All other pipeline code/config stays identical.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import replace
from datetime import date
import json
from pathlib import Path
import shutil
import socket
import subprocess
import time
import types
from unittest.mock import patch

import pandas as pd

from kr_quant.hashing import sha256_file
from kr_quant.settings import load_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', default='bd09ece')
    parser.add_argument('--as-of', required=True)
    args = parser.parse_args()
    s = load_settings()
    stamp = time.strftime('%Y%m%d-%H%M%S')
    audit = s.root / 'output' / 'audit' / f'full-replay-{stamp}'
    audit.mkdir(parents=True, exist_ok=False)
    inputs = audit / 'inputs'
    shutil.copytree(s.root / 'config', inputs / 'config')
    for name in ('prices.parquet', 'financial_facts.parquet', 'master.parquet', 'extra.parquet', 'listing_history.parquet', 'corporate_actions.parquet'):
        src = s.staged_dir / 'live' / name
        if src.exists():
            dst = inputs / 'data' / 'staged' / 'live' / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    if s.status_csv.exists():
        shutil.copy2(s.status_csv, inputs / 'status.csv')
    for src in s.output_dir.glob('as_of_date=*/universe_snapshot.parquet'):
        dst = inputs / 'data' / 'output' / src.parent.name / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    hashes = {str(p.relative_to(inputs)): sha256_file(p) for p in inputs.rglob('*') if p.is_file()}
    (audit / 'input_hashes.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')

    from kr_quant.orchestration import run
    from kr_quant.scoring import composite
    baseline = {}
    for module in ('peers', 'composite'):
        text = subprocess.check_output(['git', 'show', f'{args.baseline}:src/kr_quant/scoring/{module}.py'], cwd=s.root, text=True, encoding='utf-8')
        mod = types.ModuleType(f'audit_{module}')
        exec(compile(text, f'{args.baseline}:{module}', 'exec'), mod.__dict__)
        baseline[module] = mod
    original_peers, original_freshness = run.assign_peer_scores, composite.freshness_component
    results = {}
    for mode in ('baseline', 'current', 'repeat'):
        root = audit / mode
        shutil.copytree(inputs, root)
        cfg = copy.deepcopy(s.config)
        cfg.setdefault('status_feed', {})['path'] = 'status.csv'
        isolated = replace(s, root=root, config=cfg)
        run.assign_peer_scores = baseline['peers'].assign_peer_scores if mode == 'baseline' else original_peers
        composite.freshness_component = baseline['composite'].freshness_component if mode == 'baseline' else original_freshness
        start = time.perf_counter()
        print(f'START {mode} {root}', flush=True)
        try:
            with patch.object(socket.socket, 'connect', side_effect=RuntimeError('Audit disallows network')):
                result = run.run_from_staged(isolated, date.fromisoformat(args.as_of), root / 'data' / 'staged' / 'live', publish_latest=False, source_mode='live')
            results[mode] = result
            print(f'DONE {mode} {time.perf_counter()-start:.1f}s rows={len(result["records"])} status={result["manifest"]["status"]}', flush=True)
        finally:
            run.assign_peer_scores, composite.freshness_component = original_peers, original_freshness
    frames = {k: pd.DataFrame(v['records']).set_index('ticker') for k, v in results.items()}
    before, after = frames['baseline'], frames['current']
    delta = after['quant_score'] - before['quant_score']
    changed = pd.DataFrame({'before': before['quant_score'], 'after': after['quant_score'], 'delta': delta})
    changed.to_csv(audit / 'score_changes.csv', encoding='utf-8-sig')
    report = {
        'as_of': args.as_of, 'baseline_scoring_revision': args.baseline,
        'scope': 'Full staged-input pipeline; only peer and freshness implementations differ; not a full historical Git-tree comparison.',
        'input_files': hashes, 'production_outputs_modified': False,
        'rows': len(after), 'changed_scores': int((delta.abs() > 1e-8).sum()),
        'max_abs_delta': float(delta.abs().max()),
        'repeat_result_hash_equal': results['current']['context'].result_hash == results['repeat']['context'].result_hash,
        'runs': {}, 'top_membership': {},
    }
    for mode, result in results.items():
        f = frames[mode]
        report['runs'][mode] = {
            'status': result['manifest']['status'], 'warnings': result['manifest']['warnings'],
            'universe_eligible': int(f['universe_eligible'].sum()),
            'exclusions': f['exclusion_reasons'].explode().dropna().value_counts().to_dict(),
        }
    for key in ('top20', 'top100'):
        old = set(results['baseline'][key]['ticker'])
        new = set(results['current'][key]['ticker'])
        report['top_membership'][key] = {'before_n': len(old), 'after_n': len(new), 'added': sorted(new-old), 'removed': sorted(old-new)}
    (audit / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'input_files'}, ensure_ascii=False, indent=2), flush=True)
    print(f'REPORT {audit / "report.json"}', flush=True)


if __name__ == '__main__':
    main()
