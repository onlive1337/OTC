import asyncio
import logging
import math
import time
from typing import Dict, Any, Optional

import aiohttp
import ujson

from config.config import (
    CACHE_EXPIRATION_TIME, ACTIVE_CURRENCIES, CRYPTO_CURRENCIES,
    CRYPTO_ID_MAPPING, HTTP_TOTAL_TIMEOUT, HTTP_CONNECT_TIMEOUT,
    STALE_WHILE_REVALIDATE, HTTP_CONNECTOR_LIMIT,
    HTTP_CONNECTOR_LIMIT_PER_HOST, HTTP_DNS_CACHE_TTL,
    RATE_REFRESH_TIMEOUT, RATE_REFRESH_RETRY_INTERVAL,
)
from utils.http import _host_of, _with_retries, _safe_bg_task, get_http_session

logger = logging.getLogger(__name__)

cache: Dict[str, Any] = {}
_refresh_task: Optional[asyncio.Task] = None
_last_refresh_finished: Optional[float] = None


def _as_rates_dict(payload: Any) -> Optional[Dict[str, float]]:
    return payload if isinstance(payload, dict) else None


def normalize_fiat_payload(fiat_data: Any) -> Optional[Dict[str, float]]:
    if not isinstance(fiat_data, dict):
        return None

    source = fiat_data.get('rates')
    if not isinstance(source, dict):
        source = fiat_data.get('usd')
    if isinstance(source, dict):
        normalized_rates: Dict[str, float] = {}
        for currency, rate in source.items():
            try:
                if isinstance(rate, bool):
                    continue
                rate_f = float(rate)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(rate_f) and rate_f > 0:
                normalized_rates[str(currency).upper()] = rate_f
        if normalized_rates:
            normalized_rates['USD'] = 1.0
        return normalized_rates

    return None


def get_cached_data(key: str) -> Optional[Any]:
    if key in cache:
        cached_data, timestamp = cache[key]
        if time.time() - timestamp < CACHE_EXPIRATION_TIME:
            return cached_data
    return None


def set_cached_data(key: str, data: Dict[str, float]):
    cache[key] = (data, time.time())


def _store_rates(new_rates: Dict[str, float]) -> Dict[str, float]:
    prev_item = cache.get('exchange_rates')
    prev_rates = _as_rates_dict(prev_item[0]) if prev_item else None

    if not new_rates:
        logger.error("No rates fetched, keeping previous cache untouched")
        return prev_rates or {}

    merged = {**prev_rates, **new_rates} if prev_rates else new_rates
    set_cached_data('exchange_rates', merged)
    logger.info(f"Successfully cached {len(merged)} exchange rates ({len(new_rates)} freshly fetched)")
    return merged


async def get_exchange_rates() -> Dict[str, float]:
    try:
        cached_rates = _as_rates_dict(get_cached_data('exchange_rates'))
        if cached_rates:
            logger.debug("Using cached exchange rates")
            return cached_rates

        stale_item = cache.get('exchange_rates')
        now = time.time()
        if stale_item:
            data, ts = stale_item
            if now - ts < (CACHE_EXPIRATION_TIME + STALE_WHILE_REVALIDATE):
                _start_refresh()
                logger.info("Returning stale exchange rates while refreshing in background")
                return data

        rates = await refresh_rates()

        if not rates and stale_item:
            data, ts = stale_item
            age_minutes = int((now - ts) / 60)
            logger.warning(f"All rate sources failed, using {age_minutes}min old cache as fallback")
            return data

        return rates
    except (RuntimeError, asyncio.TimeoutError, aiohttp.ClientError, ValueError, TypeError, KeyError) as fetch_err:
        logger.error(f"Error fetching exchange rates: {fetch_err}")
        stale_item = cache.get('exchange_rates')
        if stale_item:
            data, _ = stale_item
            logger.warning("Using emergency fallback cache due to exception")
            return data
        return {}


def _previous_rates() -> Dict[str, float]:
    item = cache.get('exchange_rates')
    return (_as_rates_dict(item[0]) or {}) if item else {}


def _start_refresh() -> Optional[asyncio.Task]:
    global _refresh_task
    # Assign before yielding: all concurrent callers share this exact task.
    if _refresh_task is not None and not _refresh_task.done():
        return _refresh_task
    if (_last_refresh_finished is not None
            and time.monotonic() - _last_refresh_finished < RATE_REFRESH_RETRY_INTERVAL):
        return None
    _refresh_task = _safe_bg_task(_run_refresh(), name="refresh_rates")
    return _refresh_task


async def _run_refresh() -> Dict[str, float]:
    global _last_refresh_finished
    try:
        async with asyncio.timeout(RATE_REFRESH_TIMEOUT):
            return await _fetch_rates_unlocked()
    except (RuntimeError, asyncio.TimeoutError, aiohttp.ClientError, ValueError, TypeError, KeyError):
        logger.exception("Rate refresh failed; keeping cached rates")
        return _previous_rates()
    finally:
        _last_refresh_finished = time.monotonic()


