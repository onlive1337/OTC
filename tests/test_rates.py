import os
import sys
import time
import asyncio
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils.rates as rates
from utils.rates import normalize_fiat_payload, convert_currency


class TestNormalizeFiatPayload:
    @pytest.mark.parametrize('shape', ['rates', 'usd'])
    def test_filters_nonfinite_and_invalid_rates(self, shape):
        payload = {shape: {'EUR': '0.9', 'nan': float('nan'), 'inf': float('inf'),
                           'negative': -1, 'zero': 0, 'boolean': True, 'bad': 'x'}}
        assert normalize_fiat_payload(payload) == {'USD': 1.0, 'EUR': 0.9}

    def test_empty_rates_are_not_a_success(self):
        assert normalize_fiat_payload({'rates': {'EUR': float('nan')}}) == {}

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


class TestStoreRates:
    def setup_method(self):
        rates.cache.clear()

    def test_full_fetch_is_cached(self):
        result = rates._store_rates({"USD": 1.0, "EUR": 0.9})
        assert result == {"USD": 1.0, "EUR": 0.9}
        assert rates.cache["exchange_rates"][0] == result

    def test_empty_fetch_keeps_previous_cache(self):
        rates.set_cached_data("exchange_rates", {"USD": 1.0, "EUR": 0.9})
        result = rates._store_rates({})
        assert result == {"USD": 1.0, "EUR": 0.9}
        assert rates.cache["exchange_rates"][0] == {"USD": 1.0, "EUR": 0.9}

    def test_empty_fetch_does_not_refresh_timestamp(self):
        stale_ts = time.time() - rates.CACHE_EXPIRATION_TIME - 10
        rates.cache["exchange_rates"] = ({"USD": 1.0}, stale_ts)
        rates._store_rates({})
        assert rates.cache["exchange_rates"][1] == stale_ts

    def test_empty_fetch_with_no_cache_returns_empty(self):
        assert rates._store_rates({}) == {}
        assert "exchange_rates" not in rates.cache

    def test_partial_fetch_merges_over_previous(self):
        rates.set_cached_data("exchange_rates", {"EUR": 0.9, "RUB": 90.0, "BTC": 0.00002})
        result = rates._store_rates({"BTC": 0.00001})
        assert result == {"EUR": 0.9, "RUB": 90.0, "BTC": 0.00001}
        assert rates.cache["exchange_rates"][0] == result


class TestConvertCurrency:
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


@pytest.fixture
def refresh_state(monkeypatch):
    monkeypatch.setattr(rates, 'cache', {})
    monkeypatch.setattr(rates, '_refresh_task', None)
    monkeypatch.setattr(rates, '_last_refresh_finished', None)


def test_concurrent_forced_refreshes_share_one_fetch(monkeypatch, refresh_state):
    async def scenario():
        fetch = AsyncMock(return_value={'USD': 1.0, 'EUR': 0.9})
        monkeypatch.setattr(rates, '_fetch_rates_unlocked', fetch)
        results = await asyncio.gather(*(rates.refresh_rates(force=True) for _ in range(100)))
        assert all(result == {'USD': 1.0, 'EUR': 0.9} for result in results)
        fetch.assert_awaited_once()
        await rates.close_rate_refresh()
    asyncio.run(scenario())


def test_stale_reads_schedule_one_refresh(monkeypatch, refresh_state):
    async def scenario():
        rates.cache['exchange_rates'] = ({'EUR': 0.9}, time.time() - rates.CACHE_EXPIRATION_TIME - 1)
        fetch = AsyncMock(return_value={'EUR': 0.95})
        monkeypatch.setattr(rates, '_fetch_rates_unlocked', fetch)
        results = await asyncio.gather(*(rates.get_exchange_rates() for _ in range(100)))
        assert all(result == {'EUR': 0.9} for result in results)
        await rates._refresh_task
        fetch.assert_awaited_once()
        await rates.close_rate_refresh()
    asyncio.run(scenario())


def test_cancelling_one_caller_does_not_cancel_shared_refresh(monkeypatch, refresh_state):
    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()
        async def fetch():
            started.set()
            await finish.wait()
            return {'EUR': 0.9}
        monkeypatch.setattr(rates, '_fetch_rates_unlocked', fetch)
        caller = asyncio.create_task(rates.refresh_rates())
        await started.wait()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert not rates._refresh_task.cancelled()
        finish.set()
        assert await rates.refresh_rates() == {'EUR': 0.9}
        await rates.close_rate_refresh()
    asyncio.run(scenario())


def test_failed_refresh_has_cooldown_and_keeps_old_cache(monkeypatch, refresh_state):
    async def scenario():
        old_timestamp = time.time() - 10000
        rates.cache['exchange_rates'] = ({'EUR': 0.9}, old_timestamp)
        fetch = AsyncMock(side_effect=RuntimeError('source offline'))
        monkeypatch.setattr(rates, '_fetch_rates_unlocked', fetch)
        for _ in range(10):
            assert await rates.refresh_rates(force=True) == {'EUR': 0.9}
        fetch.assert_awaited_once()
        assert rates.cache['exchange_rates'][1] == old_timestamp
        monkeypatch.setattr(rates, '_last_refresh_finished', time.monotonic() - 31)
        await rates.refresh_rates(force=True)
        assert fetch.await_count == 2
        await rates.close_rate_refresh()
    asyncio.run(scenario())


