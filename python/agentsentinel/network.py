# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Network security controls for AgentSentinel."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import List, Tuple
from urllib.parse import urlparse


@dataclass
class NetworkPolicy:
    """Network security policy for controlling outbound connections.

    Parameters
    ----------
    mode:
        "allowlist" - only allowed_domains can be accessed
        "blocklist" - all domains except blocked_domains can be accessed
        "monitor" - log all outbound requests but don't block
    allowed_domains:
        Domains that are permitted (supports wildcards like "*.openai.com").
    blocked_domains:
        Domains that are never permitted.
    allowed_ips:
        IP addresses/ranges that are permitted.
    blocked_ips:
        IP addresses/ranges that are never permitted.
    block_private_ips:
        Block requests to private/internal IP ranges (10.x, 192.168.x, etc.).
    block_localhost:
        Block requests to localhost/127.0.0.1.
    max_request_size_bytes:
        Maximum size of outbound request body (prevents large data exfil).
    """
    mode: str = "allowlist"  # "allowlist", "blocklist", "monitor"

    allowed_domains: List[str] = field(default_factory=lambda: [
        "api.openai.com",
        "api.anthropic.com",
        "api.github.com",
        "*.githubusercontent.com",
    ])

    blocked_domains: List[str] = field(default_factory=lambda: [
        "*.pastebin.com",
        "*.requestbin.com",
        "*.webhook.site",
        "*.ngrok.io",
        "*.localtunnel.me",
    ])

    allowed_ips: List[str] = field(default_factory=list)
    blocked_ips: List[str] = field(default_factory=list)

    block_private_ips: bool = True
    block_localhost: bool = True

    max_request_size_bytes: int = 1_000_000  # 1MB default


# Private IP ranges (RFC 1918 + others)
PRIVATE_IP_PATTERNS = [
    r'^10\.',                           # 10.0.0.0/8
    r'^172\.(1[6-9]|2[0-9]|3[01])\.',  # 172.16.0.0/12
    r'^192\.168\.',                     # 192.168.0.0/16
    r'^127\.',                          # Loopback
    r'^169\.254\.',                     # Link-local
    r'^0\.',                            # "This" network
]


class NetworkGuard:
    """Enforces network security policy on outbound requests."""

    def __init__(self, policy: NetworkPolicy):
        self.policy = policy
        self._private_ip_regex = re.compile('|'.join(PRIVATE_IP_PATTERNS))

    def check_url(self, url: str) -> Tuple[bool, str]:
        """Check if a URL is allowed by the policy.

        Returns
        -------
        (allowed, reason)
            allowed: True if the request should proceed
            reason: Explanation if blocked
        """
        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        # Check localhost
        if self.policy.block_localhost:
            if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
                return False, f"Localhost access blocked: {hostname}"

        # Check private IPs
        if self.policy.block_private_ips and self._is_private_ip(hostname):
            return False, f"Private IP access blocked: {hostname}"

        # Check blocked domains (always enforced)
        for pattern in self.policy.blocked_domains:
            if self._match_domain(hostname, pattern):
                return False, f"Domain blocked by policy: {hostname} matches {pattern}"

        # Check blocked IPs
        for pattern in self.policy.blocked_ips:
            if self._match_ip(hostname, pattern):
                return False, f"IP blocked by policy: {hostname}"

        # Mode-specific checks
        if self.policy.mode == "allowlist":
            for pattern in self.policy.allowed_domains:
                if self._match_domain(hostname, pattern):
                    return True, "Domain in allowlist"
            for pattern in self.policy.allowed_ips:
                if self._match_ip(hostname, pattern):
                    return True, "IP in allowlist"
            return False, f"Domain not in allowlist: {hostname}"

        elif self.policy.mode == "blocklist":
            # Already checked blocked lists above
            return True, "Domain not in blocklist"

        else:  # monitor mode
            return True, "Monitor mode - logging only"

    def check_request_size(self, size_bytes: int) -> Tuple[bool, str]:
        """Check if request size is within limits."""
        if size_bytes > self.policy.max_request_size_bytes:
            return False, f"Request size {size_bytes} exceeds limit {self.policy.max_request_size_bytes}"
        return True, "Size OK"

    def _match_domain(self, hostname: str, pattern: str) -> bool:
        """Match hostname against a domain pattern (supports wildcards)."""
        if pattern.startswith("*."):
            # Wildcard subdomain match
            suffix = pattern[1:]  # ".example.com"
            return hostname.endswith(suffix) or hostname == pattern[2:]
        return fnmatch.fnmatch(hostname, pattern)

    def _match_ip(self, hostname: str, pattern: str) -> bool:
        """Match hostname against an IP pattern."""
        # Simple prefix match for now
        return hostname.startswith(pattern.rstrip('*'))

    def _is_private_ip(self, hostname: str) -> bool:
        """Check if hostname is a private IP address."""
        return bool(self._private_ip_regex.match(hostname))
