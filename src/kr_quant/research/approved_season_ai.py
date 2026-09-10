"""Bounded menu-briefing cascade: routine → routine-paid → analysis → analysis-pro."""
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


def _usable(endpoint):
    return (
        endpoint is not None
        and getattr(endpoint, 'configured', False)
        and getattr(endpoint, 'provider', '') != 'tier1_unavailable'
    )


def _endpoint_list(*items):
    seen = []
    keys = set()
    for item in items:
        if item is None:
            continue
        key = (getattr(item, 'provider', None), getattr(item, 'model', None))
        if key in keys:
            continue
        keys.add(key)
        seen.append(item)
    return seen


def _live_ok(result):
    return bool(result) and result.get('ok') and result.get('status') == 'GENERATED'


def _with_reuse(cached, **flags):
    if cached is None:
        return None
    result = dict(cached)
    meta = dict(result.get('cache') or {})
    meta['hit'] = True
    meta.update(flags)
    result['cache'] = meta
    return result


def _evidence_tickers(evidence):
    if not isinstance(evidence, dict):
        return ()
    codes = []
    for row in evidence.get('candidates') or []:
        if isinstance(row, dict) and row.get('ticker'):
            codes.append(''.join(ch for ch in str(row.get('ticker')) if ch.isdigit()).zfill(6)[-6:])
    if codes:
        return tuple(codes)
    for item in evidence.get('missing') or []:
        head = str(item).split(':', 1)[0].strip()
        digits = ''.join(ch for ch in head if ch.isdigit())
        if len(digits) >= 6:
            codes.append(digits[-6:].zfill(6))
    return tuple(codes)


def _validate_cached(cached, validator):
    if cached is None:
        return None
    try:
        if validator:
            validator(cached)
        return cached
    except ValueError:
        return None


def extra_cascade_endpoints(root):
    cfg = policy(root)
    routine = None
    analysis_pro = None
    if cfg.get('routine_paid_enabled') is not True and cfg.get('analysis_pro_enabled') is not True:
        return None, None
    try:
        from kr_quant.settings import load_settings
        from kr_quant.research.providers import (
            resolve_tier1_routine_paid_endpoint,
            resolve_tier1_analysis_pro_endpoint,
        )
        settings = load_settings()
        if cfg.get('routine_paid_enabled') is True:
            candidate = resolve_tier1_routine_paid_endpoint(settings)
            if _usable(candidate):
                routine = candidate
        if cfg.get('analysis_pro_enabled') is True:
            candidate = resolve_tier1_analysis_pro_endpoint(settings)
            if _usable(candidate):
                analysis_pro = candidate
    except Exception:
        return routine, analysis_pro
    return routine, analysis_pro


def exact_generated_cache(folder, endpoints, **kwargs):
    from kr_quant.research import tier1_contract as contract
    validator = kwargs.get('payload_validator')
    for candidate in endpoints:
        if candidate is None:
            continue
        identity = contract.tier1_cache_identity(
            candidate, namespace=kwargs['namespace'],
            prompt_version=kwargs['prompt_version'], evidence=kwargs['evidence'])
        path = folder / f"{contract._cache_namespace(kwargs['namespace'])}_{identity['cache_key'][:24]}.json"
        cached = _validate_cached(contract._read_generated_cache(path, identity), validator)
        if cached is not None:
            return cached
    return None


def _scan_generated(folder, **kwargs):
    from kr_quant.research import tier1_contract as contract
    namespace = kwargs.get('namespace') or ''
    prompt_version = kwargs.get('prompt_version')
    as_of = kwargs.get('as_of')
    if not namespace or not prompt_version:
        return None, None
    validator = kwargs.get('payload_validator')
    ns = contract._cache_namespace(namespace)
    want = _evidence_tickers(kwargs.get('evidence') or {})
    if not want:
        want = _evidence_tickers({'missing': kwargs.get('missing') or []})
    matched = None
    matched_mtime = -1.0
    any_card = None
    any_mtime = -1.0
    for path in folder.glob(f'{ns}_*.json'):
        try:
            cached = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(cached, dict) or cached.get('status') != 'GENERATED':
            continue
        if cached.get('prompt_version') != prompt_version:
            continue
        cached_asof = (cached.get('evidence') or {}).get('as_of')
        if as_of and cached_asof and str(cached_asof)[:10] != str(as_of)[:10]:
            continue
        cached = _validate_cached(cached, validator)
        if cached is None:
            continue
        mtime = path.stat().st_mtime
        if mtime > any_mtime:
            any_card, any_mtime = cached, mtime
        have = _evidence_tickers(cached.get('evidence') or {})
        if want and have != want:
            continue
        if mtime > matched_mtime:
            matched, matched_mtime = cached, mtime
    return matched, any_card


