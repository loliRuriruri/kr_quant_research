from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from kr_quant.logging_config import setup_logging
from kr_quant.settings import load_settings

app = typer.Typer(no_args_is_help=True, add_completion=False, help="KR Quant Research")
console = Console()


def _settings(root: Optional[Path] = None):
    return load_settings(root)


@app.command()
def doctor(root: Optional[Path] = typer.Option(None, help="프로젝트 루트")) -> None:
    """환경 변수와 설정 파일을 점검한다."""
    s = _settings(root)
    setup_logging(s.log_dir)
    table = Table(title="Quant Screener doctor")
    table.add_column("항목")
    table.add_column("상태")
    table.add_row("project_root", str(s.root))
    table.add_row("model", f"{s.model_id} {s.model_version}")
    table.add_row("config_hash", s.config_hash[:16] + "…")
    table.add_row("OPENDART_API_KEY", "설정됨" if s.opendart_api_key else "없음")
    table.add_row("KRX_API_KEY", "설정됨" if s.krx_api_key else "없음")
    table.add_row("LLM_PROVIDER", s.llm_provider or "xai")
    table.add_row("XAI_API_KEY (Grok)", "설정됨" if s.xai_api_key else "없음")
    table.add_row("DEEPSEEK_API_KEY", "설정됨" if s.deepseek_api_key else "없음")
    table.add_row("OPENROUTER_API_KEY", "설정됨" if s.openrouter_api_key else "없음")
    table.add_row("KIS_APP_KEY", "설정됨" if s.kis_app_key else "없음")
    table.add_row("NAVER_CLIENT_ID", "설정됨" if s.naver_client_id else "없음")
    table.add_row("NAVER_MAP_CLIENT_ID", "설정됨" if s.naver_map_client_id else "없음")
    table.add_row("TOSS_CLIENT_ID", "설정됨" if s.toss_client_id else "없음")
    table.add_row("FRED_API_KEY", "설정됨" if s.fred_api_key else "없음")
    table.add_row("BOK_ECOS_API_KEY", "설정됨" if s.bok_ecos_api_key else "sample(공개)")
    table.add_row("TELEGRAM_BOT_TOKEN", "설정됨" if s.telegram_bot_token else "없음")
    table.add_row("TELEGRAM_CHAT_ID", "설정됨" if s.telegram_chat_id else "없음")
    table.add_row("status_csv", str(s.status_csv) + (" (존재)" if s.status_csv.exists() else " (없음 → partial)"))
    table.add_row(
        "momentum",
        "활성(상장주식수 보정)" if s.config["factors"]["momentum"].get("enabled") else "비활성",
    )
    console.print(table)
    console.print(
        "실데이터 수집: OpenDART는 https://opendart.fss.or.kr 에서 인증키를 받고 "
        "KRX는 https://openapi.krx.co.kr 에서 인증키와 일별매매정보 서비스 이용신청이 필요합니다."
    )


@app.command()
def demo(
    as_of: str = typer.Option("2024-12-30", help="기준일 YYYY-MM-DD"),
    root: Optional[Path] = typer.Option(None),
) -> None:
    """합성 픽스처로 전체 파이프라인을 실행한다. API 키가 필요 없다."""
    s = _settings(root)
    setup_logging(s.log_dir, "demo")
    from kr_quant.orchestration.run import run_demo

    result = run_demo(s, date.fromisoformat(as_of))
    _print_result(result)


@app.command()
def screen(
    as_of: str = typer.Argument(..., help="기준일 YYYY-MM-DD"),
    source: str = typer.Option("staged", help="staged|demo|live"),
    staged_dir: Optional[Path] = typer.Option(None, help="prices/facts/master parquet 폴더"),
    root: Optional[Path] = typer.Option(None),
) -> None:
    """PIT 스냅샷에서 Quant Score와 TOP100/TOP20을 계산한다."""
    s = _settings(root)
    d = date.fromisoformat(as_of)
    setup_logging(s.log_dir, f"screen-{as_of}")
    from kr_quant.orchestration.run import run_demo, run_from_staged

    if source == "demo":
        result = run_demo(s, d)
    else:
        folder = staged_dir or (s.staged_dir / ("live" if source == "live" else "demo"))
        if not (folder / "prices.parquet").exists():
            raise typer.BadParameter(f"prices.parquet 없음: {folder}. 먼저 demo 또는 ingest-krx를 실행하세요.")
        result = run_from_staged(s, d, folder)
    _print_result(result)


