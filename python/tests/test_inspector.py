"""Tests for content inspection (inspector.py)."""

import pytest

from agentsentinel import (
    AgentGuard,
    AgentPolicy,
    ContentInspectionError,
    ContentInspector,
    InMemoryAuditSink,
    AuditLogger,
    InspectionResult,
    InspectorConfig,
    PIIConfig,
    PIIDetectedError,
    PIIType,
)
from agentsentinel.inspector import InspectionReport


# ---------------------------------------------------------------------------
# ContentInspector direct tests
# ---------------------------------------------------------------------------

class TestContentInspectorDirect:
    def test_clean_content_allowed(self):
        inspector = ContentInspector(InspectorConfig())
        report = inspector.inspect("Hello, world!", "my_tool")
        assert report.result == InspectionResult.ALLOW

    def test_pii_in_string_blocked(self):
        inspector = ContentInspector(InspectorConfig(
            pii_config=PIIConfig(detect_types=[PIIType.CREDIT_CARD]),
        ))
        report = inspector.inspect("Card: 4532015112830366", "payment_tool")
        assert report.result == InspectionResult.BLOCK
        assert len(report.pii_matches) > 0

    def test_pii_blocked_includes_type_in_reason(self):
        inspector = ContentInspector(InspectorConfig(
            pii_config=PIIConfig(detect_types=[PIIType.SSN]),
        ))
        report = inspector.inspect("SSN: 123-45-6789", "tool")
        assert report.result == InspectionResult.BLOCK
        assert "ssn" in report.reason.lower() or "PII" in report.reason

    def test_content_size_limit_enforced(self):
        inspector = ContentInspector(InspectorConfig(max_content_size=10))
        report = inspector.inspect("This is definitely longer than 10 chars", "tool")
        assert report.result == InspectionResult.BLOCK
        assert "size" in report.reason.lower()

    def test_inspection_disabled_always_allows(self):
        inspector = ContentInspector(InspectorConfig(enabled=False))
        report = inspector.inspect("SSN: 123-45-6789", "tool")
        assert report.result == InspectionResult.ALLOW

    def test_block_on_pii_false_redacts_instead(self):
        config = InspectorConfig(
            block_on_pii=False,
            sensitive_data_threshold=999,  # never block by threshold
            pii_config=PIIConfig(detect_types=[PIIType.SSN]),
        )
        inspector = ContentInspector(config)
        report = inspector.inspect("SSN: 123-45-6789", "tool")
        assert report.result == InspectionResult.REDACT
        assert report.redacted_content is not None
        assert "123-45-6789" not in report.redacted_content


# ---------------------------------------------------------------------------
# ContentInspector — args and result inspection
# ---------------------------------------------------------------------------

class TestInspectArgsAndResult:
    def test_inspect_args_with_pii_blocked(self):
        inspector = ContentInspector(InspectorConfig(
            pii_config=PIIConfig(detect_types=[PIIType.CREDIT_CARD]),
        ))
        report = inspector.inspect_args("my_tool", ("4532015112830366",), {})
        assert report.result == InspectionResult.BLOCK

    def test_inspect_args_disabled_always_allows(self):
        inspector = ContentInspector(InspectorConfig(inspect_tool_args=False))
        report = inspector.inspect_args("my_tool", ("4532015112830366",), {})
        assert report.result == InspectionResult.ALLOW

    def test_inspect_result_with_pii_blocked(self):
        inspector = ContentInspector(InspectorConfig(
            pii_config=PIIConfig(detect_types=[PIIType.SSN]),
        ))
        report = inspector.inspect_result("my_tool", "SSN: 123-45-6789")
        assert report.result == InspectionResult.BLOCK

    def test_inspect_result_disabled_always_allows(self):
        inspector = ContentInspector(InspectorConfig(inspect_tool_results=False))
        report = inspector.inspect_result("my_tool", "SSN: 123-45-6789")
        assert report.result == InspectionResult.ALLOW


# ---------------------------------------------------------------------------
# ContentInspector — custom inspectors
# ---------------------------------------------------------------------------