def compatible_generated_cache(folder, **kwargs):
    """Reuse a same-day, same-prompt GENERATED card when the exact hash moved.

    Ticker match is preferred when the evidence names tickers; otherwise
    namespace + prompt + as_of is enough so menus without candidates still reuse.
    """
    matched, any_card = _scan_generated(folder, **kwargs)
    want = _evidence_tickers(kwargs.get('evidence') or {})
    if not want:
        want = _evidence_tickers({'missing': kwargs.get('missing') or []})
    chosen = matched if matched is not None else (any_card if not want else None)
    return _with_reuse(chosen, compatible_reuse=True)


def last_generated_cache(folder, **kwargs):
    """Last same-day GENERATED card for this menu so the pane does not blank."""
    matched, any_card = _scan_generated(folder, **kwargs)
    return _with_reuse(matched or any_card, last_good_reuse=True)


def approved_briefing(root, endpoint, fallback, **kwargs):
    from kr_quant.research import tier1_contract as contract
    cfg = policy(root)
    routine = kwargs.pop('routine_endpoint', None)
    analysis_pro = kwargs.pop('analysis_pro_endpoint', None)
    extra_routine, extra_pro = extra_cascade_endpoints(root)
    if routine is None:
        routine = extra_routine
    if analysis_pro is None:
        analysis_pro = extra_pro
    cascade_on = (
        cfg.get('grok_fallback_enabled') is True
        or cfg.get('routine_paid_enabled') is True
        or _usable(routine)
        or _usable(analysis_pro)
        or _usable(fallback)
    )
    if not cascade_on:
        return contract.tier1_cached_chat_json(root, endpoint, allow_fallback=False, **kwargs)

    def unavailable(code, message):
        target = fallback or analysis_pro or routine or endpoint
        return contract.tier1_unavailable(target, code=code, message=message,
            **{key: kwargs[key] for key in ('prompt_version', 'as_of', 'sources', 'evidence_count', 'missing')})

    analysis_grok = fallback if (
        cfg.get('grok_fallback_enabled') is True
        and _usable(fallback)
    ) else None
    hops = _endpoint_list(endpoint, routine, analysis_grok, analysis_pro)
    folder = Path(root) / 'data/cache/tier1_briefings'
    folder.mkdir(parents=True, exist_ok=True)
    cached = exact_generated_cache(folder, hops, **kwargs)
    if cached is not None:
        return cached
    cached = compatible_generated_cache(folder, **kwargs)
    if cached is not None:
        return cached
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
            held = last_generated_cache(folder, **kwargs) or compatible_generated_cache(folder, **kwargs)
            if held is not None:
                return _with_reuse(held, pending_reuse=True)
            return unavailable('AI_REQUEST_PENDING', 'AI 분석이 이미 진행 중입니다. 잠시 후 화면을 새로고침하세요.')
        cached = exact_generated_cache(folder, hops, **kwargs) or compatible_generated_cache(folder, **kwargs)
        if cached is not None:
            return cached
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
        limit = max(0, min(48, int(cfg.get('daily_attempt_limit', 24))))
        cooldown = max(60, int(cfg.get('failure_cooldown_seconds', 90)))

        def try_live(ep, timeout, wall):
            if not _usable(ep):
                return None
            return contract.tier1_cached_chat_json(
                root, ep, timeout=timeout, wall_timeout=wall, allow_fallback=False, **kwargs)

        last_fail = None
        free = try_live(endpoint, 8, 12)
        if _live_ok(free):
            return free
        last_fail = free or last_fail
        flash = try_live(routine, 20, 28)
        if _live_ok(flash):
            return flash
        last_fail = flash or last_fail

        analysis_blocked = None
        if next_try > time.time():
            analysis_blocked = ('AI_RETRY_COOLDOWN', '분석 모델 실패 후 잠시 대기 중입니다. 일상 경로와 저장된 해설은 계속 사용합니다.')
        elif count >= limit:
            analysis_blocked = ('AI_DAILY_LIMIT', '오늘 분석 모델 호출 상한에 도달했습니다. 일상 경로와 저장된 해설을 사용합니다.')
        else:
            state = {'day': today, 'attempts': count + 1, 'next_try': time.time() + cooldown}
            contract._write_json_atomic(state_path, state)
            grok = try_live(analysis_grok, 105, 115)
            if _live_ok(grok):
                state['next_try'] = 0
                contract._write_json_atomic(state_path, state)
                return grok
            last_fail = grok or last_fail
            pro = try_live(analysis_pro, 90, 100)
            if _live_ok(pro):
                state['next_try'] = 0
                contract._write_json_atomic(state_path, state)
                return pro
            last_fail = pro or last_fail

        held = last_generated_cache(folder, **kwargs)
        if held is not None:
            return held
        if analysis_blocked:
            return unavailable(*analysis_blocked)
        return last_fail or unavailable('TIER1_GENERATION_FAILED', 'AI 설명을 생성하지 못했습니다. 원본 계산 결과는 그대로 사용할 수 있습니다.')
    except (OSError, ValueError, TypeError):
        held = last_generated_cache(folder, **kwargs)
        if held is not None:
            return held
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
