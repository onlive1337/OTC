import asyncio
import logging
import time
from typing import Dict, Any, Optional

import aiohttp
import ujson

from config.config import (
    CACHE_EXPIRATION_TIME, ACTIVE_CURRENCIES, CRYPTO_CURRENCIES,
    CRYPTO_ID_MAPPING, HTTP_TOTAL_TIMEOUT, HTTP_CONNECT_TIMEOUT,
    STALE_WHILE_REVALIDATE, HTTP_CONNECTOR_LIMIT,
    HTTP_CONNECTOR_LIMIT_PER_HOST, HTTP_DNS_CACHE_TTL
)
from utils.http import _host_of, _with_retries, _safe_bg_task, get_http_session

logger = logging.getLogger(__name__)

cache: Dict[str, Any] = {}
_revalidation_lock = asyncio.Lock()
_rates_lock = asyncio.Lock()


def _as_rates_dict(payload: Any) -> Optional[Dict[str, float]]:
    return payload if isinstance(payload, dict) else None


def get_cached_data(key: str) -> Optional[Any]:
    if key in cache:
        cached_data, timestamp = cache[key]
        if time.time() - timestamp < CACHE_EXPIRATION_TIME:
            return cached_data
    return None


def set_cached_data(key: str, data: Dict[str, float]):
    cache[key] = (data, time.time())


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
                if not _revalidation_lock.locked():
                    _safe_bg_task(_bg_refresh_rates(), name="stale_refresh_rates")
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


async def _bg_refresh_rates():
    async with _revalidation_lock:
        try:
            await refresh_rates(force=True)
        except asyncio.CancelledError:
            raise
        except (RuntimeError, asyncio.TimeoutError, aiohttp.ClientError, ValueError, TypeError, KeyError):
            logger.exception("Background rate refresh failed")


async def refresh_rates(force: bool = False) -> Dict[str, float]:
    if not force:
        async with _rates_lock:
            fresh = _as_rates_dict(get_cached_data('exchange_rates'))
            if fresh:
                return fresh
            return await _fetch_rates_unlocked()
    
    async with _rates_lock:
        return await _fetch_rates_unlocked()


async def _fetch_rates_unlocked() -> Dict[str, float]:
    session_to_close = None

    try:
        from config.config import COINCAP_API_KEY

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

        rates: Dict[str, float] = {}
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

            if isinstance(fiat_data, dict):
                if fiat_data.get('result') == 'success' and 'rates' in fiat_data:
                    logger.info(f"Fetched fiat rates from {source_host}")
                    return fiat_data['rates']
                elif 'rates' in fiat_data:
                    logger.info(f"Fetched fiat rates from {source_host}")
                    return fiat_data['rates']
                elif 'usd' in fiat_data:
                    usd_rates = fiat_data['usd']
                    normalized_rates = {'USD': 1.0}
                    for curr_lower, rate in usd_rates.items():
                        curr_upper = curr_lower.upper()
                        if rate and rate > 0:
                            normalized_rates[curr_upper] = float(rate)
                    logger.info(f"Fetched fiat rates from {source_host}")
                    return normalized_rates
            return None

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
            return merged or None

        gecko_mapping = CRYPTO_ID_MAPPING['coingecko']
        crypto_ids = ','.join(gecko_mapping.values())
        url_cg = f'https://api.coingecko.com/api/v3/simple/price?ids={crypto_ids}&vs_currencies=usd'

        async def _fetch_coingecko():
            coingecko_host = _host_of(url_cg)
            async def _cg():
                resp = await session.get(url_cg, timeout=timeout)
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
                        if cg_usd_price and cg_usd_price > 0:
                            crypto_rates[cg_symbol] = 1.0 / cg_usd_price
                logger.info("Fetched crypto rates from CoinGecko")
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
                            if coincap_usd_price > 0:
                                logger.info(f"Fetched {crypto_sym} from CoinCap v3")
                                return crypto_sym, 1.0 / coincap_usd_price
                    except (RuntimeError, asyncio.TimeoutError, aiohttp.ClientError, ValueError, TypeError, KeyError) as coincap_error:
                        logger.warning(f"Failed to fetch {crypto_sym} from CoinCap v3: {coincap_error}")
                    return crypto_sym, None

                coincap_results = await asyncio.gather(
                    *(_fetch_coincap_single(c) for c in missing_crypto),
                    return_exceptions=True
                )
                for coincap_item in coincap_results:
                    if isinstance(coincap_item, tuple) and coincap_item[1] is not None:
                        rates[coincap_item[0]] = coincap_item[1]

            elif missing_crypto:
                logger.info(f"Trying CoinGecko individual requests for: {missing_crypto}")

                for crypto_symbol in missing_crypto:
                    if crypto_symbol in gecko_mapping:
                        coin_id = gecko_mapping[crypto_symbol]
                        url_gecko = f'https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd'
                        request_host = _host_of(url_gecko)

                        async def _gecko(u=url_gecko):
                            resp = await session.get(u, timeout=timeout)
                            async with resp:
                                resp.raise_for_status()
                                return await resp.json(loads=ujson.loads)

                        try:
                            gecko_data = await _with_retries(_gecko, request_host)
                            if isinstance(gecko_data, dict) and coin_id in gecko_data:
                                single_gecko_usd_price = float(gecko_data[coin_id].get('usd', 0))
                                if single_gecko_usd_price > 0:
                                    rates[crypto_symbol] = 1.0 / single_gecko_usd_price
                                    logger.info(f"Fetched {crypto_symbol} from CoinGecko")
                        except (RuntimeError, asyncio.TimeoutError, aiohttp.ClientError, ValueError, TypeError, KeyError) as gecko_error:
                            logger.warning(f"Failed to fetch {crypto_symbol} from CoinGecko: {gecko_error}")

        final_missing = all_currencies - set(rates.keys())
        if final_missing:
            logger.error(f"Still missing currencies after all attempts: {final_missing}")

        set_cached_data('exchange_rates', rates)
        logger.info(f"Successfully cached {len(rates)} exchange rates")
        return rates

    except (RuntimeError, asyncio.TimeoutError, aiohttp.ClientError, ValueError, TypeError, KeyError) as refresh_error:
        logger.error(f"Critical error in _refresh_rates: {refresh_error}")
        return {}
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