def test_refresh_timeout_and_shutdown_cancel_the_fetch(monkeypatch, refresh_state):
    async def scenario():
        cancelled = asyncio.Event()
        async def fetch():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        monkeypatch.setattr(rates, '_fetch_rates_unlocked', fetch)
        monkeypatch.setattr(rates, 'RATE_REFRESH_TIMEOUT', 0.01)
        assert await rates.refresh_rates() == {}
        assert cancelled.is_set()
        await rates.close_rate_refresh()
        cancelled.clear()
        monkeypatch.setattr(rates, 'RATE_REFRESH_TIMEOUT', 100)
        task = rates._start_refresh()
        await asyncio.sleep(0)
        await rates.close_rate_refresh()
        assert task.cancelled()
        assert cancelled.is_set()
    asyncio.run(scenario())


def test_crypto_failure_does_not_fan_out_to_individual_requests(monkeypatch, refresh_state):
    import aiohttp
    import config.config as config

    async def scenario():
        hosts = []
        async def fetch(factory, host, **kwargs):
            hosts.append(host)
            if host == 'api.coingecko.com':
                raise aiohttp.ClientConnectionError('offline')
            return {'rates': {currency: 1.0 for currency in rates.ACTIVE_CURRENCIES}}
        monkeypatch.setattr(rates, '_with_retries', fetch)
        monkeypatch.setattr(rates, 'get_http_session', lambda: object())
        monkeypatch.setattr(config, 'COINCAP_API_KEY', '')
        result = await rates.refresh_rates()
        assert result['EUR'] == 1.0
        assert hosts.count('api.coingecko.com') == 1
        await rates.close_rate_refresh()
    asyncio.run(scenario())


def test_crypto_timeout_preserves_completed_fiat(monkeypatch, refresh_state):
    async def scenario():
        async def fetch(factory, host, **kwargs):
            if host == 'api.coingecko.com':
                await asyncio.Event().wait()
            return {'rates': {currency: 1.0 for currency in rates.ACTIVE_CURRENCIES}}
        monkeypatch.setattr(rates, '_with_retries', fetch)
        monkeypatch.setattr(rates, 'get_http_session', lambda: object())
        monkeypatch.setattr(rates, 'RATE_REFRESH_TIMEOUT', 0.02)
        result = await rates.refresh_rates()
        assert result['EUR'] == 1.0
        await rates.close_rate_refresh()
    asyncio.run(scenario())


@pytest.mark.parametrize('api_key', ['', 'offline-demo-secret'])
@pytest.mark.parametrize('forbidden', [False, True])
def test_gecko_auth_is_scoped_and_fiat_survives_rejection(monkeypatch, refresh_state, caplog, api_key, forbidden):
    import aiohttp
    import config.config as config
    from types import SimpleNamespace

    calls = []

    class Response:
        def __init__(self, url):
            self.url = url
            self.gecko = 'api.coingecko.com/' in url

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def raise_for_status(self):
            if self.gecko and forbidden:
                raise aiohttp.ClientResponseError(
                    request_info=SimpleNamespace(real_url=self.url),
                    history=(), status=403, message='Forbidden',
                )

        async def json(self, **kwargs):
            if self.gecko:
                return {coin: {'usd': 50000} for coin in rates.CRYPTO_ID_MAPPING['coingecko'].values()}
            return {'rates': {currency: 1.0 for currency in rates.ACTIVE_CURRENCIES}}

    async def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response(url)

    monkeypatch.setattr(config, 'COINGECKO_DEMO_API_KEY', api_key)
    monkeypatch.setattr(config, 'COINCAP_API_KEY', '')
    monkeypatch.setattr(rates, 'get_http_session', lambda: SimpleNamespace(get=get))

    async def scenario():
        result = await rates.refresh_rates()
        assert result['EUR'] == 1.0
        if forbidden:
            assert 'BTC' not in result
        else:
            assert result['BTC'] == pytest.approx(1 / 50000)
        await rates.close_rate_refresh()

    asyncio.run(scenario())
    gecko_calls = [(url, options) for url, options in calls if 'api.coingecko.com/' in url]
    assert len(gecko_calls) == 1
    url, options = gecko_calls[0]
    assert options['headers'] == ({'x-cg-demo-api-key': api_key} if api_key else {})
    assert options['allow_redirects'] is False
    assert 'api_key' not in url
    assert all('x-cg-demo-api-key' not in options.get('headers', {})
               for url, options in calls if 'api.coingecko.com/' not in url)
    if api_key:
        assert api_key not in caplog.text
        assert all(api_key not in url for url, _ in calls)