class TestCustomInspectors:
    def test_custom_inspector_can_block(self):
        def bad_word_inspector(content, tool_name):
            if "forbidden" in str(content):
                return InspectionReport(result=InspectionResult.BLOCK, reason="Forbidden word")
            return InspectionReport(result=InspectionResult.ALLOW, reason="OK")

        inspector = ContentInspector(InspectorConfig(
            pii_config=PIIConfig(enabled=False),
            custom_inspectors=[bad_word_inspector],
        ))
        report = inspector.inspect("This contains forbidden content", "tool")
        assert report.result == InspectionResult.BLOCK
        assert report.reason == "Forbidden word"

    def test_custom_inspector_not_called_when_pii_blocks_first(self):
        called = []

        def custom(content, tool_name):
            called.append(True)
            return InspectionReport(result=InspectionResult.ALLOW, reason="OK")

        inspector = ContentInspector(InspectorConfig(
            pii_config=PIIConfig(detect_types=[PIIType.SSN]),
            custom_inspectors=[custom],
        ))
        report = inspector.inspect("SSN: 123-45-6789", "tool")
        assert report.result == InspectionResult.BLOCK
        # Custom inspector should NOT be called if PII already blocked it
        assert len(called) == 0


# ---------------------------------------------------------------------------
# Integration: AgentGuard + DLP
# ---------------------------------------------------------------------------

def _make_guard(policy, approver=None):
    sink = InMemoryAuditSink()
    logger = AuditLogger(sinks=[sink])
    guard = AgentGuard(policy=policy, approval_handler=approver, audit_logger=logger)
    return guard, sink


class TestGuardDLPIntegration:
    def test_guard_blocks_pii_in_args(self):
        policy = AgentPolicy(
            dlp_enabled=True,
            dlp_block_on_violation=True,
            inspector_config=InspectorConfig(
                pii_config=PIIConfig(detect_types=[PIIType.CREDIT_CARD]),
                inspect_tool_results=False,
            ),
        )
        guard, sink = _make_guard(policy)

        @guard.protect(tool_name="send_payment")
        def send_payment(card_number):
            return f"Charged {card_number}"

        with pytest.raises(PIIDetectedError) as exc_info:
            send_payment("4532015112830366")

        assert exc_info.value.tool_name == "send_payment"
        assert "credit_card" in exc_info.value.pii_types
        # Should have audit event
        blocked_events = [e for e in sink.events if e.decision == "blocked_pii"]
        assert len(blocked_events) == 1

    def test_guard_blocks_pii_in_result(self):
        policy = AgentPolicy(
            dlp_enabled=True,
            dlp_block_on_violation=True,
            inspector_config=InspectorConfig(
                pii_config=PIIConfig(detect_types=[PIIType.SSN]),
                inspect_tool_args=False,
            ),
        )
        guard, sink = _make_guard(policy)

        @guard.protect(tool_name="fetch_user")
        def fetch_user(user_id):
            return f"User info: SSN 123-45-6789"

        with pytest.raises(ContentInspectionError) as exc_info:
            fetch_user(42)

        assert exc_info.value.tool_name == "fetch_user"
        blocked_events = [e for e in sink.events if e.decision == "blocked_content"]
        assert len(blocked_events) == 1

    def test_guard_dlp_disabled_allows_pii(self):
        policy = AgentPolicy(
            dlp_enabled=False,
            inspector_config=InspectorConfig(
                pii_config=PIIConfig(detect_types=[PIIType.CREDIT_CARD]),
            ),
        )
        guard, sink = _make_guard(policy)

        @guard.protect(tool_name="send_payment")
        def send_payment(card_number):
            return f"Charged {card_number}"

        result = send_payment("4532015112830366")
        assert result == "Charged 4532015112830366"

    def test_guard_clean_data_passes(self):
        policy = AgentPolicy(
            dlp_enabled=True,
            dlp_block_on_violation=True,
            inspector_config=InspectorConfig(
                pii_config=PIIConfig(detect_types=[PIIType.CREDIT_CARD, PIIType.SSN]),
            ),
        )
        guard, sink = _make_guard(policy)

        @guard.protect(tool_name="search_web")
        def search_web(query):
            return f"Results for: {query}"

        result = search_web("latest AI news")
        assert "Results for" in result
        success_events = [e for e in sink.events if e.decision == "allowed"]
        assert len(success_events) == 1
