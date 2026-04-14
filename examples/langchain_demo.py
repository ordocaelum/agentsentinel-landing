"""LangChain integration demo for AgentSentinel.

This example shows how to wrap a LangChain AgentExecutor (or a bare list of
LangChain tools) with AgentSentinel policy enforcement.

Requirements:
    pip install langchain langchain-openai

Run:
    OPENAI_API_KEY=sk-... python examples/langchain_demo.py
"""

import os

# ── AgentSentinel setup ──────────────────────────────────────────────────────
from agentsentinel import AgentGuard, AgentPolicy, InMemoryAuditSink, AuditLogger
from agentsentinel.integrations.langchain import LangChainGuard, protect_langchain_agent

policy = AgentPolicy(
    daily_budget=2.0,          # Hard stop at $2 / day
    hourly_budget=0.50,        # $0.50 / hour
    require_approval=["send_email", "delete_*"],
    rate_limits={"*": "30/min"},
)

sink = InMemoryAuditSink()
guard = AgentGuard(policy=policy, audit_logger=AuditLogger(sinks=[sink]))


# ── Option A: wrap a bare list of LangChain tools ────────────────────────────
def demo_wrap_tool_list() -> None:
    """Demonstrate wrapping a list of LangChain BaseTool instances."""
    try:
        from langchain.tools import tool as lc_tool

        @lc_tool
        def search_web(query: str) -> str:
            """Search the web for information."""
            return f"Results for: {query}"

        @lc_tool
        def calculate(expression: str) -> str:
            """Evaluate a simple mathematical expression safely."""
            import ast
            try:
                tree = ast.parse(expression, mode="eval")
                # Allow only safe literal/arithmetic nodes
                allowed = (
                    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num,
                    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
                    ast.USub, ast.UAdd, ast.Constant,
                )
                for node in ast.walk(tree):
                    if not isinstance(node, allowed):
                        return "Error: unsafe expression"
                return str(eval(compile(tree, "<string>", "eval")))  # noqa: S307
            except Exception as exc:
                return f"Error: {exc}"

        tools = [search_web, calculate]

        # One-liner — mutates tools in-place and returns them
        protect_langchain_agent(tools, guard=guard)

        print("✅ Tool list wrapped successfully")
        print(f"   Tools protected: {[t.name for t in tools]}")

        # Call through the protected tools
        result = tools[0].run("AgentSentinel")
        print(f"   search_web result: {result}")

    except ImportError:
        print("⚠️  langchain not installed — skipping tool-list demo")
        print("   pip install langchain")


# ── Option B: protect an AgentExecutor ──────────────────────────────────────
def demo_protect_executor() -> None:
    """Demonstrate wrapping a full LangChain AgentExecutor."""
    try:
        from langchain.agents import AgentExecutor, create_openai_tools_agent
        from langchain.tools import tool as lc_tool
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

        @lc_tool
        def get_word_count(text: str) -> str:
            """Return the word count of a piece of text."""
            return str(len(text.split()))

        llm = ChatOpenAI(model="gpt-4o-mini")
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant."),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])

        agent = create_openai_tools_agent(llm, [get_word_count], prompt)
        executor = AgentExecutor(agent=agent, tools=[get_word_count])

        # Wrap the executor — all tools get policy enforcement
        protect_langchain_agent(executor, guard=guard)
        print("✅ AgentExecutor wrapped successfully")

        result = executor.invoke({"input": "How many words in 'hello world foo bar'?"})
        print(f"   Agent response: {result['output']}")

    except ImportError:
        print("⚠️  langchain / langchain-openai not installed — skipping executor demo")
        print("   pip install langchain langchain-openai")


# ── Option C: LangChainGuard class directly ──────────────────────────────────
def demo_class_api() -> None:
    """Demonstrate the LangChainGuard class API."""
    try:
        from langchain.tools import StructuredTool

        def reverse_string(text: str) -> str:
            """Reverse a string."""
            return text[::-1]

        tool = StructuredTool.from_function(
            func=reverse_string,
            name="reverse_string",
            description="Reverse a string",
        )

        lc_guard = LangChainGuard(guard)
        lc_guard.wrap_tools([tool])

        print("✅ StructuredTool wrapped via LangChainGuard class")
        result = tool.run({"text": "AgentSentinel"})
        print(f"   reverse_string('AgentSentinel') = {result}")

    except ImportError:
        print("⚠️  langchain not installed — skipping class API demo")


# ── Print audit summary ──────────────────────────────────────────────────────
def print_audit_summary() -> None:
    print(f"\n📋 Audit log ({len(sink.events)} events):")
    for event in sink.events:
        print(
            f"   {event.tool_name:25s} | {event.decision:22s} | "
            f"status={event.status:7s} | cost=${event.cost:.4f}"
        )


if __name__ == "__main__":
    print("═" * 60)
    print("  AgentSentinel × LangChain Integration Demo")
    print("═" * 60)

    demo_wrap_tool_list()
    print()
    demo_protect_executor()
    print()
    demo_class_api()
    print_audit_summary()
