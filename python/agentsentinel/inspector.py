# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Content inspection for outbound data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

from .pii import PIIScanner, PIIConfig, PIIMatch


class InspectionResult(Enum):
    """Result of content inspection."""
    ALLOW = "allow"
    BLOCK = "block"
    REDACT = "redact"
    WARN = "warn"


@dataclass
class InspectionReport:
    """Report from content inspection."""
    result: InspectionResult
    reason: str
    pii_matches: List[PIIMatch] = field(default_factory=list)
    redacted_content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InspectorConfig:
    """Configuration for content inspection.

    Parameters
    ----------
    enabled:
        Master switch for content inspection.
    pii_config:
        PII detection configuration.
    max_content_size:
        Maximum content size to inspect (larger content is blocked).
    inspect_tool_args:
        Whether to inspect tool arguments before execution.
    inspect_tool_results:
        Whether to inspect tool return values.
    block_on_pii:
        Block the request if PII is detected.
    custom_inspectors:
        Additional inspection functions: (content, tool_name) -> InspectionReport
    sensitive_data_threshold:
        Number of PII matches that triggers blocking (if block_on_pii=False).
    """
    enabled: bool = True
    pii_config: PIIConfig = field(default_factory=PIIConfig)
    max_content_size: int = 10_000_000  # 10MB
    inspect_tool_args: bool = True
    inspect_tool_results: bool = True
    block_on_pii: bool = True
    custom_inspectors: List[Callable[[Any, str], InspectionReport]] = field(default_factory=list)
    sensitive_data_threshold: int = 1


class ContentInspector:
    """Inspects content for sensitive data before allowing operations."""

    def __init__(self, config: InspectorConfig):
        self.config = config
        self.pii_scanner = PIIScanner(config.pii_config)

    def inspect(self, content: Any, tool_name: str, direction: str = "outbound") -> InspectionReport:
        """Inspect content for sensitive data.

        Parameters
        ----------
        content:
            The content to inspect (str, dict, or nested structure).
        tool_name:
            Name of the tool being used.
        direction:
            "outbound" for data leaving the system, "inbound" for responses.

        Returns
        -------
        InspectionReport
            The inspection result with details.
        """
        if not self.config.enabled:
            return InspectionReport(
                result=InspectionResult.ALLOW,
                reason="Inspection disabled"
            )

        # Check content size
        content_str = str(content)
        if len(content_str) > self.config.max_content_size:
            return InspectionReport(
                result=InspectionResult.BLOCK,
                reason=f"Content size {len(content_str)} exceeds limit {self.config.max_content_size}"
            )

        # Scan for PII
        pii_matches = self.pii_scanner.scan(content)

        if pii_matches:
            if self.config.block_on_pii or len(pii_matches) >= self.config.sensitive_data_threshold:
                return InspectionReport(
                    result=InspectionResult.BLOCK,
                    reason=f"PII detected: {len(pii_matches)} matches ({', '.join(m.pii_type.value for m in pii_matches[:3])}...)",
                    pii_matches=pii_matches,
                )
            else:
                # Redact and allow
                redacted = self.pii_scanner.redact(content_str)
                return InspectionReport(
                    result=InspectionResult.REDACT,
                    reason=f"PII redacted: {len(pii_matches)} matches",
                    pii_matches=pii_matches,
                    redacted_content=redacted,
                )

        # Run custom inspectors
        for inspector_fn in self.config.custom_inspectors:
            report = inspector_fn(content, tool_name)
            if report.result in (InspectionResult.BLOCK, InspectionResult.REDACT):
                return report

        return InspectionReport(
            result=InspectionResult.ALLOW,
            reason="Content inspection passed"
        )

    def inspect_args(self, tool_name: str, args: tuple, kwargs: dict) -> InspectionReport:
        """Inspect tool arguments before execution."""
        if not self.config.inspect_tool_args:
            return InspectionReport(result=InspectionResult.ALLOW, reason="Arg inspection disabled")

        combined = {"args": args, "kwargs": kwargs}
        return self.inspect(combined, tool_name, direction="outbound")

    def inspect_result(self, tool_name: str, result: Any) -> InspectionReport:
        """Inspect tool result after execution."""
        if not self.config.inspect_tool_results:
            return InspectionReport(result=InspectionResult.ALLOW, reason="Result inspection disabled")

        return self.inspect(result, tool_name, direction="inbound")
