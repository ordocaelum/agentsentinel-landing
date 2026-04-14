"""Tests for the model pricing database."""

import pytest

from agentsentinel.pricing import (
    MODEL_PRICING,
    ModelPricing,
    ModelProvider,
    calculate_cost,
    get_model_pricing,
    list_all_providers,
    list_models_by_provider,
)


class TestModelPricingDatabase:
    def test_model_pricing_dict_is_not_empty(self):
        assert len(MODEL_PRICING) > 0

    def test_all_entries_are_model_pricing_instances(self):
        for name, pricing in MODEL_PRICING.items():
            assert isinstance(pricing, ModelPricing), f"{name} has unexpected type"

    def test_all_entries_have_valid_provider(self):
        for name, pricing in MODEL_PRICING.items():
            assert isinstance(pricing.provider, ModelProvider), f"{name} has invalid provider"

    def test_pricing_has_non_negative_costs(self):
        for name, pricing in MODEL_PRICING.items():
            assert pricing.input_per_1m >= 0, f"{name} input cost is negative"
            assert pricing.output_per_1m >= 0, f"{name} output cost is negative"

    def test_at_least_80_models(self):
        assert len(MODEL_PRICING) >= 80

    def test_openai_models_present(self):
        assert "gpt-4o" in MODEL_PRICING
        assert "gpt-4o-mini" in MODEL_PRICING
        assert "o1" in MODEL_PRICING

    def test_anthropic_models_present(self):
        assert "claude-3-5-sonnet" in MODEL_PRICING
        assert "claude-3-haiku" in MODEL_PRICING
        assert "claude-3-opus" in MODEL_PRICING

    def test_google_models_present(self):
        assert "gemini-2.5-pro" in MODEL_PRICING
        assert "gemini-1.5-flash" in MODEL_PRICING

    def test_local_wildcard_patterns_present(self):
        assert "ollama-*" in MODEL_PRICING
        assert "local-*" in MODEL_PRICING


class TestGetModelPricing:
    def test_direct_match(self):
        pricing = get_model_pricing("gpt-4o")
        assert pricing is not None
        assert pricing.provider == ModelProvider.OPENAI

    def test_case_insensitive_match(self):
        pricing = get_model_pricing("GPT-4O")
        assert pricing is not None
        assert pricing.provider == ModelProvider.OPENAI

    def test_wildcard_match_ollama(self):
        pricing = get_model_pricing("ollama-llama3")
        assert pricing is not None
        assert pricing.provider == ModelProvider.LOCAL
        assert pricing.input_per_1m == 0.0

    def test_wildcard_match_local(self):
        pricing = get_model_pricing("local-my-custom-model")
        assert pricing is not None
        assert pricing.provider == ModelProvider.LOCAL

    def test_fuzzy_match_with_date_suffix(self):
        # "gpt-4o-2024-05-13" should match "gpt-4o" via prefix matching
        pricing = get_model_pricing("gpt-4o-2024-05-13")
        assert pricing is not None
        assert pricing.provider == ModelProvider.OPENAI

    def test_unknown_model_returns_none(self):
        pricing = get_model_pricing("completely-unknown-model-xyz")
        assert pricing is None

    def test_anthropic_model_has_vision(self):
        pricing = get_model_pricing("claude-3-5-sonnet")
        assert pricing is not None
        assert pricing.supports_vision is True

    def test_context_window_is_positive(self):
        pricing = get_model_pricing("gpt-4o")
        assert pricing is not None
        assert pricing.context_window > 0


class TestCalculateCost:
    def test_zero_tokens_yields_zero_cost(self):
        cost = calculate_cost("gpt-4o", 0, 0)
        assert cost == 0.0

    def test_known_model_cost_calculation(self):
        # gpt-4o: $2.50/1M input, $10.00/1M output
        cost = calculate_cost("gpt-4o", 1_000_000, 1_000_000)
        assert cost == pytest.approx(12.50)

    def test_partial_tokens(self):
        # 500K input tokens at $2.50/1M = $1.25
        # 0 output tokens
        cost = calculate_cost("gpt-4o", 500_000, 0)
        assert cost == pytest.approx(1.25)

    def test_output_only_tokens(self):
        # gpt-4o: $10.00/1M output
        cost = calculate_cost("gpt-4o", 0, 100_000)
        assert cost == pytest.approx(1.00)

    def test_unknown_model_returns_zero(self):
        cost = calculate_cost("unknown-model-xyz", 1_000_000, 1_000_000)
        assert cost == 0.0

    def test_local_model_zero_cost(self):
        cost = calculate_cost("ollama-llama3", 1_000_000, 1_000_000)
        assert cost == 0.0

    def test_cheap_model_small_cost(self):
        # gpt-4o-mini: $0.15/1M input, $0.60/1M output
        cost = calculate_cost("gpt-4o-mini", 1_000, 1_000)
        assert cost == pytest.approx((0.15 + 0.60) / 1000)

    def test_embedding_model_has_no_output_cost(self):
        # text-embedding-3-large: $0.13/1M input, $0.0 output
        cost = calculate_cost("text-embedding-3-large", 1_000_000, 0)
        assert cost == pytest.approx(0.13)


class TestListModelsByProvider:
    def test_openai_provider_has_models(self):
        models = list_models_by_provider(ModelProvider.OPENAI)
        assert len(models) > 0
        assert "gpt-4o" in models

    def test_anthropic_provider_has_models(self):
        models = list_models_by_provider(ModelProvider.ANTHROPIC)
        assert len(models) > 0
        assert "claude-3-opus" in models

    def test_local_provider_has_wildcard_entries(self):
        models = list_models_by_provider(ModelProvider.LOCAL)
        assert len(models) > 0

    def test_all_listed_models_are_in_pricing_dict(self):
        for provider in ModelProvider:
            for model in list_models_by_provider(provider):
                assert model in MODEL_PRICING


class TestListAllProviders:
    def test_returns_all_enum_values(self):
        providers = list_all_providers()
        assert set(providers) == set(ModelProvider)

    def test_includes_major_providers(self):
        providers = list_all_providers()
        assert ModelProvider.OPENAI in providers
        assert ModelProvider.ANTHROPIC in providers
        assert ModelProvider.GOOGLE in providers
        assert ModelProvider.LOCAL in providers
