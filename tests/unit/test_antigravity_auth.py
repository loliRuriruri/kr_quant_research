from kr_quant.research.antigravity_auth import check_agy_auth, find_agy_cli


def test_find_agy_cli():
    cli = find_agy_cli()
    assert cli is not None
    assert isinstance(cli, str)


def test_check_agy_auth_shape():
    res = check_agy_auth()
    assert isinstance(res, dict)
    assert "connected" in res
    assert "cli_available" in res
    assert "detail" in res


def test_no_token_stored():
    res = check_agy_auth()
    # Program must never store or expose OAuth tokens directly
    assert "access_token" not in res
    assert "refresh_token" not in res
