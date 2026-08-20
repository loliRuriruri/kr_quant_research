from pathlib import Path

from kr_quant.web.envfile import mask_secret, parse_env_value, quote_env_value, read_env_map, upsert_env_file


def test_mask_and_quote():
    assert mask_secret(None)["configured"] is False
    m = mask_secret("abcdefghij")
    assert m["configured"] is True
    assert m["masked"].endswith("ghij")
    assert parse_env_value(quote_env_value("a+b/c=")) == "a+b/c="


def test_upsert_keeps_existing(tmp_path: Path):
    p = tmp_path / ".env"
    p.write_text("OPENDART_API_KEY=old\nKRX_API_KEY=keepme\n", encoding="utf-8")
    upsert_env_file(p, {"OPENDART_API_KEY": "new", "KRX_API_KEY": None})
    data = read_env_map(p)
    assert data["OPENDART_API_KEY"] == "new"
    assert data["KRX_API_KEY"] == "keepme"
