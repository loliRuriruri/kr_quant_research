from __future__ import annotations

from typing import Any
from urllib.parse import quote

GEOCODE_URL = "https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode"
STATIC_URL = "https://naveropenapi.apigw.ntruss.com/map-static/v2/raster"


def map_headers(client_id: str, client_secret: str) -> dict[str, str]:
    return {
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret,
        "Accept": "application/json",
    }


def naver_map_search_url(address: str) -> str:
    return "https://map.naver.com/p/search/" + quote(address)


def geocode(client_id: str, client_secret: str, address: str, timeout: int = 12) -> dict[str, Any] | None:
    import requests

    if not client_id or not client_secret or not address:
        return None
    resp = requests.get(
        GEOCODE_URL,
        headers=map_headers(client_id, client_secret),
        params={"query": address},
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"네이버 지도 HTTP {resp.status_code}: {resp.text[:160]}")
    payload = resp.json()
    addrs = payload.get("addresses") or []
    if not addrs:
        return None
    hit = addrs[0]
    return {
        "road": hit.get("roadAddress") or "",
        "jibun": hit.get("jibunAddress") or "",
        "lng": hit.get("x"),
        "lat": hit.get("y"),
    }


def fetch_static_map(
    client_id: str,
    client_secret: str,
    lat: str,
    lng: str,
    *,
    width: int = 560,
    height: int = 220,
    level: int = 14,
    timeout: int = 12,
) -> bytes:
    import requests

    resp = requests.get(
        STATIC_URL,
        headers=map_headers(client_id, client_secret),
        params={
            "w": width,
            "h": height,
            "center": f"{lng},{lat}",
            "level": level,
            "markers": f"type:d|size:mid|pos:{lng} {lat}",
        },
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"네이버 정적지도 HTTP {resp.status_code}: {resp.text[:160]}")
    return resp.content
