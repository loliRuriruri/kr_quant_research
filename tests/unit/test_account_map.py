from kr_quant.normalize.accounts import load_account_lookup, map_account


def test_samsung_style_accounts(settings):
    lookup = load_account_lookup(settings.account_map)
    assert map_account("dart_OperatingIncomeLoss", "영업이익", lookup) == "operating_profit"
    assert map_account("ifrs-full_Revenue", "매출액", lookup) == "revenue"
    assert map_account("-표준계정코드 미사용-", "단기차입금", lookup) == "short_term_borrowings"
    assert map_account("ifrs-full_ShorttermDepositsNotClassifiedAsCashEquivalents", "단기금융상품", lookup) == (
        "short_term_financial_assets"
    )
    assert map_account("ifrs-full_IncomeTaxExpenseContinuingOperations", "법인세비용(수익)", lookup) == "income_tax"
    assert map_account("ifrs-full_RepaymentsOfNoncurrentBorrowings", "사채 및 장기차입금의 상환", lookup) is None
