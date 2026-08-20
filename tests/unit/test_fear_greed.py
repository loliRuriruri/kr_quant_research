from kr_quant.ingest.fear_greed import _normalize_side, band_for


def test_fear_greed_bands():
    assert band_for(12)["id"] == "EXTREME_FEAR"
    assert band_for(40)["id"] == "FEAR"
    assert band_for(50)["id"] == "NEUTRAL"
    assert band_for(62)["id"] == "GREED"
    assert band_for(86)["id"] == "EXTREME_GREED"


def test_normalize_kr_payload():
    side = _normalize_side(
        {
            "score": 86,
            "label": "극단적 탐욕",
            "kospi_change": "5.89",
            "indicators": [{"name": "변동성 (VKOSPI)", "value": 79, "raw": 21}],
            "source": "한국투자증권 Open API",
        },
        "x",
    )
    assert side["score"] == 86
    assert side["band"] == "EXTREME_GREED"
    assert side["kospi_change"] == 5.89
    assert side["indicators"][0]["name"].startswith("변동성")
