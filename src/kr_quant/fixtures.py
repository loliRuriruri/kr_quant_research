from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from kr_quant.calendar import is_default_trading_day

AS_OF = date(2024, 12, 30)


def trading_days(start: date, end: date) -> list[date]:
    days = []
    cur = start
    while cur <= end:
        if is_default_trading_day(cur):
            days.append(cur)
        cur += timedelta(days=1)
    return days


def _specs() -> list[dict]:
    specs: list[dict] = []
    for i in range(1, 26):
        specs.append(
            {
                "ticker": f"E{i:05d}",
                "company": f"전자우량{i:02d}",
                "market": "KOSPI" if i <= 15 else "KOSDAQ",
                "ksic": "26111",
                "kind": "보통주",
                "profile": "core",
            }
        )
    for i in range(1, 9):
        specs.append(
            {
                "ticker": f"C{i:05d}",
                "company": f"화학소재{i:02d}",
                "market": "KOSPI",
                "ksic": "20111",
                "kind": "보통주",
                "profile": "core",
            }
        )
    for i in range(1, 6):
        specs.append(
            {
                "ticker": f"S{i:05d}",
                "company": f"소프트웨어{i:02d}",
                "market": "KOSDAQ",
                "ksic": "62010",
                "kind": "보통주",
                "profile": "core",
            }
        )
    specs[0]["profile"] = "compounder"
    specs[1]["profile"] = "value"
    specs[2]["profile"] = "loss"
    specs[3]["profile"] = "turnaround"
    specs[4]["profile"] = "leverage"
    specs[5]["profile"] = "decline"
    specs[6]["profile"] = "dilution"
    specs[7]["profile"] = "oneoff"
    specs[8]["profile"] = "thin_equity"
    specs[9]["profile"] = "cb_bw"
    specs.append(
        {
            "ticker": "B00001",
            "company": "테스트은행",
            "market": "KOSPI",
            "ksic": "64121",
            "kind": "보통주",
            "profile": "bank",
        }
    )
    specs.append(
        {
            "ticker": "R00001",
            "company": "테스트리츠",
            "market": "KOSPI",
            "ksic": "68121",
            "kind": "보통주",
            "profile": "reit",
        }
    )
    specs.append(
        {
            "ticker": "P00001",
            "company": "테스트스팩1호",
            "market": "KOSDAQ",
            "ksic": "64999",
            "kind": "보통주",
            "profile": "spac",
        }
    )
    specs.append(
        {
            "ticker": "N00001",
            "company": "자본잠식테스트",
            "market": "KOSDAQ",
            "ksic": "26111",
            "kind": "보통주",
            "profile": "neg_equity",
        }
    )
    return specs


def _profile_params(profile: str, rng: np.random.Generator) -> dict:
    base = {
        "rev0": 8.0e11,
        "g": 0.08,
        "opm": 0.12,
        "tax": 0.22,
        "cfo_ni": 1.05,
        "capex_rev": 0.04,
        "assets_rev": 1.4,
        "debt_assets": 0.18,
        "cash_assets": 0.12,
        "sfa_assets": 0.03,
        "px": 50000.0,
        "shares": 2.0e8,
        "mkt_mult": 1.0,
    }
    if profile == "compounder":
        base.update({"g": 0.18, "opm": 0.22, "cfo_ni": 1.2, "capex_rev": 0.05, "debt_assets": 0.08})
    elif profile == "value":
        base.update({"g": 0.04, "opm": 0.10, "mkt_mult": 0.45, "cfo_ni": 1.3})
    elif profile == "loss":
        base.update({"opm": -0.04, "cfo_ni": 0.2, "g": -0.02})
    elif profile == "turnaround":
        base.update({"opm": 0.08, "g": 0.10, "turnaround": True})
    elif profile == "leverage":
        base.update({"debt_assets": 0.55, "cash_assets": 0.03, "int_rate": 0.06})
    elif profile == "decline":
        base.update({"g": -0.08, "opm": 0.06})
    elif profile == "dilution":
        base.update({"dilute": 0.12})
    elif profile == "oneoff":
        base.update({"opm": -0.02, "oneoff_gain": 0.08})
    elif profile == "thin_equity":
        base.update({"debt_assets": 0.70, "cash_assets": 0.05})
    elif profile == "cb_bw":
        base.update({"cb_dilution": 0.18, "cb_count": 2})
    elif profile == "neg_equity":
        base.update({"neg_eq": True, "opm": -0.15})
    elif profile == "bank":
        base.update({"rev0": 3.0e12, "opm": 0.25})
    base["noise"] = rng.normal(0, 0.01)
    return base


