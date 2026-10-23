"""Bounded JSON requests, cache and per-client request budgets."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import aiohttp

from .providers.base import AuthError, ProviderError, RateLimitError


class HTTP:
    def __init__(self, session, budget=500, clock=None):
        self.session = session
        self.budget = budget
        self.clock = clock or (lambda: datetime.now(UTC))
        self.cache = {}
        self.day = None
        self.used = 0
        self.blocked_until = None
        self.lock = asyncio.Lock()

    def export_usage(self):
        return {
            "day": self.day.isoformat() if self.day else None,
            "used": self.used,
            "blocked_until": self.blocked_until.isoformat() if self.blocked_until else None,
        }

    def restore_usage(self, usage):
        try:
            from datetime import date

            self.day = date.fromisoformat(usage["day"]) if usage.get("day") else None
            self.used = max(0, int(usage.get("used", 0)))
            self.blocked_until = (
                datetime.fromisoformat(usage["blocked_until"])
                if usage.get("blocked_until")
                else None
            )
        except (ValueError, TypeError, KeyError):
            self.day, self.used, self.blocked_until = None, 0, None

    async def get(self, url, *, params=None, headers=None, auth=None, cache_seconds=300):
        async with self.lock:
            now = self.clock()
            key = (url, json.dumps(params or {}, sort_keys=True))
            if key in self.cache and self.cache[key][0] > now:
                return self.cache[key][1]
            if self.day != now.date():
                self.day, self.used = now.date(), 0
            if self.blocked_until and now < self.blocked_until:
                raise RateLimitError("Provider is backing off")
            if self.used >= self.budget:
                raise RateLimitError("Configured daily request budget reached")
            self.used += 1
            try:
                async with asyncio.timeout(20):
                    async with self.session.get(
                        url, params=params, headers=headers, auth=auth
                    ) as response:
                        if response.status in (401, 403):
                            raise AuthError("Provider credentials or product access rejected")
                        if response.status == 429:
                            try:
                                delay = min(
                                    max(int(response.headers.get("Retry-After", "60")), 1), 86400
                                )
                            except ValueError:
                                delay = 60
                            self.blocked_until = now + timedelta(seconds=delay)
                            raise RateLimitError("Provider request limit reached")
                        if response.status != 200:
                            raise ProviderError(f"Provider returned HTTP {response.status}")
                        raw = await response.content.read(2_000_001)
                        if len(raw) > 2_000_000:
                            raise ProviderError("Provider response is too large")
                        result = json.loads(raw)
                        if not isinstance(result, (dict, list)):
                            raise ProviderError("Unexpected provider response")
            except (aiohttp.ClientError, TimeoutError, ValueError):
                raise ProviderError("Provider response unavailable or invalid") from None
            self.cache[key] = (now + timedelta(seconds=cache_seconds), result)
            # Bound cache growth over a long-running Home Assistant process.
            if len(self.cache) > 500:
                self.cache = {k: v for k, v in self.cache.items() if v[0] > now}
            return result
