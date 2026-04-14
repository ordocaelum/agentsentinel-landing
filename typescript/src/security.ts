/**
 * Security utilities for AgentSentinel.
 *
 * @module security
 */

/** Fine-grained security configuration used by {@link AgentPolicy}. */
export interface SecurityConfigOptions {
  /**
   * Regular-expression patterns whose matches are replaced with `[REDACTED]`
   * before writing to audit logs.  Defaults to common credential patterns
   * (API keys, passwords, bearer tokens, secrets).
   */
  redactPatterns?: string[];

  /**
   * Tools that are **always** blocked — they will never execute regardless of
   * approval decisions.  Supports {@link https://www.npmjs.com/package/micromatch micromatch}-style
   * glob wildcards (e.g. `"delete_*"`).
   */
  blockedTools?: string[];

  /**
   * Tools that always require explicit human approval even when not listed in
   * {@link AgentPolicyOptions.requireApproval}.  Defaults to a curated list
   * of high-risk operations (shell execution, file deletion, payments, etc.).
   */
  sensitiveTools?: string[];

  /**
   * Maximum number of characters captured per parameter in audit logs.
   * Prevents large payloads (file contents, model outputs) from bloating the
   * audit trail.  Default: `1000`.
   */
  maxParamLogSize?: number;

  /**
   * When `false` (the default) parameter values are truncated to
   * {@link maxParamLogSize} characters and sensitive patterns are redacted
   * before logging.  Set to `true` only in secure, controlled environments.
   */
  logFullParams?: boolean;
}

/** Immutable security configuration value object. */
export class SecurityConfig {
  readonly redactPatterns: readonly string[];
  readonly blockedTools: readonly string[];
  readonly sensitiveTools: readonly string[];
  readonly maxParamLogSize: number;
  readonly logFullParams: boolean;

  constructor(options: SecurityConfigOptions = {}) {
    this.redactPatterns = Object.freeze(
      options.redactPatterns ?? [
        'api[_-]?key["\']?\\s*[:=]\\s*["\']?[\\w-]+',
        'password["\']?\\s*[:=]\\s*["\']?[^\\s"\']+',
        'secret["\']?\\s*[:=]\\s*["\']?[\\w-]+',
        'token["\']?\\s*[:=]\\s*["\']?[\\w-]+',
        'bearer\\s+[\\w-]+',
      ]
    );
    this.blockedTools = Object.freeze(options.blockedTools ?? []);
    this.sensitiveTools = Object.freeze(
      options.sensitiveTools ?? [
        "execute_shell",
        "run_command",
        "delete_file",
        "rm_rf",
        "drop_table",
        "send_email",
        "post_tweet",
        "make_payment",
      ]
    );
    this.maxParamLogSize = options.maxParamLogSize ?? 1000;
    this.logFullParams = options.logFullParams ?? false;
  }
}

/**
 * Redact sensitive information from *text* using *patterns*.
 *
 * Each pattern is matched case-insensitively; matches are replaced with the
 * literal string `[REDACTED]`.
 */
export function redactSensitive(text: string, patterns: readonly string[]): string {
  let result = text;
  for (const pattern of patterns) {
    result = result.replace(new RegExp(pattern, "gi"), "[REDACTED]");
  }
  return result;
}

/**
 * Return `true` if *toolName* matches any glob pattern in *blockedList*.
 *
 * Uses a simple `*` wildcard check compatible with fnmatch semantics.
 */
export function isToolBlocked(toolName: string, blockedList: readonly string[]): boolean {
  return blockedList.some((pattern) => matchesGlob(toolName, pattern));
}

/**
 * Minimal glob matching supporting `*` (any characters) and `?` (one character).
 * Converts the pattern to a RegExp for matching.
 */
function matchesGlob(name: string, pattern: string): boolean {
  if (pattern === name) return true;
  // Escape regex special chars except * and ?
  const regexStr = pattern
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*/g, ".*")
    .replace(/\?/g, ".");
  return new RegExp(`^${regexStr}$`).test(name);
}
