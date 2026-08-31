# -*- coding: utf-8 -*-
"""Bounded HTTP retries for official adapters. Do not retry most 4xx."""
from __future__ import annotations

import time
from typing import Any

import requests

RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


def request_with_retry(
    method: str,
    url: str,
    *,
    retries: int = 2,
    backoff_sec: float = 0.4,
    timeout: int = 30,
    **kwargs: Any,
) -> requests.Response:
    attempts = max(1, int(retries) + 1)
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code in RETRY_STATUS and attempt < attempts - 1:
                time.sleep(backoff_sec * (attempt + 1))
                continue
            return resp
        except (requests.Timeout, requests.ConnectionError) as exc:
            last = exc
            if attempt >= attempts - 1:
                raise
            time.sleep(backoff_sec * (attempt + 1))
    if last:
        raise last
    raise RuntimeError("HTTP retry exhausted")
