/**
 * Model pricing database for AgentSentinel cost tracking.
 * Pricing as of April 2026 — update regularly.
 */

export enum ModelProvider {
  OPENAI = "openai",
  ANTHROPIC = "anthropic",
  GOOGLE = "google",
  MISTRAL = "mistral",
  COHERE = "cohere",
  META = "meta",
  AWS_BEDROCK = "aws_bedrock",
  AZURE_OPENAI = "azure_openai",
  GROQ = "groq",
  TOGETHER = "together",
  PERPLEXITY = "perplexity",
  DEEPSEEK = "deepseek",
  XAI = "xai",
  LOCAL = "local",
}

/** Pricing per 1M tokens. */
export interface ModelPricing {
  /** Cost per 1M input tokens in USD. */
  readonly inputPer1m: number;
  /** Cost per 1M output tokens in USD. */
  readonly outputPer1m: number;
  readonly provider: ModelProvider;
  readonly contextWindow: number;
  readonly supportsVision: boolean;
  readonly supportsTools: boolean;
}

function mp(
  inputPer1m: number,
  outputPer1m: number,
  provider: ModelProvider,
  contextWindow = 128000,
  supportsVision = false,
  supportsTools = true
): ModelPricing {
  return { inputPer1m, outputPer1m, provider, contextWindow, supportsVision, supportsTools };
}

