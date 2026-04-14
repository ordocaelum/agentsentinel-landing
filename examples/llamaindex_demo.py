"""Demo: AgentSentinel + LlamaIndex integration.

Requirements:
    pip install llama-index

Run:
    python examples/llamaindex_demo.py
"""

from agentsentinel import AgentGuard, AgentPolicy, InMemoryAuditSink, AuditLogger
from agentsentinel.integrations.llamaindex import LlamaIndexGuard, protect_query_engine

# ── Policy & Guard setup ──────────────────────────────────────────────────────

policy = AgentPolicy(
    daily_budget=10.0,
    model_budgets={"gpt-4o": 5.0},
)

sink = InMemoryAuditSink()
guard = AgentGuard(policy=policy, audit_logger=AuditLogger(sinks=[sink]))
llama_guard = LlamaIndexGuard(guard)

# ── Define protected tools ────────────────────────────────────────────────────

@llama_guard.tool(model="gpt-4o")
def query_knowledge_base(query: str) -> str:
    """Query the knowledge base."""
    return f"Knowledge base results for: {query}"


@llama_guard.tool(cost=0.005, model="gpt-4o")
def summarize_document(doc_id: str) -> str:
    """Summarize a document by ID."""
    return f"Summary of document {doc_id}"


# ── QueryEngine wrapper demo (no actual LlamaIndex needed) ───────────────────

class _MockQueryEngine:
    """Stand-in for a real LlamaIndex QueryEngine."""
    def query(self, query_str: str) -> str:
        return f"Mock results for: {query_str}"


mock_engine = _MockQueryEngine()
protected_engine = protect_query_engine(
    mock_engine,
    guard=guard,
    name="knowledge_base",
)

# ── Demo ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("LlamaIndex tools protected with AgentSentinel!")
    print(f"Daily budget: ${policy.daily_budget}")

    result = query_knowledge_base("What is AgentSentinel?")
    print(f"\nquery_knowledge_base: {result}")

    result = summarize_document("doc-42")
    print(f"summarize_document: {result}")

    result = protected_engine.query("latest research papers")
    print(f"protected query_engine: {result}")

    print(f"\nAudit events recorded: {len(sink.events)}")
    for event in sink.events:
        print(f"  [{event.status}] {event.tool_name} — cost=${event.cost:.4f}")

    print("\n✅ LlamaIndex integration demo complete.")
