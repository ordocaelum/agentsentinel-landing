# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Model pricing database for AgentSentinel cost tracking."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class ModelProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    MISTRAL = "mistral"
    COHERE = "cohere"
    META = "meta"
    AWS_BEDROCK = "aws_bedrock"
    AZURE_OPENAI = "azure_openai"
    GROQ = "groq"
    TOGETHER = "together"
    PERPLEXITY = "perplexity"
    DEEPSEEK = "deepseek"
    XAI = "xai"
    LOCAL = "local"


@dataclass
class ModelPricing:
    """Pricing per 1M tokens."""

    input_per_1m: float   # Cost per 1M input tokens in USD
    output_per_1m: float  # Cost per 1M output tokens in USD
    provider: ModelProvider
    context_window: int = 128000
    supports_vision: bool = False
    supports_tools: bool = True


# Pricing as of April 2026 - UPDATE REGULARLY
MODEL_PRICING: Dict[str, ModelPricing] = {
    # ═══════════════════════════════════════════════════════════════════════
    # OPENAI
    # ═══════════════════════════════════════════════════════════════════════
    "gpt-4o": ModelPricing(2.50, 10.00, ModelProvider.OPENAI, 128000, True),
    "gpt-4o-mini": ModelPricing(0.15, 0.60, ModelProvider.OPENAI, 128000, True),
    "gpt-4o-2024-11-20": ModelPricing(2.50, 10.00, ModelProvider.OPENAI, 128000, True),
    "gpt-4-turbo": ModelPricing(10.00, 30.00, ModelProvider.OPENAI, 128000, True),
    "gpt-4-turbo-preview": ModelPricing(10.00, 30.00, ModelProvider.OPENAI, 128000),
    "gpt-4": ModelPricing(30.00, 60.00, ModelProvider.OPENAI, 8192),
    "gpt-4-32k": ModelPricing(60.00, 120.00, ModelProvider.OPENAI, 32768),
    "gpt-3.5-turbo": ModelPricing(0.50, 1.50, ModelProvider.OPENAI, 16385),
    "gpt-3.5-turbo-16k": ModelPricing(0.50, 1.50, ModelProvider.OPENAI, 16385),
    # OpenAI o1 reasoning models
    "o1": ModelPricing(15.00, 60.00, ModelProvider.OPENAI, 200000),
    "o1-mini": ModelPricing(3.00, 12.00, ModelProvider.OPENAI, 128000),
    "o1-pro": ModelPricing(150.00, 600.00, ModelProvider.OPENAI, 200000),
    "o1-preview": ModelPricing(15.00, 60.00, ModelProvider.OPENAI, 128000),
    "o3-mini": ModelPricing(1.10, 4.40, ModelProvider.OPENAI, 200000),
    # OpenAI Embeddings
    "text-embedding-3-large": ModelPricing(0.13, 0.0, ModelProvider.OPENAI),
    "text-embedding-3-small": ModelPricing(0.02, 0.0, ModelProvider.OPENAI),
    "text-embedding-ada-002": ModelPricing(0.10, 0.0, ModelProvider.OPENAI),

    # ═══════════════════════════════════════════════════════════════════════
    # ANTHROPIC
    # ═══════════════════════════════════════════════════════════════════════
    "claude-4-opus": ModelPricing(15.00, 75.00, ModelProvider.ANTHROPIC, 200000, True),
    "claude-4-sonnet": ModelPricing(3.00, 15.00, ModelProvider.ANTHROPIC, 200000, True),
    "claude-3-7-sonnet": ModelPricing(3.00, 15.00, ModelProvider.ANTHROPIC, 200000, True),
    "claude-3-5-sonnet": ModelPricing(3.00, 15.00, ModelProvider.ANTHROPIC, 200000, True),
    "claude-3-5-sonnet-20241022": ModelPricing(3.00, 15.00, ModelProvider.ANTHROPIC, 200000, True),
    "claude-3-5-haiku": ModelPricing(0.80, 4.00, ModelProvider.ANTHROPIC, 200000, True),
    "claude-3-opus": ModelPricing(15.00, 75.00, ModelProvider.ANTHROPIC, 200000, True),
    "claude-3-sonnet": ModelPricing(3.00, 15.00, ModelProvider.ANTHROPIC, 200000, True),
    "claude-3-haiku": ModelPricing(0.25, 1.25, ModelProvider.ANTHROPIC, 200000, True),

    # ═══════════════════════════════════════════════════════════════════════
    # GOOGLE
    # ═══════════════════════════════════════════════════════════════════════
    "gemini-2.5-pro": ModelPricing(1.25, 10.00, ModelProvider.GOOGLE, 1000000, True),
    "gemini-2.5-flash": ModelPricing(0.15, 0.60, ModelProvider.GOOGLE, 1000000, True),
    "gemini-2.0-flash": ModelPricing(0.10, 0.40, ModelProvider.GOOGLE, 1000000, True),
    "gemini-2.0-flash-lite": ModelPricing(0.075, 0.30, ModelProvider.GOOGLE, 1000000, True),
    "gemini-1.5-pro": ModelPricing(1.25, 5.00, ModelProvider.GOOGLE, 2000000, True),
    "gemini-1.5-flash": ModelPricing(0.075, 0.30, ModelProvider.GOOGLE, 1000000, True),
    "gemini-1.0-pro": ModelPricing(0.50, 1.50, ModelProvider.GOOGLE, 32760),

    # ═══════════════════════════════════════════════════════════════════════
    # MISTRAL
    # ═══════════════════════════════════════════════════════════════════════
    "mistral-large": ModelPricing(2.00, 6.00, ModelProvider.MISTRAL, 128000),
    "mistral-large-2": ModelPricing(2.00, 6.00, ModelProvider.MISTRAL, 128000),
    "mistral-medium": ModelPricing(2.70, 8.10, ModelProvider.MISTRAL, 32000),
    "mistral-small": ModelPricing(0.20, 0.60, ModelProvider.MISTRAL, 32000),
    "mistral-small-latest": ModelPricing(0.20, 0.60, ModelProvider.MISTRAL, 32000),
    "codestral": ModelPricing(0.20, 0.60, ModelProvider.MISTRAL, 32000),
    "codestral-latest": ModelPricing(0.20, 0.60, ModelProvider.MISTRAL, 32000),
    "mixtral-8x7b": ModelPricing(0.45, 0.70, ModelProvider.MISTRAL, 32000),
    "mixtral-8x22b": ModelPricing(1.20, 1.20, ModelProvider.MISTRAL, 65000),
    "open-mistral-7b": ModelPricing(0.25, 0.25, ModelProvider.MISTRAL, 32000),
    "open-mixtral-8x7b": ModelPricing(0.70, 0.70, ModelProvider.MISTRAL, 32000),
    "ministral-8b": ModelPricing(0.10, 0.10, ModelProvider.MISTRAL, 128000),
    "ministral-3b": ModelPricing(0.04, 0.04, ModelProvider.MISTRAL, 128000),
    "pixtral-large": ModelPricing(2.00, 6.00, ModelProvider.MISTRAL, 128000, True),

    # ═══════════════════════════════════════════════════════════════════════
    # COHERE
    # ═══════════════════════════════════════════════════════════════════════
    "command-r-plus": ModelPricing(2.50, 10.00, ModelProvider.COHERE, 128000),
    "command-r": ModelPricing(0.15, 0.60, ModelProvider.COHERE, 128000),
    "command": ModelPricing(1.00, 2.00, ModelProvider.COHERE, 4096),
    "command-light": ModelPricing(0.30, 0.60, ModelProvider.COHERE, 4096),
    "embed-english-v3.0": ModelPricing(0.10, 0.0, ModelProvider.COHERE),
    "embed-multilingual-v3.0": ModelPricing(0.10, 0.0, ModelProvider.COHERE),

    # ═══════════════════════════════════════════════════════════════════════
    # META / LLAMA (via various providers — using Together AI pricing)
    # ═══════════════════════════════════════════════════════════════════════
    "llama-3.3-70b": ModelPricing(0.88, 0.88, ModelProvider.META, 128000),
    "llama-3.2-90b-vision": ModelPricing(1.20, 1.20, ModelProvider.META, 128000, True),
    "llama-3.2-11b-vision": ModelPricing(0.18, 0.18, ModelProvider.META, 128000, True),
    "llama-3.2-3b": ModelPricing(0.06, 0.06, ModelProvider.META, 128000),
    "llama-3.2-1b": ModelPricing(0.04, 0.04, ModelProvider.META, 128000),
    "llama-3.1-405b": ModelPricing(3.50, 3.50, ModelProvider.META, 128000),
    "llama-3.1-70b": ModelPricing(0.88, 0.88, ModelProvider.META, 128000),
    "llama-3.1-8b": ModelPricing(0.18, 0.18, ModelProvider.META, 128000),
    "llama-3-70b": ModelPricing(0.90, 0.90, ModelProvider.META, 8192),
    "llama-3-8b": ModelPricing(0.20, 0.20, ModelProvider.META, 8192),

    # ═══════════════════════════════════════════════════════════════════════
    # DEEPSEEK
    # ═══════════════════════════════════════════════════════════════════════
    "deepseek-chat": ModelPricing(0.14, 0.28, ModelProvider.DEEPSEEK, 64000),
    "deepseek-coder": ModelPricing(0.14, 0.28, ModelProvider.DEEPSEEK, 64000),
    "deepseek-v3": ModelPricing(0.27, 1.10, ModelProvider.DEEPSEEK, 64000),
    "deepseek-r1": ModelPricing(0.55, 2.19, ModelProvider.DEEPSEEK, 64000),

    # ═══════════════════════════════════════════════════════════════════════
    # XAI (GROK)
    # ═══════════════════════════════════════════════════════════════════════
    "grok-2": ModelPricing(2.00, 10.00, ModelProvider.XAI, 131072),
    "grok-2-mini": ModelPricing(0.20, 1.00, ModelProvider.XAI, 131072),
    "grok-beta": ModelPricing(5.00, 15.00, ModelProvider.XAI, 131072),
    "grok-2-vision": ModelPricing(2.00, 10.00, ModelProvider.XAI, 32768, True),

    # ═══════════════════════════════════════════════════════════════════════
    # GROQ (Fast inference — their own pricing)
    # ═══════════════════════════════════════════════════════════════════════
    "groq-llama-3.3-70b": ModelPricing(0.59, 0.79, ModelProvider.GROQ, 128000),
    "groq-llama-3.1-70b": ModelPricing(0.59, 0.79, ModelProvider.GROQ, 128000),
    "groq-llama-3.1-8b": ModelPricing(0.05, 0.08, ModelProvider.GROQ, 128000),
    "groq-mixtral-8x7b": ModelPricing(0.24, 0.24, ModelProvider.GROQ, 32000),
    "groq-gemma-2-9b": ModelPricing(0.20, 0.20, ModelProvider.GROQ, 8192),

    # ═══════════════════════════════════════════════════════════════════════
    # TOGETHER AI
    # ═══════════════════════════════════════════════════════════════════════
    "together-llama-3.1-405b": ModelPricing(3.50, 3.50, ModelProvider.TOGETHER, 128000),
    "together-llama-3.1-70b": ModelPricing(0.88, 0.88, ModelProvider.TOGETHER, 128000),
    "together-mixtral-8x22b": ModelPricing(1.20, 1.20, ModelProvider.TOGETHER, 65000),
    "together-qwen-2.5-72b": ModelPricing(1.20, 1.20, ModelProvider.TOGETHER, 128000),

    # ═══════════════════════════════════════════════════════════════════════
    # PERPLEXITY
    # ═══════════════════════════════════════════════════════════════════════
    "sonar-pro": ModelPricing(3.00, 15.00, ModelProvider.PERPLEXITY, 200000),
    "sonar": ModelPricing(1.00, 1.00, ModelProvider.PERPLEXITY, 128000),
    "sonar-reasoning-pro": ModelPricing(2.00, 8.00, ModelProvider.PERPLEXITY, 128000),
    "sonar-reasoning": ModelPricing(1.00, 5.00, ModelProvider.PERPLEXITY, 128000),
    "sonar-deep-research": ModelPricing(2.00, 8.00, ModelProvider.PERPLEXITY, 128000),

    # ═══════════════════════════════════════════════════════════════════════
    # AWS BEDROCK (on-demand pricing)
    # ═══════════════════════════════════════════════════════════════════════
    "bedrock-claude-3-5-sonnet": ModelPricing(3.00, 15.00, ModelProvider.AWS_BEDROCK, 200000),
    "bedrock-claude-3-haiku": ModelPricing(0.25, 1.25, ModelProvider.AWS_BEDROCK, 200000),
    "bedrock-llama-3.1-70b": ModelPricing(2.65, 3.50, ModelProvider.AWS_BEDROCK, 128000),
    "bedrock-llama-3.1-8b": ModelPricing(0.22, 0.22, ModelProvider.AWS_BEDROCK, 128000),
    "bedrock-titan-text-express": ModelPricing(0.20, 0.60, ModelProvider.AWS_BEDROCK, 8000),
    "bedrock-titan-text-lite": ModelPricing(0.15, 0.20, ModelProvider.AWS_BEDROCK, 4000),
    "amazon-nova-pro": ModelPricing(0.80, 3.20, ModelProvider.AWS_BEDROCK, 300000, True),
    "amazon-nova-lite": ModelPricing(0.06, 0.24, ModelProvider.AWS_BEDROCK, 300000, True),
    "amazon-nova-micro": ModelPricing(0.035, 0.14, ModelProvider.AWS_BEDROCK, 128000),

    # ═══════════════════════════════════════════════════════════════════════
    # AZURE OPENAI (same models, slightly different pricing)
    # ═══════════════════════════════════════════════════════════════════════
    "azure-gpt-4o": ModelPricing(2.50, 10.00, ModelProvider.AZURE_OPENAI, 128000, True),
    "azure-gpt-4o-mini": ModelPricing(0.15, 0.60, ModelProvider.AZURE_OPENAI, 128000, True),
    "azure-gpt-4-turbo": ModelPricing(10.00, 30.00, ModelProvider.AZURE_OPENAI, 128000),
    "azure-gpt-35-turbo": ModelPricing(0.50, 1.50, ModelProvider.AZURE_OPENAI, 16385),

    # ═══════════════════════════════════════════════════════════════════════
    # LOCAL / SELF-HOSTED (zero cost tracking, but track usage)
    # ═══════════════════════════════════════════════════════════════════════
    "ollama-*": ModelPricing(0.0, 0.0, ModelProvider.LOCAL, 128000),
    "local-*": ModelPricing(0.0, 0.0, ModelProvider.LOCAL, 128000),
    "lmstudio-*": ModelPricing(0.0, 0.0, ModelProvider.LOCAL, 128000),
}