async def refresh_rates(force: bool = False) -> Dict[str, float]:
    if not force:
        fresh = _as_rates_dict(get_cached_data('exchange_rates'))
        if fresh:
            return fresh
    task = _start_refresh()
    # A disconnected caller must not cancel the refresh shared by other users.
    return await asyncio.shield(task) if task is not None else _previous_rates()


async def close_rate_refresh():
    global _refresh_task, _last_refresh_finished
    if _refresh_task is not None:
        _refresh_task.cancel()
        await asyncio.gather(_refresh_task, return_exceptions=True)
        _refresh_task = None
    _last_refresh_finished = None


async def _fetch_rates_unlocked() -> Dict[str, float]:
    session_to_close = None
    rates: Dict[str, float] = {}

    try:
        from config.config import COINCAP_API_KEY, COINGECKO_DEMO_API_KEY

        session_opt = get_http_session()
        if session_opt is None:
            session_to_close = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(
                    limit=HTTP_CONNECTOR_LIMIT,
                    limit_per_host=HTTP_CONNECTOR_LIMIT_PER_HOST,
                    ttl_dns_cache=HTTP_DNS_CACHE_TTL,
                ),
                json_serialize=ujson.dumps,
            )
            session_opt = session_to_close

        assert session_opt is not None
        session = session_opt

        timeout = aiohttp.ClientTimeout(total=HTTP_TOTAL_TIMEOUT, connect=HTTP_CONNECT_TIMEOUT)

        fiat_sources = [
            'https://open.er-api.com/v6/latest/USD',
            'https://api.exchangerate-api.com/v4/latest/USD',
            'https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json'
        ]

        async def _fetch_single_fiat(fiat_url: str):
            source_host = _host_of(fiat_url)

            async def _fiat(url=fiat_url):
                resp = await session.get(url, timeout=timeout)
                async with resp:
                    resp.raise_for_status()
                    return await resp.json(loads=ujson.loads)

            fiat_data = await _with_retries(_fiat, source_host)

            normalized = normalize_fiat_payload(fiat_data)
            if normalized is not None:
                logger.info(f"Fetched fiat rates from {source_host}")
            return normalized

        async def _fetch_all_fiat():
            needed_fiat = set(ACTIVE_CURRENCIES)
            merged: Dict[str, float] = {}
            tasks = [asyncio.create_task(_fetch_single_fiat(url)) for url in fiat_sources]
            try:
                for coro in asyncio.as_completed(tasks):
                    try:
                        fiat_chunk = await coro
                        if fiat_chunk:
                            merged.update(fiat_chunk)
                            if needed_fiat.issubset(merged.keys()):
                                for t in tasks:
                                    if not t.done():
                                        t.cancel()
                                return merged
                    except (RuntimeError, asyncio.TimeoutError, aiohttp.ClientError, ValueError, TypeError, KeyError) as fiat_error:
                        logger.warning(f"Fiat source failed: {fiat_error}")
                        continue
            finally:
                for t in tasks:
                    if not t.done():
                        t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                # Keep completed fiat data even if the crypto branch times out.
                rates.update(merged)
            return merged or None

        gecko_mapping = CRYPTO_ID_MAPPING['coingecko']
        crypto_ids = ','.join(gecko_mapping.values())
        url_cg = f'https://api.coingecko.com/api/v3/simple/price?ids={crypto_ids}&vs_currencies=usd'
        # Keep the key out of URLs/logs and send it only to CoinGecko.
        gecko_headers = {'x-cg-demo-api-key': COINGECKO_DEMO_API_KEY} if COINGECKO_DEMO_API_KEY else {}

        async def _fetch_coingecko():
            coingecko_host = _host_of(url_cg)
            async def _cg():
                resp = await session.get(url_cg, timeout=timeout, headers=gecko_headers, allow_redirects=False)
                async with resp:
                    resp.raise_for_status()
                    return await resp.json(loads=ujson.loads)
            return await _with_retries(_cg, coingecko_host)

        async def _fetch_all_crypto():
            try:
                cg_result = await _fetch_coingecko()
                crypto_rates = {}
                for cg_symbol, cg_id in gecko_mapping.items():
                    if isinstance(cg_result, dict) and cg_id in cg_result and isinstance(cg_result[cg_id], dict):
                        cg_usd_price = cg_result[cg_id].get('usd')
                        try:
                            cg_usd_price = float(cg_usd_price)
                        except (TypeError, ValueError):
                            cg_usd_price = None
                        if cg_usd_price and math.isfinite(cg_usd_price) and cg_usd_price > 0:
                            crypto_rates[cg_symbol] = 1.0 / cg_usd_price
                logger.info("Fetched crypto rates from CoinGecko")
                rates.update(crypto_rates)
                return crypto_rates
            except (RuntimeError, asyncio.TimeoutError, aiohttp.ClientError, ValueError, TypeError, KeyError) as coingecko_error:
                logger.error(f"CoinGecko failed: {coingecko_error}")
                return None

        fiat_result, crypto_result = await asyncio.gather(
            _fetch_all_fiat(), _fetch_all_crypto(), return_exceptions=True
        )

        fiat_fetched = False
        if isinstance(fiat_result, dict):
            rates.update(fiat_result)
            fiat_fetched = True
        elif isinstance(fiat_result, Exception):
            logger.error(f"Fiat fetch failed with exception: {fiat_result}")

        if not fiat_fetched:
            logger.error("All fiat currency sources failed!")

        if isinstance(crypto_result, dict):
            rates.update(crypto_result)
        elif isinstance(crypto_result, Exception):
            logger.error(f"Crypto fetch failed with exception: {crypto_result}")

        all_currencies = set(ACTIVE_CURRENCIES + CRYPTO_CURRENCIES)
        missing_currencies = all_currencies - set(rates.keys())

        if missing_currencies:
            logger.warning(f"Missing currencies after primary sources: {missing_currencies}")

            missing_crypto = missing_currencies.intersection(set(CRYPTO_CURRENCIES))
            if missing_crypto and COINCAP_API_KEY:
                logger.info(f"Trying CoinCap v3 for: {missing_crypto}")
                coincap_mapping = CRYPTO_ID_MAPPING['coincap']

                async def _fetch_coincap_single(crypto_sym):
                    asset_id = coincap_mapping.get(crypto_sym, crypto_sym.lower())
                    url_cap = f'https://rest.coincap.io/v3/assets/{asset_id}?apiKey={COINCAP_API_KEY}'
                    coincap_host = _host_of(url_cap)
                    async def _cap(u=url_cap):
                        resp = await session.get(u, timeout=timeout)
                        async with resp:
                            resp.raise_for_status()
                            return await resp.json(loads=ujson.loads)
                    try:
                        alt_crypto_data = await _with_retries(_cap, coincap_host)
                        if isinstance(alt_crypto_data, dict) and 'data' in alt_crypto_data:
                            coincap_usd_price = float(alt_crypto_data['data'].get('priceUsd', 0))
                            if math.isfinite(coincap_usd_price) and coincap_usd_price > 0:
                                logger.info(f"Fetched {crypto_sym} from CoinCap v3")
                                return crypto_sym, 1.0 / coincap_usd_price
                    except (RuntimeError, asyncio.TimeoutError, aiohttp.ClientError, ValueError, TypeError, KeyError) as coincap_error:
                        # ClientResponseError includes the request URL (and API key).
                        logger.warning("Failed to fetch %s from CoinCap v3: %s", crypto_sym, type(coincap_error).__name__)
                    return crypto_sym, None

                coincap_results = await asyncio.gather(
                    *(_fetch_coincap_single(c) for c in missing_crypto),
                    return_exceptions=True
                )
                for coincap_item in coincap_results:
                    if isinstance(coincap_item, tuple) and coincap_item[1] is not None:
                        rates[coincap_item[0]] = coincap_item[1]

            elif missing_crypto:
                logger.info("CoinCap fallback is disabled; retaining any previously cached crypto rates")

        rates = _store_rates(rates)

        final_missing = all_currencies - set(rates.keys())
        if final_missing:
            logger.error(f"Still missing currencies after all attempts: {final_missing}")

        return rates

    except asyncio.CancelledError:
        if rates:
            _store_rates(rates)
        raise
    except (RuntimeError, asyncio.TimeoutError, aiohttp.ClientError, ValueError, TypeError, KeyError) as refresh_error:
        logger.error(f"Critical error in _refresh_rates: {refresh_error}")
        return _store_rates(rates)
    finally:
        if session_to_close is not None:
            await session_to_close.close()


def convert_currency(amount: float, from_currency: str, to_currency: str, rates: Dict[str, float]) -> float:
    if from_currency != 'USD' and from_currency not in rates:
        raise KeyError(f"Rate not available for {from_currency}")
    if to_currency != 'USD' and to_currency not in rates:
        raise KeyError(f"Rate not available for {to_currency}")

    if from_currency != 'USD' and rates.get(from_currency, 0) == 0:
        raise ValueError(f"Invalid rate for {from_currency}")
    if to_currency != 'USD' and rates.get(to_currency, 0) == 0:
        raise ValueError(f"Invalid rate for {to_currency}")

    if from_currency == 'USD':
        return amount * rates[to_currency]
    elif to_currency == 'USD':
        return amount / rates[from_currency]
    else:
        return amount / rates[from_currency] * rates[to_currency]
