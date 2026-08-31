from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from kr_quant.hashing import hash_config_files


def find_project_root(start: Path | None = None) -> Path:
    env_home = os.environ.get("KR_QUANT_HOME") or os.environ.get("STOCK_SCREENER_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / "config" / "quant_v1.yaml").exists():
            return candidate
    return cur


@dataclass(frozen=True)
class Settings:
    root: Path
    config: dict[str, Any]
    universe_rules: dict[str, Any]
    risk_rules: dict[str, Any]
    account_map: dict[str, Any]
    research: dict[str, Any]
    config_hash: str
    opendart_api_key: str | None
    krx_api_key: str | None
    xai_api_key: str | None
    deepseek_api_key: str | None
    openrouter_api_key: str | None
    llm_provider: str
    llm_model: str | None
    xai_base_url: str
    custom_llm_base_url: str | None
    custom_llm_api_key: str | None
    kis_app_key: str | None
    kis_app_secret: str | None
    kis_base_url: str
    naver_client_id: str | None
    naver_client_secret: str | None
    naver_map_client_id: str | None
    naver_map_client_secret: str | None
    toss_client_id: str | None
    toss_client_secret: str | None
    fred_api_key: str | None
    bok_ecos_api_key: str | None
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    tavily_api_key: str | None
    kiwoom_app_key: str | None
    kiwoom_secret_key: str | None
    opendart_sleep_sec: float
    sec_user_agent: str

    @property
    def model_id(self) -> str:
        return str(self.config["model"]["id"])

    @property
    def model_version(self) -> str:
        return str(self.config["model"]["version"])

    @property
    def timezone(self) -> str:
        return str(self.config["model"]["timezone"])

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def staged_dir(self) -> Path:
        return self.data_dir / "staged"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def output_dir(self) -> Path:
        return self.data_dir / "output"

    @property
    def db_path(self) -> Path:
        return self.root / "db" / "screener.duckdb"

    @property
    def log_dir(self) -> Path:
        return self.root / "logs"

    @property
    def status_csv(self) -> Path:
        rel = self.config.get("status_feed", {}).get("path", "data/raw/status/krx_status.csv")
        p = Path(rel)
        return p if p.is_absolute() else self.root / p


def _normalize_llm_provider(raw: str | None) -> str:
    from kr_quant.research.providers import normalize_provider

    return normalize_provider(raw)


def _load_yaml(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".csv":
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def load_settings(root: Path | None = None) -> Settings:
    project = find_project_root(root)
    load_dotenv(project / ".env")
    cfg_dir = project / "config"
    quant_path = cfg_dir / "quant_v1.yaml"
    universe_path = cfg_dir / "universe_rules.yaml"
    risk_path = cfg_dir / "risk_rules.yaml"
    account_path = cfg_dir / "account_map_ifrs.yaml"
    research_path = cfg_dir / "research_v1.yaml"
    for required in (quant_path, universe_path, risk_path, account_path):
        if not required.exists():
            raise FileNotFoundError(f"missing config: {required}")

    config_hash = hash_config_files(
        [quant_path, universe_path, risk_path, account_path, cfg_dir / "sector_map_ksic.csv"]
    )
    return Settings(
        root=project,
        config=_load_yaml(quant_path),
        universe_rules=_load_yaml(universe_path),
        risk_rules=_load_yaml(risk_path),
        account_map=_load_yaml(account_path),
        research=_load_yaml(research_path) if research_path.exists() else {},
        config_hash=config_hash,
        opendart_api_key=os.environ.get("OPENDART_API_KEY") or None,
        krx_api_key=os.environ.get("KRX_API_KEY") or None,
        xai_api_key=os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY") or None,
        deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY") or None,
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY") or None,
        llm_provider=_normalize_llm_provider(os.environ.get("LLM_PROVIDER")),
        llm_model=os.environ.get("LLM_MODEL") or None,
        xai_base_url=os.environ.get("XAI_BASE_URL") or "https://api.x.ai/v1",
        custom_llm_base_url=os.environ.get("CUSTOM_LLM_BASE_URL") or None,
        custom_llm_api_key=os.environ.get("CUSTOM_LLM_API_KEY") or None,
        kis_app_key=os.environ.get("KIS_APP_KEY") or None,
        kis_app_secret=os.environ.get("KIS_APP_SECRET") or None,
        kis_base_url=os.environ.get("KIS_BASE_URL") or "https://openapi.koreainvestment.com:9443",
        naver_client_id=os.environ.get("NAVER_CLIENT_ID") or None,
        naver_client_secret=os.environ.get("NAVER_CLIENT_SECRET") or None,
        naver_map_client_id=os.environ.get("NAVER_MAP_CLIENT_ID") or None,
        naver_map_client_secret=os.environ.get("NAVER_MAP_CLIENT_SECRET") or None,
        toss_client_id=os.environ.get("TOSS_CLIENT_ID") or os.environ.get("TOSS_API_KEY") or None,
        toss_client_secret=os.environ.get("TOSS_CLIENT_SECRET") or os.environ.get("TOSS_SECRET_KEY") or None,
        fred_api_key=(os.environ.get("FRED_API_KEY") or "").strip().lower() or None,
        bok_ecos_api_key=os.environ.get("BOK_ECOS_API_KEY") or os.environ.get("KSKILL_BOK_ECOS_API_KEY") or None,
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN") or None,
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID") or None,
        tavily_api_key=os.environ.get("TAVILY_API_KEY") or None,
        kiwoom_app_key=os.environ.get("KIWOOM_APP_KEY") or None,
        kiwoom_secret_key=os.environ.get("KIWOOM_SECRET_KEY") or None,
        opendart_sleep_sec=float(os.environ.get("OPENDART_SLEEP_SEC", "0.15")),
        sec_user_agent=(os.environ.get("SEC_USER_AGENT") or "KR Quant Research a4jud@gmail.com").strip(),
    )
