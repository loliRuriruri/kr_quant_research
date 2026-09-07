"""In-memory thread-safe TTL cache for high-latency web API endpoints."""

from __future__ import annotations

import functools
import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

_CACHE_LOCK = threading.Lock()
_CACHE_STORE: dict[str, tuple[float, Any]] = {}


def ttl_cache(seconds: int = 60, bypass_kwarg: str | None = "refresh") -> Callable:
    """Decorator to cache function return value in memory for `seconds` seconds.

    If bypass_kwarg is provided and present in kwargs as True, cache is bypassed and refreshed.
    """

    def decorator(fn: Callable) -> Callable:
        fn_name = fn.__name__

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check bypass
            if bypass_kwarg and kwargs.get(bypass_kwarg):
                res = fn(*args, **kwargs)
                # Update cache
                key = _make_key(fn_name, args, kwargs)
                with _CACHE_LOCK:
                    _CACHE_STORE[key] = (time.time() + seconds, res)
                return res

            key = _make_key(fn_name, args, kwargs)
            now = time.time()

            with _CACHE_LOCK:
                if key in _CACHE_STORE:
                    expires_at, val = _CACHE_STORE[key]
                    if now < expires_at:
                        return val
                    # Expired
                    del _CACHE_STORE[key]

            # Execute function
            res = fn(*args, **kwargs)

            with _CACHE_LOCK:
                _CACHE_STORE[key] = (time.time() + seconds, res)

            return res

        return wrapper

    return decorator


def _make_key(fn_name: str, args: tuple, kwargs: dict) -> str:
    # Filter out non-hashable or volatile objects like Settings if present
    clean_args = [a for a in args if not hasattr(a, "__dict__") and not isinstance(a, (dict, list, set))]
    clean_kwargs = {k: v for k, v in kwargs.items() if not hasattr(v, "__dict__") and not isinstance(v, (dict, list, set))}
    return f"{fn_name}:{tuple(clean_args)}:{sorted(clean_kwargs.items())}"


def invalidate_cache(fn_prefix: str | None = None) -> None:
    """Clear cached entries matching prefix, or all entries if None."""
    with _CACHE_LOCK:
        if not fn_prefix:
            _CACHE_STORE.clear()
            return
        keys_to_del = [k for k in _CACHE_STORE if k.startswith(fn_prefix)]
        for k in keys_to_del:
            del _CACHE_STORE[k]
