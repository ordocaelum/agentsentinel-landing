# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Slack approval handler for AgentSentinel.

Sends a Block Kit message with **Approve / Deny** buttons to a Slack channel
and waits for a human response (or times out).

Zero external dependencies — uses the Python standard-library ``urllib``
for all HTTP calls.  A tiny ``http.server``-based callback server listens
for Slack's interactive-component payloads.

Usage::

    from agentsentinel import AgentGuard, AgentPolicy
    from agentsentinel.handlers.slack import SlackApprover, SlackConfig

    config = SlackConfig(
        bot_token="xoxb-...",
        channel="#agent-approvals",
        timeout_seconds=120,
    )
    approver = SlackApprover(config)
    guard = AgentGuard(policy=policy, approval_handler=approver)

When the agent requests approval:

1. A Slack message with **Approve** and **Deny** buttons is posted.
2. The approver blocks (up to *timeout_seconds*) waiting for a button click.
3. Slack sends an HTTP POST to the callback server; the response is
   forwarded to the waiting thread.
4. If the timeout expires with no response the call is **denied** by default.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

from ..approval import ApprovalHandler
from ..errors import ApprovalRequiredError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SlackConfig:
    """Configuration for the Slack approval integration.

    Parameters
    ----------
    bot_token:
        A Slack Bot Token (``xoxb-...``) with ``chat:write`` and
        ``chat:write.public`` scopes.
    channel:
        Slack channel ID or name (e.g. ``"#agent-approvals"`` or
        ``"C01AB2C3D4E"``).
    timeout_seconds:
        How long to wait for a human response before auto-denying.
        Defaults to 120 seconds.
    callback_host:
        Hostname / IP the callback HTTP server will bind to.
        Defaults to ``"0.0.0.0"`` (all interfaces).
    callback_port:
        Port the callback HTTP server listens on.
        Defaults to ``9_876``.
    default_on_timeout:
        ``"deny"`` (default) or ``"approve"`` — what to do when the
        timeout expires with no human response.
    """

    bot_token: str
    channel: str
    timeout_seconds: int = 120
    callback_host: str = "0.0.0.0"
    callback_port: int = 9_876
    default_on_timeout: str = "deny"

    # Populated at runtime — public URL the callback server is reachable at.
    # Set this to your server's external URL if running behind a proxy/ngrok.
    callback_url: Optional[str] = None

    def effective_callback_url(self) -> str:
        """Return the URL Slack will POST interactive payloads to."""
        if self.callback_url:
            return self.callback_url
        return f"http://localhost:{self.callback_port}/slack/actions"


# ---------------------------------------------------------------------------
# Pending-approval registry (shared between callback server + approver)
# ---------------------------------------------------------------------------

