# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Audit logging system for AgentSentinel."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

Decision = Literal[
    "allowed",
    "blocked_budget",
    "blocked_rate_limit",
    "blocked_security",
    "approval_required",
    "approved",
    "error",
]


@dataclass
class AuditEvent:
    """A single recorded event from a protected tool invocation.

    Attributes
    ----------
    timestamp:
        Unix epoch time (seconds) when the event was created.
    tool_name:
        The name of the tool that was invoked.
    status:
        ``"success"`` or ``"error"`` after execution; ``"blocked"`` when
        the call was prevented before reaching the tool.
    cost:
        Estimated or explicit cost (USD) of this invocation.
    decision:
        Outcome classification (see :data:`Decision`).
    metadata:
        Arbitrary key/value pairs for additional context.
    """

    timestamp: float
    tool_name: str
    status: str
    cost: float
    decision: Decision
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def now(
        cls,
        tool_name: str,
        status: str,
        cost: float,
        decision: Decision,
        **metadata: Any,
    ) -> "AuditEvent":
        """Create an :class:`AuditEvent` timestamped to the current moment."""
        return cls(
            timestamp=time.time(),
            tool_name=tool_name,
            status=status,
            cost=cost,
            decision=decision,
            metadata=metadata,
        )


class AuditSink(ABC):
    """Abstract base for audit event destinations."""

    @abstractmethod
    def record(self, event: AuditEvent) -> None:
        """Persist or forward *event*."""


class ConsoleAuditSink(AuditSink):
    """Prints every :class:`AuditEvent` to *stdout*."""

    def record(self, event: AuditEvent) -> None:
        import datetime

        ts = datetime.datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"[AgentSentinel] {ts} | {event.tool_name:30s} | "
            f"{event.decision:22s} | status={event.status:7s} | cost=${event.cost:.4f}"
        )


class InMemoryAuditSink(AuditSink):
    """Stores events in-memory — useful for testing and demos."""

    def __init__(self) -> None:
        self.events: List[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)

    def clear(self) -> None:
        """Remove all stored events."""
        self.events.clear()


class AuditLogger:
    """Manages one or more :class:`AuditSink` instances.

    Parameters
    ----------
    sinks:
        Initial list of sinks to write to.  If empty, a
        :class:`ConsoleAuditSink` is added automatically.
    """

    def __init__(self, sinks: Optional[List[AuditSink]] = None) -> None:
        self._sinks: List[AuditSink] = list(sinks) if sinks else [ConsoleAuditSink()]

    def add_sink(self, sink: AuditSink) -> None:
        """Attach *sink* so it receives future events."""
        self._sinks.append(sink)

    def remove_sink(self, sink: AuditSink) -> None:
        """Detach *sink*."""
        self._sinks.remove(sink)

    def record(self, event: AuditEvent) -> None:
        """Broadcast *event* to all registered sinks."""
        for sink in self._sinks:
            sink.record(event)