@app.command("refresh-prices")
def refresh_prices(
    as_of: str = typer.Option("auto", help="YYYY-MM-DD 또는 auto"),
    lookback_days: int = typer.Option(10, help="비어 있는 최근 거래일만 채움. 이력 확장은 750"),
    root: Optional[Path] = typer.Option(None),
) -> None:
    """KRX 일봉만 갱신한다. OpenDART와 Quant 재계산은 하지 않는다."""
    s = _settings(root)
    setup_logging(s.log_dir, "refresh-prices")
    from kr_quant.web.jobs import job_krx_prices

    if lookback_days > 40:
        from kr_quant.web.jobs import job_krx_history

        result = job_krx_history(as_of, lookback_days)
    else:
        result = job_krx_prices(as_of, lookback_days)
    console.print(result)


@app.command("ingest-krx")
def ingest_krx(
    as_of: str = typer.Argument(..., help="기준일 YYYY-MM-DD"),
    root: Optional[Path] = typer.Option(None),
) -> None:
    """KRX Open API로 당일 시세를 받아 staged/live/prices.parquet에 적재한다."""
    s = _settings(root)
    setup_logging(s.log_dir, f"ingest-krx-{as_of}")
    if not s.krx_api_key:
        raise typer.Exit("KRX_API_KEY가 없습니다. .env.example을 참고하세요.")
    from kr_quant.orchestration.run import ingest_krx_day

    path = ingest_krx_day(s, date.fromisoformat(as_of))
    console.print(f"saved {path}")


@app.command("ingest-dart")
def ingest_dart(
    tickers: str = typer.Option(..., help="쉼표 구분 6자리 종목코드"),
    years: str = typer.Option("2021,2022,2023,2024,2025", help="쉼표 구분 연도"),
    max_corps: Optional[int] = typer.Option(None),
    root: Optional[Path] = typer.Option(None),
) -> None:
    """OpenDART 전체 재무제표를 받아 staged/live/financial_facts.parquet에 적재한다."""
    s = _settings(root)
    setup_logging(s.log_dir, "ingest-dart")
    if not s.opendart_api_key:
        raise typer.Exit("OPENDART_API_KEY가 없습니다. .env.example을 참고하세요.")
    from kr_quant.orchestration.run import ingest_dart_financials

    path = ingest_dart_financials(
        s,
        [t.strip() for t in tickers.split(",") if t.strip()],
        [int(y) for y in years.split(",") if y.strip()],
        max_corps=max_corps,
    )
    console.print(f"saved {path}")


@app.command("live-bootstrap")
def live_bootstrap(
    as_of: str = typer.Option("auto", help="YYYY-MM-DD 또는 auto"),
    lookback_days: int = typer.Option(80, min=20, max=1250),
    max_corps: int = typer.Option(400, min=10, max=3000),
    root: Optional[Path] = typer.Option(None),
) -> None:
    """KRX 시세 + OpenDART 재무를 받아 staged/live 에 적재한다."""
    s = _settings(root)
    setup_logging(s.log_dir, "live-bootstrap")
    if not s.krx_api_key or not s.opendart_api_key:
        raise typer.Exit("KRX_API_KEY와 OPENDART_API_KEY가 모두 필요합니다.")
    from datetime import timedelta

    from kr_quant.ingest.krx import KrxOpenApiAdapter
    from kr_quant.ingest.live import bootstrap_live

    if as_of == "auto":
        adapter = KrxOpenApiAdapter(s.krx_api_key, s.config["ingest"]["krx_base_url"])
        cur = date.today()
        chosen = None
        for _ in range(10):
            if adapter.fetch_daily_maybe(cur, "KOSPI"):
                chosen = cur
                break
            cur -= timedelta(days=1)
        if chosen is None:
            raise typer.Exit("최근 거래일 KRX 시세를 찾지 못했습니다.")
        d = chosen
    else:
        d = date.fromisoformat(as_of)
    console.print(f"bootstrap as_of={d} lookback={lookback_days} max_corps={max_corps}")
    info = bootstrap_live(s, d, lookback_days=lookback_days, max_corps=max_corps)
    console.print(info)


