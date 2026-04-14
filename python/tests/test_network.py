"""Tests for network security controls (network.py)."""

import pytest

from agentsentinel import NetworkGuard, NetworkPolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _guard(policy: NetworkPolicy) -> NetworkGuard:
    return NetworkGuard(policy)


# ---------------------------------------------------------------------------
# Allowlist mode
# ---------------------------------------------------------------------------

class TestAllowlistMode:
    def test_allowed_domain_passes(self):
        policy = NetworkPolicy(mode="allowlist", allowed_domains=["api.openai.com"])
        guard = _guard(policy)
        allowed, reason = guard.check_url("https://api.openai.com/v1/chat")
        assert allowed is True

    def test_unlisted_domain_blocked(self):
        policy = NetworkPolicy(mode="allowlist", allowed_domains=["api.openai.com"])
        guard = _guard(policy)
        allowed, reason = guard.check_url("https://evil.example.com/steal")
        assert allowed is False
        assert "not in allowlist" in reason

    def test_wildcard_subdomain_allowed(self):
        policy = NetworkPolicy(
            mode="allowlist",
            allowed_domains=["*.githubusercontent.com"],
            block_private_ips=False,
            block_localhost=False,
        )
        guard = _guard(policy)
        allowed, _ = guard.check_url("https://raw.githubusercontent.com/file.txt")
        assert allowed is True

    def test_wildcard_does_not_allow_parent_domain(self):
        policy = NetworkPolicy(
            mode="allowlist",
            allowed_domains=["*.example.com"],
            block_private_ips=False,
            block_localhost=False,
        )
        guard = _guard(policy)
        # "sub.example.com" should match "*.example.com"
        allowed, _ = guard.check_url("https://sub.example.com/")
        assert allowed is True
        # "evil.com" should NOT match "*.example.com"
        allowed2, _ = guard.check_url("https://evil.com/")
        assert allowed2 is False


# ---------------------------------------------------------------------------
# Blocklist mode
# ---------------------------------------------------------------------------

class TestBlocklistMode:
    def test_non_blocked_domain_passes(self):
        policy = NetworkPolicy(
            mode="blocklist",
            blocked_domains=["*.pastebin.com"],
            block_private_ips=False,
            block_localhost=False,
        )
        guard = _guard(policy)
        allowed, _ = guard.check_url("https://api.openai.com/v1/chat")
        assert allowed is True

    def test_blocked_domain_is_rejected(self):
        policy = NetworkPolicy(
            mode="blocklist",
            blocked_domains=["*.pastebin.com"],
            block_private_ips=False,
            block_localhost=False,
        )
        guard = _guard(policy)
        allowed, reason = guard.check_url("https://pastebin.com/abc123")
        assert allowed is False

    def test_blocked_subdomain_rejected(self):
        policy = NetworkPolicy(
            mode="blocklist",
            blocked_domains=["*.pastebin.com"],
            block_private_ips=False,
            block_localhost=False,
        )
        guard = _guard(policy)
        allowed, reason = guard.check_url("https://sub.pastebin.com/data")
        assert allowed is False


# ---------------------------------------------------------------------------
# Monitor mode
# ---------------------------------------------------------------------------

class TestMonitorMode:
    def test_monitor_mode_allows_all(self):
        policy = NetworkPolicy(
            mode="monitor",
            block_private_ips=False,
            block_localhost=False,
        )
        guard = _guard(policy)
        allowed, reason = guard.check_url("https://anywhere.example.com/")
        assert allowed is True
        assert "Monitor mode" in reason


# ---------------------------------------------------------------------------
# Localhost blocking
# ---------------------------------------------------------------------------

class TestLocalhostBlocking:
    def test_localhost_blocked(self):
        policy = NetworkPolicy(block_localhost=True, block_private_ips=False, mode="monitor")
        guard = _guard(policy)
        allowed, reason = guard.check_url("http://localhost:8080/api")
        assert allowed is False
        assert "Localhost" in reason

    def test_127_0_0_1_blocked(self):
        policy = NetworkPolicy(block_localhost=True, block_private_ips=False, mode="monitor")
        guard = _guard(policy)
        allowed, _ = guard.check_url("http://127.0.0.1/secret")
        assert allowed is False

    def test_localhost_allowed_when_disabled(self):
        policy = NetworkPolicy(block_localhost=False, block_private_ips=False, mode="blocklist")
        guard = _guard(policy)
        allowed, _ = guard.check_url("http://localhost:3000/")
        assert allowed is True


# ---------------------------------------------------------------------------
# Private IP blocking
# ---------------------------------------------------------------------------

class TestPrivateIPBlocking:
    def test_10_x_blocked(self):
        policy = NetworkPolicy(block_private_ips=True, block_localhost=False, mode="monitor")
        guard = _guard(policy)
        allowed, reason = guard.check_url("http://10.0.0.1/internal")
        assert allowed is False
        assert "Private IP" in reason

    def test_192_168_blocked(self):
        policy = NetworkPolicy(block_private_ips=True, block_localhost=False, mode="monitor")
        guard = _guard(policy)
        allowed, _ = guard.check_url("http://192.168.1.1/admin")
        assert allowed is False

    def test_172_16_blocked(self):
        policy = NetworkPolicy(block_private_ips=True, block_localhost=False, mode="monitor")
        guard = _guard(policy)
        allowed, _ = guard.check_url("http://172.16.0.1/")
        assert allowed is False

    def test_public_ip_not_blocked(self):
        policy = NetworkPolicy(
            block_private_ips=True,
            block_localhost=False,
            mode="allowlist",
            allowed_ips=["8.8.8.8"],
        )
        guard = _guard(policy)
        allowed, _ = guard.check_url("http://8.8.8.8/dns")
        assert allowed is True


# ---------------------------------------------------------------------------
# Request size checks
# ---------------------------------------------------------------------------

class TestRequestSizeCheck:
    def test_within_limit_passes(self):
        policy = NetworkPolicy(max_request_size_bytes=1000)
        guard = _guard(policy)
        allowed, reason = guard.check_request_size(500)
        assert allowed is True

    def test_exceeds_limit_blocked(self):
        policy = NetworkPolicy(max_request_size_bytes=1000)
        guard = _guard(policy)
        allowed, reason = guard.check_request_size(2000)
        assert allowed is False
        assert "exceeds limit" in reason

    def test_exactly_at_limit_passes(self):
        policy = NetworkPolicy(max_request_size_bytes=1000)
        guard = _guard(policy)
        allowed, _ = guard.check_request_size(1000)
        assert allowed is True


# ---------------------------------------------------------------------------
# Default blocked domains
# ---------------------------------------------------------------------------

class TestDefaultBlockedDomains:
    def test_webhook_site_blocked_by_default(self):
        policy = NetworkPolicy(mode="blocklist", block_private_ips=False, block_localhost=False)
        guard = _guard(policy)
        allowed, _ = guard.check_url("https://webhook.site/abc123")
        assert allowed is False

    def test_ngrok_blocked_by_default(self):
        policy = NetworkPolicy(mode="blocklist", block_private_ips=False, block_localhost=False)
        guard = _guard(policy)
        allowed, _ = guard.check_url("https://abc.ngrok.io/tunnel")
        assert allowed is False
