"""Market data access (Yahoo Finance) behind a narrow, typed interface."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Mapping

from .errors import UpstreamError
from .models import normalize_symbol

logger = logging.getLogger(__name__)

CHAIN_COLUMNS = ["strike", "lastPrice", "bid", "ask", "volume", "openInterest", "impliedVolatility"]
CHAIN_ROWS = 10
MAX_EXPIRIES = 8

TickerFactory = Callable[[str], Any]


def _default_ticker_factory(symbol: str) -> Any:
    import yfinance as yf  # imported lazily so tests need no network stack

    return yf.Ticker(symbol)


class _TTLCache:
    """Minimal thread-safe TTL cache; keeps Yahoo from being hammered."""

    def __init__(self, ttl: float) -> None:
        self._ttl = ttl
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        if self._ttl <= 0:
            return None
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.monotonic():
                self._entries.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        if self._ttl <= 0:
            return
        with self._lock:
            self._entries[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def _as_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if result != result else result


class MarketDataService:
    """Fetches quotes, summaries and option chains.

    The ticker factory is injectable so the service can be tested without
    touching the network.
    """

    def __init__(
        self,
        *,
        ticker_factory: TickerFactory = _default_ticker_factory,
        cache_ttl: float = 30.0,
    ) -> None:
        self._ticker_factory = ticker_factory
        self._cache = _TTLCache(cache_ttl)

    def _ticker(self, symbol: str) -> Any:
        try:
            return self._ticker_factory(symbol)
        except Exception as exc:  # noqa: BLE001 - third-party failure surface
            raise UpstreamError(f"تعذّر الوصول لبيانات {symbol}") from exc

    def get_price(self, raw_symbol: str) -> float | None:
        symbol = normalize_symbol(raw_symbol)
        cached = self._cache.get(f"price:{symbol}")
        if cached is not None:
            return cached
        ticker = self._ticker(symbol)
        try:
            price = _as_float(getattr(ticker.fast_info, "last_price", None))
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"تعذّر جلب سعر {symbol}") from exc
        price = round(price, 2) if price else None
        self._cache.set(f"price:{symbol}", price)
        return price

    def get_summary(self, raw_symbol: str) -> dict[str, Any]:
        symbol = normalize_symbol(raw_symbol)
        cached = self._cache.get(f"summary:{symbol}")
        if cached is not None:
            return cached
        ticker = self._ticker(symbol)
        try:
            info: Mapping[str, Any] = ticker.info or {}
            history = ticker.history(period="5d")
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"تعذّر جلب بيانات السوق لـ {symbol}") from exc

        change_pct = 0.0
        try:
            closes = history["Close"]
            if len(closes) >= 2 and closes.iloc[-2]:
                change_pct = round((closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100, 2)
        except (KeyError, IndexError, TypeError, ZeroDivisionError):
            logger.debug("no usable price history for %s", symbol)

        summary = {
            "symbol": symbol,
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "change_pct": change_pct,
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "beta": info.get("beta"),
            "sector": info.get("sector"),
        }
        self._cache.set(f"summary:{symbol}", summary)
        return summary

    def get_options_chain(self, raw_symbol: str, expiry: str | None = None) -> dict[str, Any]:
        symbol = normalize_symbol(raw_symbol)
        cache_key = f"chain:{symbol}:{expiry or ''}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        ticker = self._ticker(symbol)
        try:
            expiries = list(ticker.options or [])
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"تعذّر جلب تواريخ الاستحقاق لـ {symbol}") from exc
        if not expiries:
            raise UpstreamError(f"لا توجد عقود خيارات متاحة لـ {symbol}")

        target = expiry if expiry in expiries else expiries[0]
        try:
            chain = ticker.option_chain(target)
            calls = chain.calls[CHAIN_COLUMNS].head(CHAIN_ROWS).to_dict("records")
            puts = chain.puts[CHAIN_COLUMNS].head(CHAIN_ROWS).to_dict("records")
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"تعذّر جلب سلسلة الخيارات لـ {symbol}") from exc

        result = {
            "symbol": symbol,
            "expiry": target,
            "calls": calls,
            "puts": puts,
            "all_expiries": expiries[:MAX_EXPIRIES],
        }
        self._cache.set(cache_key, result)
        return result
