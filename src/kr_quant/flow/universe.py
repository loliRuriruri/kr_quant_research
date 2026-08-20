from __future__ import annotations

from typing import Any

import pandas as pd

from kr_quant.settings import Settings

TOSS_RANK_SPECS = (
    ("TOP_GAINERS", "1d"),
    ("TOP_LOSERS", "1d"),
    ("MARKET_TRADING_AMOUNT", "realtime"),
    ("TOSS_SECURITIES_TRADING_AMOUNT", "1d"),
)


def _code(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits.zfill(6) if digits else ""


# KRX stock master often omits ETFs; Toss rankings still include them by code.
KNOWN_ETF: dict[str, str] = {
    "069500": "KODEX 200",
    "069660": "KIWOOM 200",
    "102110": "TIGER 200",
    "105190": "ACE 200",
    "108590": "TREX 200",
    "114800": "KODEX 인버스",
    "122630": "KODEX 레버리지",
    "123310": "TIGER 인버스",
    "123320": "TIGER 레버리지",
    "152870": "ACE 레버리지",
    "229200": "KODEX 코스닥150",
    "232080": "TIGER 코스닥150",
    "233740": "KODEX 코스닥150레버리지",
    "251340": "KODEX 코스닥150선물인버스",
    "252670": "KODEX 200선물인버스2X",
    "252710": "TIGER 200선물인버스2X",
    "253530": "PLUS 200선물인버스2X",
    "267770": "TIGER 200선물레버리지",
    "278530": "KODEX 200TR",
    "310970": "TIGER MSCI Korea TR",
    "379800": "KODEX 미국S&P500",
    "379810": "KODEX 미국나스닥100",
    "381180": "TIGER 미국필라델피아반도체나스닥",
    "453810": "KODEX 미국S&P500TR",
    "091160": "KODEX 반도체",
    "091170": "KODEX 은행",
    "091180": "KODEX 자동차",
    "140700": "KODEX 보험",
    "157490": "TIGER 소프트웨어",
    "305540": "TIGER 2차전지테마",
    "305720": "KODEX 2차전지산업",
    "364690": "KODEX 혁신기술",
    "371460": "TIGER 차이나전기차SOLACTIVE",
    "395160": "KODEX 인터넷",
    "442260": "TIGER 미국S&P500",
    "448290": "KODEX 미국나스닥100레버리지",
    "455850": "SOL 미국S&P500",
}


def local_name(code: str) -> str | None:
    key = _code(code)
    return KNOWN_ETF.get(key)


def resolve_names(settings: Settings, codes: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    """Fill ETF/stock names missing from KRX equity master. Returns names, security_types."""
    names: dict[str, str] = {}
    types: dict[str, str] = {}
    uniq = [_code(c) for c in codes if _code(c)]
    uniq = list(dict.fromkeys(uniq))
    for code in uniq:
        known = local_name(code)
        if known:
            names[code] = known
            types[code] = "ETF"
    missing = [c for c in uniq if c not in names]
    if missing and settings.toss_client_id and settings.toss_client_secret:
        from kr_quant.ingest.tossinvest import get_stocks

        for i in range(0, len(missing), 20):
            chunk = missing[i : i + 20]
            try:
                stocks = get_stocks(settings.toss_client_id, settings.toss_client_secret, chunk)
            except Exception:  # noqa: BLE001
                stocks = []
            for item in stocks:
                if not isinstance(item, dict):
                    continue
                code = _code(item.get("symbol"))
                if item.get("name"):
                    names[code] = str(item["name"])
                if item.get("securityType"):
                    types[code] = str(item["securityType"])
    return names, types


def quant_top_map(settings: Settings) -> dict[str, str]:
    names: dict[str, str] = {}
    path = settings.output_dir / "latest_top100.csv"
    if not path.exists():
        path = settings.output_dir / "latest_top20.csv"
    if not path.exists():
        return names
    df = pd.read_csv(path, dtype={"ticker": str})
    for rec in df.to_dict("records"):
        code = _code(rec.get("ticker"))
        if code:
            names[code] = str(rec.get("company") or code)
    return names


def quant_rank_map(settings: Settings) -> dict[str, int]:
    ranks: dict[str, int] = {}
    path = settings.output_dir / "latest_all_stocks.parquet"
    if not path.exists():
        return ranks
    df = pd.read_parquet(path)
    keep = [c for c in ("ticker", "quant_rank", "quant_rank_raw") if c in df.columns]
    if "ticker" not in keep:
        return ranks
    for rec in df[keep].to_dict("records"):
        code = _code(rec.get("ticker"))
        if not code:
            continue
        rank = rec.get("quant_rank")
        if rank is None or (isinstance(rank, float) and pd.isna(rank)):
            rank = rec.get("quant_rank_raw")
        try:
            if rank is not None and not (isinstance(rank, float) and pd.isna(rank)):
                ranks[code] = int(rank)
        except (TypeError, ValueError):
            continue
    return ranks


def liquid_map(settings: Settings, n: int = 60) -> dict[str, str]:
    names: dict[str, str] = {}
    path = None
    for folder in (settings.staged_dir / "live", settings.staged_dir / "demo"):
        p = folder / "prices.parquet"
        if p.exists():
            path = p
            break
    if path is None:
        return names
    df = pd.read_parquet(path, columns=["ticker", "company", "trade_date", "trading_value"])
    if df.empty:
        return names
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    last = df["trade_date"].max()
    day = df[df["trade_date"] == last].copy()
    day["trading_value"] = pd.to_numeric(day["trading_value"], errors="coerce").fillna(0)
    day = day.sort_values("trading_value", ascending=False).head(max(1, n))
    for rec in day.to_dict("records"):
        code = _code(rec.get("ticker"))
        if code:
            names[code] = str(rec.get("company") or code)
    return names


def toss_mover_map(settings: Settings, per: int = 25) -> dict[str, str]:
    names: dict[str, str] = {}
    if not settings.toss_client_id or not settings.toss_client_secret:
        return names
    from kr_quant.ingest.tossinvest import get_rankings, normalize_ranking_row

    for rtype, duration in TOSS_RANK_SPECS:
        try:
            data = get_rankings(
                settings.toss_client_id,
                settings.toss_client_secret,
                ranking_type=rtype,
                duration=duration,
                count=per,
            )
        except Exception:  # noqa: BLE001
            continue
        raw = data.get("rankings") if isinstance(data, dict) else data
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            row = normalize_ranking_row(item)
            code = _code(row.get("code") or row.get("symbol"))
            if code:
                names[code] = str(row.get("name") or code)
    return names


def watch_map(settings: Settings) -> dict[str, str]:
    names: dict[str, str] = {}
    try:
        from kr_quant.context.watchlist import load_watchlist

        for rec in load_watchlist(settings.root):
            code = _code(rec.get("ticker"))
            if code:
                names[code] = str(rec.get("company") or code)
    except Exception:  # noqa: BLE001
        pass
    return names


def build_universe(
    settings: Settings,
    extra: list[str] | None = None,
    limit: int = 160,
) -> tuple[list[tuple[str, str]], dict[str, list[str]]]:
    names: dict[str, str] = {}
    sources: dict[str, list[str]] = {}

    def add(mapping: dict[str, str], src: str) -> None:
        for code, company in mapping.items():
            key = _code(code)
            if not key.isdigit():
                continue
            label = str(company or "").strip()
            if label and label != key:
                names[key] = label
            else:
                names.setdefault(key, key)
            bucket = sources.setdefault(key, [])
            if src not in bucket:
                bucket.append(src)

    add(toss_mover_map(settings), "toss")
    add(liquid_map(settings), "liquid")
    add(watch_map(settings), "watch")
    extra_map = {str(c).zfill(6): str(c).zfill(6) for c in (extra or [])}
    add(extra_map, "extra")
    add(quant_top_map(settings), "quant")
    filled, _types = resolve_names(settings, list(names))
    for code, label in filled.items():
        if label and label != code:
            names[code] = label

    ordered: list[str] = []
    seen: set[str] = set()
    for group in ("toss", "liquid", "watch", "extra", "quant"):
        for code, srcs in sources.items():
            if group in srcs and code not in seen:
                seen.add(code)
                ordered.append(code)
            if len(ordered) >= limit:
                break
        if len(ordered) >= limit:
            break
    meta = {code: sources.get(code, []) for code in ordered}
    return [(code, names.get(code, code)) for code in ordered], meta
