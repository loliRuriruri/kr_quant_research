from kr_quant.research.kit import REQUIRED_HEADINGS, compile_system_prompt, kit_dir
from kr_quant.research.report import (
    build_report_messages,
    extract_summary,
    list_saved_reports,
    missing_headings,
    strip_fence,
)


def test_kit_compiles():
    text = compile_system_prompt()
    assert "45초 총평" in text
    assert "확인불가" in text
    assert (kit_dir() / "ADAPTER.md").exists()


def test_report_messages_include_quant_and_headings():
    msgs = build_report_messages(
        {"ticker": "005930", "company": "삼성전자", "quant_score": 80, "per": 12},
        "2026-08-13",
        links=[{"label": "네이버", "url": "https://finance.naver.com"}],
        news=[{"title": "실적 발표", "pubDate": "2026-08-13", "link": "https://news.example"}],
    )
    assert msgs[0]["role"] == "system"
    assert "Final Action Playbook" in msgs[0]["content"]
    assert "005930" in msgs[1]["content"]
    assert "quant_score" in msgs[1]["content"]
    assert "실적 발표" in msgs[1]["content"]
    assert "naver_news" in msgs[1]["content"]
    assert "macro_context" in msgs[1]["content"]
    assert "Quant 점수" in msgs[1]["content"]


def test_missing_headings_and_fence():
    text = strip_fence("```markdown\n## 45초 총평\nok\n```")
    assert text.startswith("## 45초 총평")
    miss = missing_headings(text)
    assert "밸류에이션" in miss
    assert "45초 총평" not in miss
    assert len(REQUIRED_HEADINGS) > 5


def test_extract_summary_skips_headings():
    text = "# 제목\n## 45초 총평\n이 회사는 엔진 부품을 만드는 제조업체다.\n"
    assert "엔진 부품" in extract_summary(text)


def test_list_saved_reports_reads_disk(tmp_path):
    folder = tmp_path / "research" / "as_of=2026-08-13"
    folder.mkdir(parents=True)
    (folder / "071970.report.json").write_text(
        '{"ticker":"071970","company":"HD현대마린엔진","as_of_date":"2026-08-13",'
        '"schema_version":"research_report_v4","provider":"xai","model":"grok-4.6",'
        '"researched_at":"2026-08-14T12:00:00+00:00","report_markdown":"## 45초 총평\\n엔진 제조사다."}',
        encoding="utf-8",
    )
    rows = list_saved_reports(tmp_path)
    assert len(rows) == 1
    assert rows[0]["kind"] == "AI 분석 리포트"
    assert rows[0]["ticker"] == "071970"
    assert "엔진" in rows[0]["summary"]
