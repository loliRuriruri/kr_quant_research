"""Bounded, copy-isolated TTL cache with per-key single-flight execution."""
from __future__ import annotations

import copy
import functools
import hashlib
import inspect
import pickle
import threading
import time
from collections import OrderedDict
from typing import Any, Callable

_CACHE_LOCK = threading.RLock()
_CACHE_STORE: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_CACHE_EPOCH = 0
_MAX_ENTRIES = 256
_FLIGHTS = [threading.RLock() for _ in range(64)]


def ttl_cache(seconds: int = 60, bypass_kwarg: str | None = "refresh", key_extra: Callable | None = None) -> Callable:
    def decorator(fn: Callable) -> Callable:
        signature = inspect.signature(fn)
        namespace = f"{fn.__name__}:{fn.__module__}.{fn.__qualname__}:{id(fn)}"

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            refresh = bool(bound.arguments.pop(bypass_kwarg, False)) if bypass_kwarg else False
            try:
                key = _make_key(namespace, (key_extra() if key_extra else None,), dict(bound.arguments))
            except (TypeError, AttributeError, pickle.PicklingError):
                return fn(*args, **kwargs)
            with _FLIGHTS[hash(key) % len(_FLIGHTS)]:
                with _CACHE_LOCK:
                    epoch = _CACHE_EPOCH
                    cached = _CACHE_STORE.get(key)
                    if not refresh and cached and time.monotonic() < cached[0]:
                        _CACHE_STORE.move_to_end(key)
                        return copy.deepcopy(cached[1])
                result = fn(*args, **kwargs)
                if not (isinstance(result, dict) and result.get("ok") is False):
                    isolated = copy.deepcopy(result)
                    with _CACHE_LOCK:
                        if epoch == _CACHE_EPOCH:
                            now = time.monotonic()
                            for expired in [k for k, (until, _) in _CACHE_STORE.items() if until <= now]:
                                del _CACHE_STORE[expired]
                            _CACHE_STORE[key] = (now + seconds, isolated)
                            _CACHE_STORE.move_to_end(key)
                            while len(_CACHE_STORE) > _MAX_ENTRIES:
                                _CACHE_STORE.popitem(last=False)
                return result
        return wrapper
    return decorator


def _make_key(fn_name: str, args: tuple, kwargs: dict) -> str:
    digest = hashlib.sha256(pickle.dumps((args, sorted(kwargs.items())))).hexdigest()
    return f"{fn_name}:{digest}"


def invalidate_cache(fn_prefix: str | None = None) -> None:
    global _CACHE_EPOCH
    with _CACHE_LOCK:
        _CACHE_EPOCH += 1
        for key in list(_CACHE_STORE):
            if not fn_prefix or key.startswith(fn_prefix):
                del _CACHE_STORE[key]
