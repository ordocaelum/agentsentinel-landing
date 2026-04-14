"""In-memory rate limiter using a sliding-window approach."""

from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, Tuple

from .errors import RateLimitExceededError


def _parse_limit(limit_str: str) -> Tuple[int, float]:
    """Parse a rate-limit string like ``"10/min"`` or ``"100/hour"``.

    Returns
    -------
    (max_calls, window_seconds)
        *max_calls* is the maximum number of calls allowed in
        *window_seconds* seconds.

    Raises
    ------
    ValueError
        If *limit_str* cannot be parsed.
    """
    parts = limit_str.strip().split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid rate limit format: {limit_str!r}. Expected '<N>/min' or '<N>/hour'.")

    count_str, unit = parts[0].strip(), parts[1].strip().lower()
    try:
        count = int(count_str)
    except ValueError:
        raise ValueError(f"Invalid rate limit count: {count_str!r}")

    if unit in ("min", "minute", "minutes"):
        window = 60.0
    elif unit in ("hour", "hours"):
        window = 3600.0
    elif unit in ("sec", "second", "seconds"):
        window = 1.0
    else:
        raise ValueError(f"Unknown rate limit unit: {unit!r}. Use 'sec', 'min', or 'hour'.")

    return count, window


class RateLimiter:
    """Per-tool sliding-window rate limiter.

    Each tool tracked by this limiter maintains a deque of call
    timestamps.  On each :meth:`check` call, timestamps outside the
    window are evicted and the current count is compared against the
    configured maximum.

    Parameters
    ----------
    limits:
        Mapping of tool-name patterns to limit strings (``"10/min"``).
        The key ``"*"`` is used as a global default for tools that do not
        match any other entry.

    Example
    -------
    ::

        limiter = RateLimiter({"search_web": "10/min", "*": "100/hour"})
        limiter.check("search_web")   # raises RateLimitExceededError if exceeded
    """

    def __init__(self, limits: Dict[str, str]) -> None:
        self._parsed: Dict[str, Tuple[int, float]] = {
            pattern: _parse_limit(limit_str) for pattern, limit_str in limits.items()
        }
        self._windows: Dict[str, Deque[float]] = {}

    def _get_limit(self, tool_name: str) -> Tuple[int, float] | None:
        """Return ``(max_calls, window_seconds)`` for *tool_name*, or ``None``."""
        import fnmatch

        # Exact match takes priority over wildcards.
        if tool_name in self._parsed:
            return self._parsed[tool_name]

        for pattern, limit in self._parsed.items():
            if pattern != tool_name and fnmatch.fnmatch(tool_name, pattern):
                return limit

        return None

    def check(self, tool_name: str) -> None:
        """Assert that *tool_name* is within its rate limit.

        Records the current call timestamp and raises
        :class:`.RateLimitExceededError` if the window is full.

        Parameters
        ----------
        tool_name:
            The tool being invoked.

        Raises
        ------
        RateLimitExceededError
            When the configured rate is exceeded.
        """
        limit = self._get_limit(tool_name)
        if limit is None:
            return  # No limit configured — always allowed.

        max_calls, window = limit
        now = time.monotonic()

        if tool_name not in self._windows:
            self._windows[tool_name] = deque()

        window_deque: Deque[float] = self._windows[tool_name]

        # Evict timestamps outside the current window.
        cutoff = now - window
        while window_deque and window_deque[0] <= cutoff:
            window_deque.popleft()

        if len(window_deque) >= max_calls:
            unit = "min" if window == 60.0 else ("hour" if window == 3600.0 else "sec")
            raise RateLimitExceededError(
                f"Rate limit exceeded for '{tool_name}': {max_calls}/{unit}.",
                tool_name=tool_name,
                limit=f"{max_calls}/{unit}",
            )

        window_deque.append(now)

    def reset(self, tool_name: str | None = None) -> None:
        """Clear sliding-window state.

        Parameters
        ----------
        tool_name:
            If given, resets only that tool's window.
            If ``None``, resets all windows.
        """
        if tool_name is None:
            self._windows.clear()
        else:
            self._windows.pop(tool_name, None)
