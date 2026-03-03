import asyncio
import logging
import random
import urllib.parse
from typing import Dict, Optional

import aiohttp

from config.config import HTTP_RETRIES, SEMAPHORE_LIMITS

logger = logging.getLogger(__name__)

_http_session: Optional[aiohttp.ClientSession] = None
_domain_semaphores: Dict[str, asyncio.Semaphore] = {}


def set_http_session(session: aiohttp.ClientSession):
    global _http_session
    _http_session = session


async def close_http_session():
    global _http_session
    if _http_session is not None:
        try:
            await _http_session.close()
        finally:
            _http_session = None


def get_http_session() -> Optional[aiohttp.ClientSession]:
    return _http_session


def _host_of(url: str) -> str:
    return urllib.parse.urlparse(url).netloc


def _get_semaphore(host: str) -> asyncio.Semaphore:
    if host not in _domain_semaphores:
        _domain_semaphores[host] = asyncio.Semaphore(SEMAPHORE_LIMITS.get(host, 5))
    return _domain_semaphores[host]


async def _with_retries(coro_factory, host: str, retries: int = HTTP_RETRIES):
    last_exc = None
    sem = _get_semaphore(host)
    for attempt in range(retries + 1):
        try:
            async with sem:
                return await coro_factory()
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            last_exc = e
            if attempt == retries:
                break
            await asyncio.sleep(0.3 * (2 ** attempt) + random.random() * 0.2)
    if last_exc:
        raise last_exc
    raise RuntimeError("_with_retries failed without exception")


def _safe_bg_task(coro, name: str = "background"):
    task = asyncio.create_task(coro, name=name)
    def _on_done(t: asyncio.Task):
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.error(f"Background task '{name}' failed: {exc}", exc_info=exc)
    task.add_done_callback(_on_done)
    return task
