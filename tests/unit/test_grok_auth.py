from kr_quant.research.grok_auth import grok_cli, parse_login_output, session_status


def test_session_status_shape():
    st = session_status()
    assert "connected" in st
    assert "cli" in st
    assert "auth_file" in st
    assert "email" in st


def test_cli_detection_is_bool():
    assert grok_cli() is None or grok_cli().name.lower().startswith("grok")


def test_parse_device_login_output():
    text = """
Open https://auth.x.ai/activate
Then enter this code:
WXYZ-1234
Confirm this code in your browser:
WXYZ-1234
Waiting for authorization...
"""
    parsed = parse_login_output(text)
    assert parsed["verification_url"] == "https://auth.x.ai/activate"
    assert parsed["user_code"] == "WXYZ-1234"
    assert parsed["detail"]


def test_parse_login_output_ignores_tokens():
    parsed = parse_login_output("access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaa")
    assert parsed["user_code"] is None