def get_model_pricing(model_name: str) -> Optional[ModelPricing]:
    """Get pricing for a model, with fuzzy matching and wildcard support."""
    # Direct match
    if model_name in MODEL_PRICING:
        return MODEL_PRICING[model_name]

    # Lowercase match
    lower = model_name.lower()
    if lower in MODEL_PRICING:
        return MODEL_PRICING[lower]

    # Wildcard matching (e.g., "ollama-*" matches "ollama-llama3")
    for pattern, pricing in MODEL_PRICING.items():
        if fnmatch.fnmatch(lower, pattern):
            return pricing

    # Fuzzy partial match (e.g., "gpt-4o-2024-05-13" matches "gpt-4o")
    for known_model in MODEL_PRICING:
        if lower.startswith(known_model) or known_model.startswith(lower):
            return MODEL_PRICING[known_model]

    return None


def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for a model call."""
    pricing = get_model_pricing(model_name)
    if pricing is None:
        return 0.0

    input_cost = (input_tokens / 1_000_000) * pricing.input_per_1m
    output_cost = (output_tokens / 1_000_000) * pricing.output_per_1m
    return input_cost + output_cost


def list_models_by_provider(provider: ModelProvider) -> List[str]:
    """List all models for a given provider."""
    return [name for name, p in MODEL_PRICING.items() if p.provider == provider]


def list_all_providers() -> List[ModelProvider]:
    """List all supported providers."""
    return list(ModelProvider)
