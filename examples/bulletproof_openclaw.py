"""
Bulletproof OpenClaw Configuration
==================================

This example shows the maximum-security configuration for OpenClaw
agents that may have access to sensitive data (credit cards,
personal info, private keys, etc.).
"""

from agentsentinel import (
    AgentGuard,
    AgentPolicy,
    ContentInspectionError,
    InspectorConfig,
    NetworkPolicy,
    PIIConfig,
    PIIDetectedError,
    PIIType,
    SecurityConfig,
)

# ---------------------------------------------------------------------------
# Maximum-security PII detection
# ---------------------------------------------------------------------------

pii_config = PIIConfig(
    enabled=True,
    block_on_detection=True,
    detect_types=[
        PIIType.CREDIT_CARD,
        PIIType.SSN,
        PIIType.PRIVATE_KEY,
        PIIType.API_KEY,
        PIIType.AWS_CREDENTIALS,
        PIIType.BANK_ACCOUNT,
        PIIType.CRYPTO_WALLET,
    ],
    min_confidence=0.7,
)

# ---------------------------------------------------------------------------
# Strict outbound network policy — only allow known-good AI APIs
# ---------------------------------------------------------------------------

network_policy = NetworkPolicy(
    mode="allowlist",
    allowed_domains=[
        "api.openai.com",
        "api.anthropic.com",
    ],
    blocked_domains=[
        "*.pastebin.com",
        "*.webhook.site",
        "*.ngrok.io",
        "*.requestbin.com",
    ],
    block_private_ips=True,
    block_localhost=True,
    max_request_size_bytes=100_000,  # 100 KB max outbound
)

# ---------------------------------------------------------------------------
# Content inspection — scan args & results for PII
# ---------------------------------------------------------------------------

inspector_config = InspectorConfig(
    enabled=True,
    pii_config=pii_config,
    inspect_tool_args=True,
    inspect_tool_results=True,
    block_on_pii=True,
)

# ---------------------------------------------------------------------------
# Security config — block dangerous tools, require approval for sensitive ones
# ---------------------------------------------------------------------------

security = SecurityConfig(
    blocked_tools=["rm_rf", "drop_database", "format_disk"],
    sensitive_tools=["execute_shell", "write_file", "http_post", "send_email"],
)

# ---------------------------------------------------------------------------
# Assemble the full policy
# ---------------------------------------------------------------------------

policy = AgentPolicy(
    daily_budget=5.00,
    hourly_budget=1.00,
    require_approval=["http_post", "send_email", "execute_shell"],
    rate_limits={"*": "50/hour"},
    security=security,
    pii_config=pii_config,
    network_policy=network_policy,
    inspector_config=inspector_config,
    dlp_enabled=True,
    dlp_block_on_violation=True,
    sandbox_mode=True,
)

guard = AgentGuard(policy=policy)

# ---------------------------------------------------------------------------
# Wrap your OpenClaw tools with @guard.protect
# ---------------------------------------------------------------------------


@guard.protect(tool_name="search_web", cost=0.001)
def search_web(query: str) -> str:
    """Safe: no PII in a search query."""
    return f"[search results for '{query}']"


@guard.protect(tool_name="send_payment", cost=0.0)
def send_payment(card_number: str, amount: float) -> str:
    """This will be blocked — credit card number detected in args."""
    return f"Charged ${amount}"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Safe call — passes all checks
    result = search_web("latest AI safety research")
    print(f"Search result: {result}")

    # Unsafe call — blocked by PII detection
    try:
        send_payment("4532015112830366", 99.99)
    except PIIDetectedError as e:
        print(f"Blocked! PIIDetectedError: {e}")
        print(f"  Tool: {e.tool_name}, PII types: {e.pii_types}")

    # Example of blocking a result with PII
    @guard.protect(tool_name="fetch_user_data")
    def fetch_user_data(user_id: int) -> str:
        # This simulates a tool that accidentally returns sensitive data
        return f"User {user_id}: SSN 123-45-6789"

    try:
        fetch_user_data(42)
    except ContentInspectionError as e:
        print(f"Blocked! ContentInspectionError: {e}")
        print(f"  Tool: {e.tool_name}, Reason: {e.reason}")
