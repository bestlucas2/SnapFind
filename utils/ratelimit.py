"""In-memory fixed-window throttle for login attempts.

Guards against password brute force / credential stuffing. Tripping *either*
the per-IP or the per-email counter blocks further attempts for a cooldown,
so a single attacker IP can't spray many accounts and a single account can't
be hammered from many IPs.

State is per-process — fine for the single-instance deploy and it resets on
restart. That's acceptable: an attacker mid-attack keeps sending requests,
which keeps the instance awake, so the counters persist for the window that
matters. (Move to Redis/DB if you ever run multiple instances.)

Note the deliberate trade-off: per-email locking lets someone temporarily lock
a victim out by failing their login on purpose, so the cooldown is kept short
(minutes) rather than a hard, long account lock.
"""
from __future__ import annotations

import threading
import time

from config import settings


class _Throttle:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key -> (window_start_epoch, fail_count, locked_until_epoch)
        self._state: dict[str, tuple[float, int, float]] = {}

    def _prune(self, now: float) -> None:
        window = settings.login_window_seconds
        stale = [
            k
            for k, (start, _count, locked) in self._state.items()
            if locked < now and (now - start) > window
        ]
        for k in stale:
            del self._state[k]

    def blocked_seconds(self, *keys: str) -> int:
        """Seconds remaining if any key is currently locked out, else 0."""
        now = time.time()
        with self._lock:
            self._prune(now)
            remaining = 0
            for k in keys:
                entry = self._state.get(k)
                if entry and entry[2] > now:
                    remaining = max(remaining, int(entry[2] - now) + 1)
            return remaining

    def record_failure(self, *keys: str) -> None:
        now = time.time()
        window = settings.login_window_seconds
        limit = settings.login_max_attempts
        lockout = settings.login_lockout_seconds
        with self._lock:
            for k in keys:
                start, count, locked = self._state.get(k, (now, 0, 0.0))
                if now - start > window:  # window elapsed → start fresh
                    start, count = now, 0
                count += 1
                if count >= limit:
                    locked = now + lockout
                self._state[k] = (start, count, locked)

    def reset(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._state.pop(k, None)


_throttle = _Throttle()


def client_ip(request) -> str:
    """Best-effort client IP, honoring the proxy's X-Forwarded-For (Render)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def login_block_seconds(ip: str, email: str) -> int:
    return _throttle.blocked_seconds(f"ip:{ip}", f"email:{email}")


def record_login_failure(ip: str, email: str) -> None:
    _throttle.record_failure(f"ip:{ip}", f"email:{email}")


def record_login_success(ip: str, email: str) -> None:
    _throttle.reset(f"ip:{ip}", f"email:{email}")