/** Comprehensive model pricing database. */
export const MODEL_PRICING: Readonly<Record<string, ModelPricing>> = Object.freeze({
  // ── OPENAI ────────────────────────────────────────────────────────────────
  "gpt-4o":                    mp(2.50, 10.00,  ModelProvider.OPENAI, 128000, true),
  "gpt-4o-mini":               mp(0.15,  0.60,  ModelProvider.OPENAI, 128000, true),
  "gpt-4o-2024-11-20":         mp(2.50, 10.00,  ModelProvider.OPENAI, 128000, true),
  "gpt-4-turbo":               mp(10.00, 30.00, ModelProvider.OPENAI, 128000, true),
  "gpt-4-turbo-preview":       mp(10.00, 30.00, ModelProvider.OPENAI, 128000),
  "gpt-4":                     mp(30.00, 60.00, ModelProvider.OPENAI,   8192),
  "gpt-4-32k":                 mp(60.00, 120.00, ModelProvider.OPENAI, 32768),
  "gpt-3.5-turbo":             mp(0.50,   1.50, ModelProvider.OPENAI, 16385),
  "gpt-3.5-turbo-16k":         mp(0.50,   1.50, ModelProvider.OPENAI, 16385),
  // o1 reasoning
  "o1":                        mp(15.00, 60.00,  ModelProvider.OPENAI, 200000),
  "o1-mini":                   mp(3.00,  12.00,  ModelProvider.OPENAI, 128000),
  "o1-pro":                    mp(150.00, 600.00, ModelProvider.OPENAI, 200000),
  "o1-preview":                mp(15.00, 60.00,  ModelProvider.OPENAI, 128000),
  "o3-mini":                   mp(1.10,   4.40,  ModelProvider.OPENAI, 200000),
  // Embeddings
  "text-embedding-3-large":    mp(0.13,   0.0,   ModelProvider.OPENAI),
  "text-embedding-3-small":    mp(0.02,   0.0,   ModelProvider.OPENAI),
  "text-embedding-ada-002":    mp(0.10,   0.0,   ModelProvider.OPENAI),

  // ── ANTHROPIC ─────────────────────────────────────────────────────────────
  "claude-4-opus":             mp(15.00,  75.00, ModelProvider.ANTHROPIC, 200000, true),
  "claude-4-sonnet":           mp(3.00,   15.00, ModelProvider.ANTHROPIC, 200000, true),
  "claude-3-7-sonnet":         mp(3.00,   15.00, ModelProvider.ANTHROPIC, 200000, true),
  "claude-3-5-sonnet":         mp(3.00,   15.00, ModelProvider.ANTHROPIC, 200000, true),
  "claude-3-5-sonnet-20241022":mp(3.00,   15.00, ModelProvider.ANTHROPIC, 200000, true),
  "claude-3-5-haiku":          mp(0.80,    4.00, ModelProvider.ANTHROPIC, 200000, true),
  "claude-3-opus":             mp(15.00,  75.00, ModelProvider.ANTHROPIC, 200000, true),
  "claude-3-sonnet":           mp(3.00,   15.00, ModelProvider.ANTHROPIC, 200000, true),
  "claude-3-haiku":            mp(0.25,    1.25, ModelProvider.ANTHROPIC, 200000, true),

  // ── GOOGLE ────────────────────────────────────────────────────────────────
  "gemini-2.5-pro":            mp(1.25,  10.00,  ModelProvider.GOOGLE, 1000000, true),
  "gemini-2.5-flash":          mp(0.15,   0.60,  ModelProvider.GOOGLE, 1000000, true),
  "gemini-2.0-flash":          mp(0.10,   0.40,  ModelProvider.GOOGLE, 1000000, true),
  "gemini-2.0-flash-lite":     mp(0.075,  0.30,  ModelProvider.GOOGLE, 1000000, true),
  "gemini-1.5-pro":            mp(1.25,   5.00,  ModelProvider.GOOGLE, 2000000, true),
  "gemini-1.5-flash":          mp(0.075,  0.30,  ModelProvider.GOOGLE, 1000000, true),
  "gemini-1.0-pro":            mp(0.50,   1.50,  ModelProvider.GOOGLE,   32760),

  // ── MISTRAL ───────────────────────────────────────────────────────────────
  "mistral-large":             mp(2.00,  6.00, ModelProvider.MISTRAL, 128000),
  "mistral-large-2":           mp(2.00,  6.00, ModelProvider.MISTRAL, 128000),
  "mistral-medium":            mp(2.70,  8.10, ModelProvider.MISTRAL,  32000),
  "mistral-small":             mp(0.20,  0.60, ModelProvider.MISTRAL,  32000),
  "mistral-small-latest":      mp(0.20,  0.60, ModelProvider.MISTRAL,  32000),
  "codestral":                 mp(0.20,  0.60, ModelProvider.MISTRAL,  32000),
  "codestral-latest":          mp(0.20,  0.60, ModelProvider.MISTRAL,  32000),
  "mixtral-8x7b":              mp(0.45,  0.70, ModelProvider.MISTRAL,  32000),
  "mixtral-8x22b":             mp(1.20,  1.20, ModelProvider.MISTRAL,  65000),
  "open-mistral-7b":           mp(0.25,  0.25, ModelProvider.MISTRAL,  32000),
  "open-mixtral-8x7b":         mp(0.70,  0.70, ModelProvider.MISTRAL,  32000),
  "ministral-8b":              mp(0.10,  0.10, ModelProvider.MISTRAL, 128000),
  "ministral-3b":              mp(0.04,  0.04, ModelProvider.MISTRAL, 128000),
  "pixtral-large":             mp(2.00,  6.00, ModelProvider.MISTRAL, 128000, true),

  // ── COHERE ────────────────────────────────────────────────────────────────
  "command-r-plus":            mp(2.50, 10.00, ModelProvider.COHERE, 128000),
  "command-r":                 mp(0.15,  0.60, ModelProvider.COHERE, 128000),
  "command":                   mp(1.00,  2.00, ModelProvider.COHERE,   4096),
  "command-light":             mp(0.30,  0.60, ModelProvider.COHERE,   4096),
  "embed-english-v3.0":        mp(0.10,  0.0,  ModelProvider.COHERE),
  "embed-multilingual-v3.0":   mp(0.10,  0.0,  ModelProvider.COHERE),

  // ── META / LLAMA ──────────────────────────────────────────────────────────
  "llama-3.3-70b":             mp(0.88, 0.88, ModelProvider.META, 128000),
  "llama-3.2-90b-vision":      mp(1.20, 1.20, ModelProvider.META, 128000, true),
  "llama-3.2-11b-vision":      mp(0.18, 0.18, ModelProvider.META, 128000, true),
  "llama-3.2-3b":              mp(0.06, 0.06, ModelProvider.META, 128000),
  "llama-3.2-1b":              mp(0.04, 0.04, ModelProvider.META, 128000),
  "llama-3.1-405b":            mp(3.50, 3.50, ModelProvider.META, 128000),
  "llama-3.1-70b":             mp(0.88, 0.88, ModelProvider.META, 128000),
  "llama-3.1-8b":              mp(0.18, 0.18, ModelProvider.META, 128000),
  "llama-3-70b":               mp(0.90, 0.90, ModelProvider.META,   8192),
  "llama-3-8b":                mp(0.20, 0.20, ModelProvider.META,   8192),

  // ── DEEPSEEK ──────────────────────────────────────────────────────────────
  "deepseek-chat":             mp(0.14, 0.28, ModelProvider.DEEPSEEK, 64000),
  "deepseek-coder":            mp(0.14, 0.28, ModelProvider.DEEPSEEK, 64000),
  "deepseek-v3":               mp(0.27, 1.10, ModelProvider.DEEPSEEK, 64000),
  "deepseek-r1":               mp(0.55, 2.19, ModelProvider.DEEPSEEK, 64000),

  // ── XAI (GROK) ────────────────────────────────────────────────────────────
  "grok-2":                    mp(2.00, 10.00, ModelProvider.XAI, 131072),
  "grok-2-mini":               mp(0.20,  1.00, ModelProvider.XAI, 131072),
  "grok-beta":                 mp(5.00, 15.00, ModelProvider.XAI, 131072),
  "grok-2-vision":             mp(2.00, 10.00, ModelProvider.XAI,  32768, true),

  // ── GROQ ──────────────────────────────────────────────────────────────────
  "groq-llama-3.3-70b":        mp(0.59, 0.79, ModelProvider.GROQ, 128000),
  "groq-llama-3.1-70b":        mp(0.59, 0.79, ModelProvider.GROQ, 128000),
  "groq-llama-3.1-8b":         mp(0.05, 0.08, ModelProvider.GROQ, 128000),
  "groq-mixtral-8x7b":         mp(0.24, 0.24, ModelProvider.GROQ,  32000),
  "groq-gemma-2-9b":           mp(0.20, 0.20, ModelProvider.GROQ,   8192),

  // ── TOGETHER AI ───────────────────────────────────────────────────────────
  "together-llama-3.1-405b":   mp(3.50, 3.50, ModelProvider.TOGETHER, 128000),
  "together-llama-3.1-70b":    mp(0.88, 0.88, ModelProvider.TOGETHER, 128000),
  "together-mixtral-8x22b":    mp(1.20, 1.20, ModelProvider.TOGETHER,  65000),
  "together-qwen-2.5-72b":     mp(1.20, 1.20, ModelProvider.TOGETHER, 128000),

  // ── PERPLEXITY ────────────────────────────────────────────────────────────
  "sonar-pro":                 mp(3.00, 15.00, ModelProvider.PERPLEXITY, 200000),
  "sonar":                     mp(1.00,  1.00, ModelProvider.PERPLEXITY, 128000),
  "sonar-reasoning-pro":       mp(2.00,  8.00, ModelProvider.PERPLEXITY, 128000),
  "sonar-reasoning":           mp(1.00,  5.00, ModelProvider.PERPLEXITY, 128000),
  "sonar-deep-research":       mp(2.00,  8.00, ModelProvider.PERPLEXITY, 128000),

  // ── AWS BEDROCK ───────────────────────────────────────────────────────────
  "bedrock-claude-3-5-sonnet": mp(3.00, 15.00, ModelProvider.AWS_BEDROCK, 200000),
  "bedrock-claude-3-haiku":    mp(0.25,  1.25, ModelProvider.AWS_BEDROCK, 200000),
  "bedrock-llama-3.1-70b":     mp(2.65,  3.50, ModelProvider.AWS_BEDROCK, 128000),
  "bedrock-llama-3.1-8b":      mp(0.22,  0.22, ModelProvider.AWS_BEDROCK, 128000),
  "bedrock-titan-text-express":mp(0.20,  0.60, ModelProvider.AWS_BEDROCK,   8000),
  "bedrock-titan-text-lite":   mp(0.15,  0.20, ModelProvider.AWS_BEDROCK,   4000),
  "amazon-nova-pro":           mp(0.80,  3.20, ModelProvider.AWS_BEDROCK, 300000, true),
  "amazon-nova-lite":          mp(0.06,  0.24, ModelProvider.AWS_BEDROCK, 300000, true),
  "amazon-nova-micro":         mp(0.035, 0.14, ModelProvider.AWS_BEDROCK, 128000),

  // ── AZURE OPENAI ──────────────────────────────────────────────────────────
  "azure-gpt-4o":              mp(2.50, 10.00, ModelProvider.AZURE_OPENAI, 128000, true),
  "azure-gpt-4o-mini":         mp(0.15,  0.60, ModelProvider.AZURE_OPENAI, 128000, true),
  "azure-gpt-4-turbo":         mp(10.00, 30.00, ModelProvider.AZURE_OPENAI, 128000),
  "azure-gpt-35-turbo":        mp(0.50,  1.50, ModelProvider.AZURE_OPENAI,  16385),

  // ── LOCAL / SELF-HOSTED ───────────────────────────────────────────────────
  "ollama-*":                  mp(0.0, 0.0, ModelProvider.LOCAL, 128000),
  "local-*":                   mp(0.0, 0.0, ModelProvider.LOCAL, 128000),
  "lmstudio-*":                mp(0.0, 0.0, ModelProvider.LOCAL, 128000),
});

