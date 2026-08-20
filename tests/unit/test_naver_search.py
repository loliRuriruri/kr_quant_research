from kr_quant.ingest.naver_maps import naver_map_search_url
from kr_quant.ingest.naver_search import ENDPOINTS, company_query, strip_html


def test_strip_html_and_query():
    assert strip_html("국내 <b>주식</b> 뉴스") == "국내 주식 뉴스"
    assert company_query("삼성전자", "5930") == "삼성전자 005930"


def test_search_news_requires_keys():
    try:
        from kr_quant.ingest.naver_search import search_news

        search_news("", "", "삼성전자")
    except RuntimeError as exc:
        assert "네이버" in str(exc)
        return
    raise AssertionError("expected missing-key error")


def test_hub_endpoints_cover_web_and_news():
    assert "news" in ENDPOINTS
    assert "webkr" in ENDPOINTS
    assert ENDPOINTS["news"][0].endswith("/news")


def test_map_search_url():
    url = naver_map_search_url("서울특별시 중구 세종대로 110")
    assert url.startswith("https://map.naver.com/p/search/")
    assert "세종대로" in url or "%EC%" in url
