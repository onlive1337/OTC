import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils.rates as rates
from utils.rates import normalize_fiat_payload, convert_currency


class TestNormalizeFiatPayload:
    def test_er_api_shape(self):
        # open.er-api.com: {"result": "success", "rates": {...}}
        payload = {"result": "success", "rates": {"USD": 1.0, "EUR": 0.9}}
        assert normalize_fiat_payload(payload) == {"USD": 1.0, "EUR": 0.9}

    def test_exchangerate_api_shape(self):
        # exchangerate-api.com: {"rates": {...}} (no "result" key)
        payload = {"rates": {"USD": 1.0, "RUB": 90.0}}
        assert normalize_fiat_payload(payload) == {"USD": 1.0, "RUB": 90.0}

    def test_fawazahmed_usd_shape(self):
        # fawazahmed currency-api: {"usd": {"eur": 0.9, ...}} with lowercase codes
        payload = {"date": "2024-01-01", "usd": {"eur": 0.9, "rub": 90.0}}
        result = normalize_fiat_payload(payload)
        assert result == {"USD": 1.0, "EUR": 0.9, "RUB": 90.0}

    def test_usd_shape_skips_non_positive_and_garbage(self):
        payload = {"usd": {"eur": 0.9, "bad": "x", "zero": 0, "neg": -1, "none": None}}
        result = normalize_fiat_payload(payload)
        assert result == {"USD": 1.0, "EUR": 0.9}

    def test_rates_takes_precedence_over_usd(self):
        payload = {"rates": {"USD": 1.0}, "usd": {"eur": 0.9}}
        assert normalize_fiat_payload(payload) == {"USD": 1.0}

    def test_non_dict_returns_none(self):
        assert normalize_fiat_payload(None) is None
        assert normalize_fiat_payload("oops") is None
        assert normalize_fiat_payload([1, 2, 3]) is None

    def test_unknown_shape_returns_none(self):
        assert normalize_fiat_payload({"result": "error", "code": 42}) is None
        assert normalize_fiat_payload({}) is None


class TestRateCache:
    def setup_method(self):
        rates.cache.clear()

    def test_set_and_get_fresh(self):
        rates.set_cached_data("exchange_rates", {"USD": 1.0})
        assert rates.get_cached_data("exchange_rates") == {"USD": 1.0}

    def test_expired_returns_none(self):
        stale_ts = time.time() - rates.CACHE_EXPIRATION_TIME - 10
        rates.cache["exchange_rates"] = ({"USD": 1.0}, stale_ts)
        assert rates.get_cached_data("exchange_rates") is None

    def test_missing_key_returns_none(self):
        assert rates.get_cached_data("does_not_exist") is None


class TestConvertCurrency:
    # rates are stored as "units per USD" for fiat, "USD per unit inverse" for crypto;
    # here we just verify the USD-pivot arithmetic.
    RATES = {"EUR": 0.9, "RUB": 90.0, "GBP": 0.8}

    def test_from_usd(self):
        assert convert_currency(100, "USD", "EUR", self.RATES) == 90.0

    def test_to_usd(self):
        assert convert_currency(90, "EUR", "USD", self.RATES) == 100.0

    def test_cross_rate(self):
        # 90 RUB -> USD (1.0) -> EUR (0.9)
        result = convert_currency(90, "RUB", "EUR", self.RATES)
        assert abs(result - 0.9) < 1e-9

    def test_missing_rate_raises(self):
        import pytest
        with pytest.raises(KeyError):
            convert_currency(1, "USD", "XXX", self.RATES)
