# -*- coding: utf-8 -*-
from kr_quant.web.publish import URL_RE, load_publish_config


def test_publish_config_defaults_to_pages_project():
    cfg = load_publish_config()
    assert cfg["project"] == "korea-quant-research"
    assert "live" in cfg["after_jobs"]
    assert "screen" in cfg["after_jobs"]


def test_parse_pages_url_from_wrangler_output():
    text = "Deployment complete! Take a peek over at https://3a19cc91.korea-quant-research.pages.dev"
    urls = URL_RE.findall(text)
    assert urls[-1].startswith("https://")
    assert "pages.dev" in urls[-1]
