"""Security utilities for AgentSentinel."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class SecurityConfig:
    """Security configuration for AgentSentinel.

    Parameters
    ----------
    redact_patterns:
        Regular-expression patterns to redact from audit log output.
        Defaults to common credential patterns (API keys, passwords, tokens).
    blocked_tools:
        Tools that are **always** blocked — they will never execute,
        regardless of approvals.  Supports ``fnmatch``-style wildcards.
        Use this as an emergency kill-list for catastrophic operations.
    sensitive_tools:
        Tools that always require explicit human approval even if they are
        not listed in :attr:`.AgentPolicy.require_approval`.  Defaults to
        a curated list of high-risk operations (shell execution, file
        deletion, financial actions, etc.).
    max_param_log_size:
        Maximum number of characters captured per parameter in audit logs.
        Prevents large payloads (file contents, model outputs) from
        bloating the audit trail.
    log_full_params:
        When ``False`` (the default) parameter values are truncated to
        *max_param_log_size* characters and sensitive patterns are
        redacted before logging.  Set to ``True`` only in secure,
        controlled environments.
    """

    # Patterns to redact from audit logs (e.g., API keys, passwords)
    redact_patterns: List[str] = field(default_factory=lambda: [
        r'api[_-]?key["\']?\s*[:=]\s*["\']?[\w-]+',
        r'password["\']?\s*[:=]\s*["\']?[^\s"\']+',
        r'secret["\']?\s*[:=]\s*["\']?[\w-]+',
        r'token["\']?\s*[:=]\s*["\']?[\w-]+',
        r'bearer\s+[\w-]+',
    ])

    # Tools that are ALWAYS blocked (emergency kill list)
    blocked_tools: List[str] = field(default_factory=list)

    # Tools that require approval even if not in policy.require_approval
    sensitive_tools: List[str] = field(default_factory=lambda: [
        "execute_shell",
        "run_command",
        "delete_file",
        "rm_rf",
        "drop_table",
        "send_email",
        "post_tweet",
        "make_payment",
    ])

    # Maximum parameter size to log (prevents memory issues with large payloads)
    max_param_log_size: int = 1000

    # Whether to log full parameters (False = redact/truncate by default)
    log_full_params: bool = False


def redact_sensitive(text: str, patterns: List[str]) -> str:
    """Redact sensitive information from *text* using *patterns*.

    Each pattern is compiled with :data:`re.IGNORECASE` so credential
    names are matched regardless of capitalisation.

    Parameters
    ----------
    text:
        The string to sanitise.
    patterns:
        List of regular-expression patterns whose matches are replaced
        with the literal string ``'[REDACTED]'``.

    Returns
    -------
    str
        A copy of *text* with all sensitive matches replaced.
    """
    result = text
    for pattern in patterns:
        result = re.sub(pattern, "[REDACTED]", result, flags=re.IGNORECASE)
    return result


def is_tool_blocked(tool_name: str, blocked_list: List[str]) -> bool:
    """Return ``True`` if *tool_name* matches any entry in *blocked_list*.

    Matching uses :func:`fnmatch.fnmatch` so entries like ``"delete_*"``
    block any tool whose name starts with ``delete_``.

    Parameters
    ----------
    tool_name:
        The name of the tool being checked.
    blocked_list:
        Patterns to match against (exact names or fnmatch wildcards).
    """
    return any(fnmatch.fnmatch(tool_name, pattern) for pattern in blocked_list)
