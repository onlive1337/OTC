import asyncio
from unittest.mock import AsyncMock

import aiohttp
import pytest

from utils import http


@pytest.mark.parametrize('status', [400, 401, 403, 404])
def test_permanent_http_errors_are_not_retried(status):
    request = AsyncMock(side_effect=aiohttp.ClientResponseError(None, (), status=status))
    with pytest.raises(aiohttp.ClientResponseError):
        asyncio.run(http._with_retries(request, 'permanent-error.example'))
    assert request.await_count == 1


@pytest.mark.parametrize('status', [408, 429, 500, 503])
def test_transient_errors_retry_the_request(monkeypatch, status):
    error = aiohttp.ClientResponseError(None, (), status=status, headers={'Retry-After': '2'})
    request = AsyncMock(side_effect=[error, {'ok': True}])
    sleep = AsyncMock()
    monkeypatch.setattr(http.asyncio, 'sleep', sleep)
    assert asyncio.run(http._with_retries(request, 'transient-error.example')) == {'ok': True}
    assert request.await_count == 2
    if status == 429:
        sleep.assert_awaited_once_with(2.0)


@pytest.mark.parametrize('value', ['nan', 'inf', 'invalid'])
def test_invalid_retry_after_is_bounded(value):
    error = aiohttp.ClientResponseError(None, (), status=429, headers={'Retry-After': value})
    assert 0.5 <= http._retry_delay_from_429(error, 0) <= 0.7
