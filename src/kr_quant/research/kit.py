from __future__ import annotations

from pathlib import Path

from kr_quant.settings import find_project_root

PROMPT_VERSION = "jonnajokun_ver4.0.0"

CORE_FILES = (
    "ADAPTER.md",
    "00_PROJECT_INSTRUCTIONS_VER4.0.0.md",
)

MODULE_FILES = (
    "14_OUTPUT_TEMPLATE_DEEP_READABLE.md",
    "15_INTERNAL_QUALITY_GATE.md",
    "03_THESIS_BUSINESS_MODEL_MOAT.md",
    "04_FINANCIAL_FORENSICS_EARNINGS_QUALITY.md",
    "07_VALUATION_REVERSE_PRICE_MAP.md",
    "18_EVIDENCE_CONTRADICTION_DECISION_ENGINE.md",
    "05_INDUSTRY_CYCLE_COMPETITION.md",
    "11_NEW_HOLDER_TRADER_STRATEGY.md",
    "12_RISK_PORTFOLIO_POSITION.md",
    "20_AUTO_DEPTH_SECTION_VERDICT_MATRIX.md",
)

REQUIRED_HEADINGS = (
    "45초 총평",
    "최신 뉴스·공시·이벤트",
    "재무·최근 실적·이익의 질",
    "밸류에이션",
    "성장성·경제적 해자·업계",
    "정책·테마·거시",
    "기술적 위치·거래량·수급·유사국면",
    "핵심 리스크",
    "목표가·Price & Action Map",
    "사용자별 전략",
    "Final Action Playbook",
)


def kit_dir(root: Path | None = None) -> Path:
    return find_project_root(root) / "config" / "research_kit"


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def compile_system_prompt(root: Path | None = None) -> str:
    base = kit_dir(root)
    chunks: list[str] = []
    for name in CORE_FILES:
        text = _read(base / name)
        if text:
            chunks.append(text)
    modules = base / "modules"
    for name in MODULE_FILES:
        text = _read(modules / name)
        if text:
            chunks.append(f"\n\n===== {name} =====\n{text}")
    if not chunks:
        raise FileNotFoundError(f"research kit missing: {base}")
    return "\n\n".join(chunks)