/**
 * Get pricing for a model, with fuzzy matching and wildcard support.
 * Returns `undefined` if no pricing is found.
 */
export function getModelPricing(modelName: string): ModelPricing | undefined {
  // Direct match
  if (modelName in MODEL_PRICING) return MODEL_PRICING[modelName];

  // Lowercase match
  const lower = modelName.toLowerCase();
  if (lower in MODEL_PRICING) return MODEL_PRICING[lower];

  // Wildcard matching (e.g., "ollama-*" matches "ollama-llama3")
  for (const [pattern, pricing] of Object.entries(MODEL_PRICING)) {
    if (_matchesGlob(lower, pattern)) return pricing;
  }

  // Fuzzy partial match (e.g., "gpt-4o-2024-05-13" matches "gpt-4o")
  for (const known of Object.keys(MODEL_PRICING)) {
    if (lower.startsWith(known) || known.startsWith(lower)) return MODEL_PRICING[known];
  }

  return undefined;
}

/** Simple glob pattern matcher supporting `*` wildcards. */
function _matchesGlob(str: string, pattern: string): boolean {
  if (!pattern.includes("*")) return str === pattern;
  const re = new RegExp(
    "^" + pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*") + "$"
  );
  return re.test(str);
}

/** Calculate cost in USD for a model call. */
export function calculateCost(
  modelName: string,
  inputTokens: number,
  outputTokens: number
): number {
  const pricing = getModelPricing(modelName);
  if (!pricing) return 0;
  return (inputTokens / 1_000_000) * pricing.inputPer1m +
         (outputTokens / 1_000_000) * pricing.outputPer1m;
}

/** List all models for a given provider. */
export function listModelsByProvider(provider: ModelProvider): string[] {
  return Object.entries(MODEL_PRICING)
    .filter(([, p]) => p.provider === provider)
    .map(([name]) => name);
}

/** List all supported providers. */
export function listAllProviders(): ModelProvider[] {
  return Object.values(ModelProvider);
}