@app.command("live")
def live(
    as_of: str = typer.Option("auto", help="YYYY-MM-DD 또는 auto"),
    lookback_days: int = typer.Option(80, min=20, max=1250),
    max_corps: int = typer.Option(400, min=10, max=3000),
    skip_ingest: bool = typer.Option(False, help="이미 받은 staged/live만 사용"),
    root: Optional[Path] = typer.Option(None),
) -> None:
    """실데이터를 받은 뒤 Quant 스크리닝을 실행한다."""
    s = _settings(root)
    setup_logging(s.log_dir, "live")
    from datetime import timedelta

    from kr_quant.ingest.krx import KrxOpenApiAdapter
    from kr_quant.ingest.live import bootstrap_live
    from kr_quant.orchestration.run import run_from_staged

    if as_of == "auto":
        adapter = KrxOpenApiAdapter(s.krx_api_key or "", s.config["ingest"]["krx_base_url"])
        cur = date.today()
        chosen = None
        for _ in range(10):
            if adapter.fetch_daily_maybe(cur, "KOSPI"):
                chosen = cur
                break
            cur -= timedelta(days=1)
        if chosen is None:
            raise typer.Exit("최근 거래일 KRX 시세를 찾지 못했습니다.")
        d = chosen
    else:
        d = date.fromisoformat(as_of)
    if not skip_ingest:
        if not s.krx_api_key or not s.opendart_api_key:
            raise typer.Exit("KRX_API_KEY와 OPENDART_API_KEY가 모두 필요합니다.")
        console.print(f"ingest as_of={d}")
        console.print(bootstrap_live(s, d, lookback_days=lookback_days, max_corps=max_corps))
    folder = s.staged_dir / "live"
    result = run_from_staged(s, d, folder)
    _print_result(result)


@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8790),
    no_browser: bool = typer.Option(False, help="브라우저를 열지 않음"),
    root: Optional[Path] = typer.Option(None),
) -> None:
    """웹 대시보드를 연다."""
    _settings(root)
    from kr_quant.web.app import serve

    serve(host=host, port=port, open_browser=not no_browser)


@app.command("show-top")
def show_top(
    n: int = typer.Option(20, min=1, max=100),
    root: Optional[Path] = typer.Option(None),
) -> None:
    """latest_top100.csv를 표로 보여준다."""
    s = _settings(root)
    path = s.output_dir / "latest_top20.csv" if n <= 20 else s.output_dir / "latest_top100.csv"
    if not path.exists():
        path = s.output_dir / "latest_top100.csv"
    if not path.exists():
        raise typer.Exit("출력 파일이 없습니다. 먼저 `kr-quant-research demo`를 실행하세요.")
    import pandas as pd

    df = pd.read_csv(path).head(n)
    table = Table(title=str(path.name))
    cols = [
        c
        for c in ["quant_rank", "ticker", "company", "quant_score", "value_score", "quality_score", "growth_score", "risk_penalty", "data_confidence"]
        if c in df.columns
    ]
    for c in cols:
        table.add_column(c)
    for rec in df[cols].to_dict("records"):
        table.add_row(*[str(rec[c]) if rec[c] == rec[c] else "" for c in cols])
    console.print(table)


def _print_result(result: dict) -> None:
    ctx = result["context"]
    top20 = result["top20"]
    console.print(f"[bold]{ctx.run_id}[/bold]  status={ctx.status}  result={ctx.result_hash[:12]}")
    if ctx.warnings:
        console.print("warnings:", ", ".join(ctx.warnings))
    if top20 is None or top20.empty:
        console.print("TOP20 적격 종목이 없습니다. data_quality_report.json을 확인하세요.")
        return
    table = Table(title="TOP20")
    for c in ["quant_rank", "ticker", "company", "quant_score", "risk_penalty", "data_confidence"]:
        if c in top20.columns:
            table.add_column(c)
    show = top20.head(20)
    for rec in show.to_dict("records"):
        table.add_row(
            str(int(rec["quant_rank"])) if rec.get("quant_rank") == rec.get("quant_rank") else "",
            str(rec.get("ticker", "")),
            str(rec.get("company", "")),
            f"{rec.get('quant_score', 0):.2f}",
            f"{rec.get('risk_penalty', 0):.1f}",
            f"{rec.get('data_confidence', 0):.1f}",
        )
    console.print(table)
    console.print(f"output: {result['manifest']['output_dir']}")


if __name__ == "__main__":
    app()
