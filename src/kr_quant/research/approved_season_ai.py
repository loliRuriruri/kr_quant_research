"""Explicitly approved, bounded Grok fallback for the season pilot only."""
import json
import os
import queue
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path


def policy(root):
    try:
        value = json.loads((Path(root) / 'config/season_ai.json').read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def bounded_chat(endpoint, messages, timeout, deadline):
    from kr_quant.research.analyze import call_chat
    result = queue.Queue(maxsize=1)
    def worker():
        try:
            result.put((True, call_chat(endpoint, messages, timeout=timeout, json_mode=True)))
        except Exception as exc:
            result.put((False, exc))
    threading.Thread(target=worker, daemon=True).start()
    try:
        ok, value = result.get(timeout=deadline)
    except queue.Empty:
        raise TimeoutError('AI response deadline exceeded') from None
    if not ok:
        raise value
    return value


def approved_briefing(root, endpoint, fallback, **kwargs):
    from kr_quant.research import tier1_contract as contract
    cfg = policy(root)
    if kwargs['namespace'] != 'seasonality' or cfg.get('grok_fallback_enabled') is not True:
        return contract.tier1_cached_chat_json(root, endpoint, **kwargs)
    def unavailable(code, message):
        return contract.tier1_unavailable(fallback, code=code, message=message,
            **{key: kwargs[key] for key in ('prompt_version', 'as_of', 'sources', 'evidence_count', 'missing')})
    if fallback.provider != 'xai' or not fallback.configured:
        return contract.tier1_cached_chat_json(root, endpoint, **kwargs)
    folder = Path(root) / 'data/cache/tier1_briefings'
    folder.mkdir(parents=True, exist_ok=True)
    # OS file lock covers multiple server processes and is released on crashes.
    lock = (folder / 'season-fallback.lock').open('a+b')
    acquired = False
    try:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            return unavailable('AI_REQUEST_PENDING', '시즌 분석이 이미 진행 중입니다. 잠시 후 화면을 새로고침하세요.')
        for candidate in (endpoint, fallback):
            identity = contract.tier1_cache_identity(candidate, namespace=kwargs['namespace'],
                prompt_version=kwargs['prompt_version'], evidence=kwargs['evidence'])
            path = folder / f"seasonality_{identity['cache_key'][:24]}.json"
            cached = contract._read_generated_cache(path, identity)
            if cached is not None:
                try:
                    if kwargs.get('payload_validator'):
                        kwargs['payload_validator'](cached)
                    return cached
                except ValueError:
                    pass
        state_path = folder / 'season-budget.json'
        today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
        try:
            state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
            if not isinstance(state, dict):
                raise ValueError('invalid budget')
            count = int(state.get('attempts', 0)) if state.get('day') == today else 0
            next_try = float(state.get('next_try', 0))
            if count < 0:
                raise ValueError('invalid count')
        except (OSError, ValueError, TypeError):
            return unavailable('AI_BUDGET_UNREADABLE', 'AI 호출 기록을 확인해야 합니다. 원본 통계는 사용할 수 있습니다.')
        if next_try > time.time():
            return unavailable('AI_RETRY_COOLDOWN', 'AI 응답 실패 후 잠시 대기 중입니다. 5분 뒤 다시 확인하세요.')
        free = contract.tier1_cached_chat_json(root, endpoint, timeout=12, wall_timeout=20, **kwargs)
        if free.get('ok'):
            return free
        limit = max(0, min(6, int(cfg.get('daily_attempt_limit', 6))))
        if count >= limit:
            return unavailable('AI_DAILY_LIMIT', '오늘 시즌 AI 대체 호출 상한에 도달했습니다. 저장된 분석과 원본 통계를 사용하세요.')
        # Reserve before the paid call, including failed requests and server restarts.
        cooldown = max(300, int(cfg.get('failure_cooldown_seconds', 300)))
        state = {'day': today, 'attempts': count+1, 'next_try': time.time()+cooldown}
        contract._write_json_atomic(state_path, state)
        paid = contract.tier1_cached_chat_json(root, fallback, timeout=105, wall_timeout=115, **kwargs)
        if paid.get('ok'):
            state['next_try'] = 0
            contract._write_json_atomic(state_path, state)
        return paid
    except (OSError, ValueError, TypeError):
        return unavailable('AI_POLICY_STORAGE_ERROR', 'AI 호출 설정·기록을 확인해야 합니다. 원본 통계는 사용할 수 있습니다.')
    finally:
        if acquired:
            lock.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