class _ApprovalRegistry:
    """Thread-safe registry for in-flight approval requests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # approval_id -> threading.Event
        self._events: dict[str, threading.Event] = {}
        # approval_id -> bool (True = approved)
        self._decisions: dict[str, bool] = {}

    def register(self, approval_id: str) -> threading.Event:
        event = threading.Event()
        with self._lock:
            self._events[approval_id] = event
        return event

    def resolve(self, approval_id: str, *, approved: bool) -> bool:
        """Record *approved* for *approval_id* and signal the waiting thread.

        Returns ``True`` if the ID was found, ``False`` otherwise.
        """
        with self._lock:
            if approval_id not in self._events:
                return False
            self._decisions[approval_id] = approved
            self._events[approval_id].set()
        return True

    def pop_decision(self, approval_id: str) -> Optional[bool]:
        with self._lock:
            self._events.pop(approval_id, None)
            return self._decisions.pop(approval_id, None)


# ---------------------------------------------------------------------------
# Callback HTTP server (receives Slack interactive payloads)
# ---------------------------------------------------------------------------

def _make_handler_class(registry: _ApprovalRegistry):  # type: ignore[return]
    """Return a BaseHTTPRequestHandler subclass bound to *registry*."""
    import http.server

    class _SlackCallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            content_len = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(content_len)

            try:
                # Slack sends URL-encoded ``payload=<json>``
                parsed = urllib.parse.parse_qs(raw.decode())
                payload_json = parsed.get("payload", ["{}"])[0]
                payload = json.loads(payload_json)

                action = (payload.get("actions") or [{}])[0]
                action_id: str = action.get("action_id", "")
                approval_id, _, decision_str = action_id.partition(":")
                approved = decision_str == "approve"

                registry.resolve(approval_id, approved=approved)

                # Respond with 200 + a plain confirmation message
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                msg = "Approved ✅" if approved else "Denied ❌"
                self.wfile.write(json.dumps({"text": msg}).encode())
            except Exception:
                self.send_response(400)
                self.end_headers()

        def log_message(self, *_args: object) -> None:  # suppress access logs
            pass

    return _SlackCallbackHandler


class _CallbackServer:
    """Thin wrapper around ``http.server.HTTPServer`` that starts in a daemon thread."""

    def __init__(self, host: str, port: int, registry: _ApprovalRegistry) -> None:
        import http.server

        handler_class = _make_handler_class(registry)
        self._server = http.server.HTTPServer((host, port), handler_class)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()


# ---------------------------------------------------------------------------
# Slack API helpers
# ---------------------------------------------------------------------------

def _post_approval_message(
    token: str,
    channel: str,
    tool_name: str,
    approval_id: str,
    kwargs: dict,
) -> str:
    """Post a Block Kit approval message to Slack. Returns the message ``ts``.

    The interactive buttons use ``action_id`` to carry the decision.  Slack
    POSTs the payload to the interactivity URL configured in the Slack app
    settings (or to the local callback server when ``SlackApprover`` is used
    with ``start_server=True`` and the app is configured accordingly).
    """

    # Truncate kwargs preview to avoid leaking large payloads
    kwargs_preview = json.dumps(
        {k: str(v)[:120] for k, v in list(kwargs.items())[:5]},
        indent=2,
    )

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🤖 Agent Action Requires Approval"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Tool:*\n`{tool_name}`"},
                {"type": "mrkdwn", "text": f"*Request ID:*\n`{approval_id[:8]}…`"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Arguments preview:*\n```{kwargs_preview}```",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Approve"},
                    "style": "primary",
                    "action_id": f"{approval_id}::approve",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Deny"},
                    "style": "danger",
                    "action_id": f"{approval_id}::deny",
                },
            ],
        },
    ]

    payload = json.dumps({"channel": channel, "blocks": blocks}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    # urllib uses SSL verification by default; no additional config required.
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read())
    if not body.get("ok"):
        raise RuntimeError(f"Slack API error: {body.get('error', 'unknown')}")
    return body["ts"]


# ---------------------------------------------------------------------------
# SlackApprover
# ---------------------------------------------------------------------------

class SlackApprover(ApprovalHandler):
    """Approval handler that sends a Slack Block Kit message and waits for a click.

    Parameters
    ----------
    config:
        :class:`SlackConfig` instance with bot token, channel, etc.
    start_server:
        Whether to start the local callback server automatically.
        Set to ``False`` if you manage the callback server yourself.

    Example
    -------
    ::

        config   = SlackConfig(bot_token="xoxb-...", channel="#approvals")
        approver = SlackApprover(config)
        guard    = AgentGuard(policy=policy, approval_handler=approver)
    """

    def __init__(self, config: SlackConfig, *, start_server: bool = True) -> None:
        self.config = config
        self._registry = _ApprovalRegistry()
        self._server: Optional[_CallbackServer] = None

        if start_server:
            self._server = _CallbackServer(
                config.callback_host, config.callback_port, self._registry
            )
            self._server.start()

    def stop(self) -> None:
        """Shut down the callback HTTP server."""
        if self._server is not None:
            self._server.stop()

    # ------------------------------------------------------------------
    # ApprovalHandler interface
    # ------------------------------------------------------------------

    def request_approval(self, tool_name: str, **kwargs) -> bool:
        """Post a Slack message and block until a human clicks Approve/Deny.

        Returns
        -------
        ``True`` if approved, raises :class:`.ApprovalRequiredError` if denied
        or timed-out.
        """
        import uuid
        approval_id = uuid.uuid4().hex
        event = self._registry.register(approval_id)

        try:
            _post_approval_message(
                token=self.config.bot_token,
                channel=self.config.channel,
                tool_name=tool_name,
                approval_id=approval_id,
                kwargs=kwargs,
            )
        except Exception as exc:
            self._registry.resolve(approval_id, approved=False)
            raise ApprovalRequiredError(
                f"Failed to post Slack approval request for '{tool_name}': {exc}",
                tool_name=tool_name,
            ) from exc

        # Block until the callback arrives or the timeout expires
        received = event.wait(timeout=self.config.timeout_seconds)

        decision = self._registry.pop_decision(approval_id)

        if not received or decision is None:
            # Timeout
            if self.config.default_on_timeout == "approve":
                return True
            raise ApprovalRequiredError(
                f"Approval request for '{tool_name}' timed out after "
                f"{self.config.timeout_seconds}s — defaulting to deny.",
                tool_name=tool_name,
            )

        if not decision:
            raise ApprovalRequiredError(
                f"Tool '{tool_name}' was denied via Slack.",
                tool_name=tool_name,
            )

        return True
