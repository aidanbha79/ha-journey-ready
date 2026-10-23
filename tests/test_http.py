import json
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.journey_ready.http import HTTP
from custom_components.journey_ready.providers.base import AuthError, ProviderError, RateLimitError


class Response:
    def __init__(self, status=200, data=None, headers=None, raw=None):
        self.status, self.headers = status, headers or {}
        self.raw = raw if raw is not None else json.dumps(data or {"ok": True}).encode()
        self.content = self

    async def read(self, limit):
        return self.raw[:limit]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class Session:
    def __init__(self, response):
        self.response, self.calls = response, 0

    def get(self, *args, **kwargs):
        self.calls += 1
        return self.response


@pytest.mark.asyncio
async def test_cache_avoids_spending_budget():
    session = Session(Response())
    http = HTTP(session, budget=1)
    assert await http.get("https://example.test") == {"ok": True}
    assert await http.get("https://example.test") == {"ok": True}
    with pytest.raises(RateLimitError):
        await http.get("https://other.test")
    assert session.calls == 1


@pytest.mark.asyncio
async def test_429_obeys_retry_after():
    now = [datetime(2026, 10, 23, tzinfo=UTC)]
    session = Session(Response(429, headers={"Retry-After": "120"}))
    http = HTTP(session, clock=lambda: now[0])
    with pytest.raises(RateLimitError):
        await http.get("https://example.test")
    session.response = Response()
    now[0] += timedelta(seconds=60)
    with pytest.raises(RateLimitError):
        await http.get("https://example.test")
    assert session.calls == 1
    now[0] += timedelta(seconds=61)
    assert await http.get("https://example.test") == {"ok": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_access_errors_are_safe(status):
    http = HTTP(Session(Response(status)))
    with pytest.raises(AuthError) as error:
        await http.get("https://example.test?key=private")
    assert "private" not in str(error.value)


@pytest.mark.asyncio
async def test_invalid_json_is_not_cached():
    session = Session(Response(raw=b"broken"))
    http = HTTP(session)
    with pytest.raises(ProviderError):
        await http.get("https://example.test")
    session.response = Response()
    assert await http.get("https://example.test") == {"ok": True}