def generate_demo_dataset(out_dir: Path, as_of: date = AS_OF) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    specs = _specs()
    days = trading_days(date(2023, 1, 2), as_of)
    prices: list[dict] = []
    facts: list[dict] = []
    master: list[dict] = []
    extra_rows: list[dict] = []

    years = [2020, 2021, 2022, 2023, 2024]
    report_meta = [
        ("11013", 3, 31, 0.25),
        ("11012", 6, 30, 0.50),
        ("11014", 9, 30, 0.75),
        ("11011", 12, 31, 1.00),
    ]

    for idx, spec in enumerate(specs):
        p = _profile_params(spec["profile"], rng)
        ticker = spec["ticker"]
        sid = f"KR{ticker}"
        shares0 = p["shares"]
        shares_now = shares0 * (1.12 if spec["profile"] == "dilution" else 1.0)
        px = p["px"] * p["mkt_mult"] * (1 + 0.002 * idx)
        mcap = px * shares_now
        master.append(
            {
                "security_id": sid,
                "ticker": ticker,
                "corp_code": f"{10000000 + idx:08d}",
                "company": spec["company"],
                "market": spec["market"],
                "kind": spec["kind"],
                "secu_group": "주권",
                "list_date": date(2015, 1, 5),
                "induty_code": spec["ksic"],
                "acc_mt": 12,
            }
        )
        extra_rows.append(
            {
                "ticker": ticker,
                "shares_latest": shares_now,
                "shares_12m_ago": shares0,
                "potential_dilution_pct": p.get("cb_dilution"),
                "cb_bw_count_24m": int(p.get("cb_count") or 0),
            }
        )
        for d in days:
            drift = 1.0 + 0.0002 * ((d - days[0]).days)
            close = px * drift * (1 + 0.01 * np.sin(idx + d.toordinal() / 20))
            prices.append(
                {
                    "security_id": sid,
                    "ticker": ticker,
                    "company": spec["company"],
                    "market": spec["market"],
                    "trade_date": d,
                    "open": close * 0.995,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "adj_close": None,
                    "volume": 1_000_000 + 1000 * idx,
                    "trading_value": 5.0e8 + idx * 1.0e7,
                    "market_cap": close * shares_now,
                    "listed_shares": shares_now,
                    "kind": spec["kind"],
                    "secu_group": "주권",
                    "list_date": date(2015, 1, 5),
                }
            )

        for year in years:
            growth_year = year - 2020
            g = p["g"]
            if spec["profile"] == "decline":
                g = -0.08
            rev_fy = p["rev0"] * ((1 + g) ** growth_year)
            opm = p["opm"]
            if spec["profile"] == "turnaround":
                opm = -0.05 if year <= 2022 else 0.09
            if spec["profile"] == "loss":
                opm = -0.04
            op_fy = rev_fy * opm
            if spec["profile"] == "oneoff":
                pretax_fy = op_fy + rev_fy * 0.10
            else:
                pretax_fy = op_fy * 0.95
            tax_fy = max(pretax_fy, 0) * p["tax"]
            ni_fy = pretax_fy - tax_fy
            nio_fy = ni_fy * 0.97
            assets = rev_fy * p["assets_rev"]
            if spec["profile"] == "neg_equity":
                equity = -1.0e10
            elif spec["profile"] == "thin_equity":
                equity = assets * 0.03
            else:
                equity = assets * (1 - p["debt_assets"] - 0.25)
            liab = assets - equity
            debt = assets * p["debt_assets"]
            cash = assets * p["cash_assets"]
            sfa = assets * p["sfa_assets"]
            cfo_fy = ni_fy * p["cfo_ni"]
            capex_fy = rev_fy * p["capex_rev"]
            interest_fy = debt * float(p.get("int_rate", 0.03))

            for code, month, day, frac in report_meta:
                period_end = date(year, month, day)
                period_start = date(year, 1, 1)
                available = period_end + timedelta(days=40)
                # Q3 2024 available mid-Nov; FY 2024 not yet available on 2024-12-30
                if year == 2024 and code == "11011":
                    available = date(2025, 3, 15)

                def add(account: str, account_id: str, value: float, sj: str) -> None:
                    facts.append(
                        {
                            "security_id": sid,
                            "ticker": ticker,
                            "corp_code": f"{10000000 + idx:08d}",
                            "canonical_account": account,
                            "account_id": account_id,
                            "account_nm": account,
                            "sj_div": sj,
                            "fs_div": "CFS",
                            "bsns_year": year,
                            "reprt_code": code,
                            "period_start": period_start,
                            "period_end": period_end,
                            "normalized_value": value,
                            "currency": "KRW",
                            "rcept_no": f"{year}{code}{idx:04d}",
                            "rcept_dt": available,
                            "available_date": available,
                            "revision_id": 1,
                            "is_correction": False,
                            "is_withdrawn": False,
                        }
                    )

                add("revenue", "ifrs-full_Revenue", rev_fy * frac, "IS")
                add("operating_profit", "ifrs-full_ProfitLossFromOperatingActivities", op_fy * frac, "IS")
                add("pretax_income", "ifrs-full_ProfitLossBeforeTax", pretax_fy * frac, "IS")
                add("net_income", "ifrs-full_ProfitLoss", ni_fy * frac, "IS")
                add("net_income_owners", "ifrs-full_ProfitLossAttributableToOwnersOfParent", nio_fy * frac, "IS")
                add("income_tax", "ifrs-full_IncomeTaxExpenseContinuingOperations", tax_fy * frac, "IS")
                add("interest_expense", "ifrs-full_InterestExpense", interest_fy * frac, "IS")
                add("cfo", "ifrs-full_CashFlowsFromUsedInOperatingActivities", cfo_fy * frac, "CF")
                add(
                    "ppe_acquisition",
                    "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
                    capex_fy * 0.8 * frac,
                    "CF",
                )
                add(
                    "intangible_acquisition",
                    "ifrs-full_PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",
                    capex_fy * 0.2 * frac,
                    "CF",
                )
                add("total_assets", "ifrs-full_Assets", assets, "BS")
                add("total_liabilities", "ifrs-full_Liabilities", liab, "BS")
                add("total_equity", "ifrs-full_Equity", equity, "BS")
                add("equity_owners", "ifrs-full_EquityAttributableToOwnersOfParent", equity * 0.97, "BS")
                add("nci", "ifrs-full_NoncontrollingInterests", equity * 0.03, "BS")
                add("cash", "ifrs-full_CashAndCashEquivalents", cash, "BS")
                add("short_term_financial_assets", "ifrs-full_CurrentFinancialAssets", sfa, "BS")
                add("current_assets", "ifrs-full_CurrentAssets", assets * 0.45, "BS")
                add("current_liabilities", "ifrs-full_CurrentLiabilities", max(liab * 0.4, 1.0), "BS")
                add("short_term_borrowings", "ifrs-full_ShorttermBorrowings", debt * 0.3, "BS")
                add("current_portion_ltd", "ifrs-full_CurrentPortionOfLongtermBorrowings", debt * 0.1, "BS")
                add("long_term_borrowings", "ifrs-full_LongtermBorrowings", debt * 0.4, "BS")
                add("bonds", "ifrs-full_BondsIssued", debt * 0.15, "BS")
                add("lease_liabilities", "ifrs-full_LeaseLiabilities", debt * 0.05, "BS")

    prices_df = pd.DataFrame(prices)
    facts_df = pd.DataFrame(facts)
    master_df = pd.DataFrame(master)
    extra_df = pd.DataFrame(extra_rows)
    status_df = pd.DataFrame(
        [{"ticker": s["ticker"], "as_of_date": as_of, "status": "NORMAL"} for s in specs]
    )

    paths = {
        "prices": out_dir / "prices.parquet",
        "facts": out_dir / "financial_facts.parquet",
        "master": out_dir / "master.parquet",
        "extra": out_dir / "extra.parquet",
        "status": out_dir / "manual_status.csv",
    }
    prices_df.to_parquet(paths["prices"], index=False)
    facts_df.to_parquet(paths["facts"], index=False)
    master_df.to_parquet(paths["master"], index=False)
    extra_df.to_parquet(paths["extra"], index=False)
    status_df.to_csv(paths["status"], index=False)
    return paths
