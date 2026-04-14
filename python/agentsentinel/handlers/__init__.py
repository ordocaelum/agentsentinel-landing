# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Additional approval handlers for AgentSentinel.

Optional modules — import only when the matching service is configured.

.. code-block:: python

    # Slack (uses stdlib urllib — no extra dependencies)
    from agentsentinel.handlers.slack import SlackApprover, SlackConfig
"""
