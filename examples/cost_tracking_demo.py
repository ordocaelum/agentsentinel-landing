"""Demo: Cost tracking across multiple models."""

from agentsentinel import AgentPolicy, AgentGuard
from agentsentinel.pricing import list_all_providers, list_models_by_provider, MODEL_PRICING
from agentsentinel.cost_tracker import CostTrackerConfig

# Show all supported models
print("🛡️  AgentSentinel Supported Models\n")
for provider in list_all_providers():
    models = list_models_by_provider(provider)
    if models:
        print(f"  {provider.value}: {len(models)} models")

print(f"\n  Total: {len(MODEL_PRICING)} models supported!\n")

# Create policy with per-model budgets
policy = AgentPolicy(
    daily_budget=20.00,
    model_budgets={
        "gpt-4o": 10.00,        # Max $10/day on GPT-4o
        "claude-*": 5.00,       # Max $5/day on any Claude model
        "gpt-4o-mini": 3.00,    # Max $3/day on GPT-4o-mini
    },
    cost_tracking=CostTrackerConfig(
        enabled=True,
        track_by_model=True,
        track_by_tool=True,
    ),
)

guard = AgentGuard(policy)


# Simulate calls to different models
@guard.protect(model="gpt-4o")
def call_gpt4o(prompt: str) -> str:
    # Simulate: would call OpenAI
    return f"GPT-4o response to: {prompt}"


@guard.protect(model="claude-3-5-sonnet")
def call_claude(prompt: str) -> str:
    # Simulate: would call Anthropic
    return f"Claude response to: {prompt}"


@guard.protect(model="gemini-2.5-pro")
def call_gemini(prompt: str) -> str:
    # Simulate: would call Google
    return f"Gemini response to: {prompt}"


# Run some calls and manually record token usage to demonstrate cost tracking
import time

print("Running simulated model calls...\n")
for i in range(3):
    call_gpt4o(f"Question {i}")
    # Manually record token usage (in real usage, you'd call record_usage after getting the response)
    guard.cost_tracker.record_usage("gpt-4o", input_tokens=500, output_tokens=200, tool_name="call_gpt4o")

    call_claude(f"Question {i}")
    guard.cost_tracker.record_usage("claude-3-5-sonnet", input_tokens=600, output_tokens=300, tool_name="call_claude")

    call_gemini(f"Question {i}")
    guard.cost_tracker.record_usage("gemini-2.5-pro", input_tokens=400, output_tokens=150, tool_name="call_gemini")

    time.sleep(0.1)

# Print cost breakdown
print("\n💰 Cost Breakdown by Model:\n")
stats = guard.cost_tracker.get_stats()
for model_name, model_stats in stats["models"].items():
    print(
        f"  {model_name}:\n"
        f"    Calls: {model_stats['calls']}\n"
        f"    Input tokens: {model_stats['input_tokens']:,}\n"
        f"    Output tokens: {model_stats['output_tokens']:,}\n"
        f"    Cost: ${model_stats['cost']:.6f}\n"
    )

print(f"  Total cost: ${stats['total_cost']:.6f}")
print(f"  Today's cost: ${stats['today_cost']:.6f}")

print("\n🔧 Cost Breakdown by Tool:\n")
for tool_name, cost in stats["tools"].items():
    print(f"  {tool_name}: ${cost:.6f}")

print("\n✅ Demo complete!")
