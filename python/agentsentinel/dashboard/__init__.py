"""Local web dashboard for AgentSentinel.

Zero external dependencies — uses the Python standard-library HTTP server.

.. code-block:: python

    from agentsentinel.dashboard import start_dashboard

    guard = AgentGuard(policy=policy)
    start_dashboard(guard, port=8080)   # opens http://localhost:8080
"""

from .server import DashboardServer, start_dashboard

__all__ = ["DashboardServer", "start_dashboard"]
