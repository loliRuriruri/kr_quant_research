from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any


class MarketDataAdapter(ABC):
    """KRX daily prices / master. Implementations must not invent adjusted prices."""

    @abstractmethod
    def fetch_daily(self, as_of: date, market: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def fetch_index(self, as_of: date, market: str) -> dict[str, Any] | None:
        raise NotImplementedError


class FilingAdapter(ABC):
    """OpenDART financials and corp map."""

    @abstractmethod
    def fetch_corp_map(self) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def fetch_company(self, corp_code: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def fetch_financials(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str,
        fs_div: str,
    ) -> dict[str, Any]:
        raise NotImplementedError
