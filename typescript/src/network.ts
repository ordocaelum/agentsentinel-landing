/**
 * AgentSentinel — Safety controls for AI agents
 * Copyright (c) 2026 Leland E. Doss. All rights reserved.
 * Licensed under the Business Source License 1.1
 * See LICENSE.md for details
 */
/**
 * Network security controls for AgentSentinel.
 */

/** Configuration options for NetworkPolicy. */
export interface NetworkPolicyOptions {
  /**
   * Enforcement mode:
   * - `"allowlist"` — only `allowedDomains` can be accessed (default).
   * - `"blocklist"` — all domains except `blockedDomains` can be accessed.
   * - `"monitor"`   — log all requests but never block.
   */
  mode?: "allowlist" | "blocklist" | "monitor";
  /** Domains permitted to receive outbound connections. Supports `*.example.com` wildcards. */
  allowedDomains?: string[];
  /** Domains that are never permitted, regardless of mode. Supports wildcards. */
  blockedDomains?: string[];
  /** IP addresses/prefixes that are explicitly permitted. */
  allowedIPs?: string[];
  /** IP addresses/prefixes that are never permitted. */
  blockedIPs?: string[];
  /** Block requests to RFC-1918 private IP ranges. Default: true. */
  blockPrivateIPs?: boolean;
  /** Block requests to localhost / 127.0.0.1. Default: true. */
  blockLocalhost?: boolean;
  /** Maximum outbound request body size in bytes. Default: 1 MB. */
  maxRequestSizeBytes?: number;
}

/** Immutable network policy value object. */
export class NetworkPolicy {
  readonly mode: "allowlist" | "blocklist" | "monitor";
  readonly allowedDomains: readonly string[];
  readonly blockedDomains: readonly string[];
  readonly allowedIPs: readonly string[];
  readonly blockedIPs: readonly string[];
  readonly blockPrivateIPs: boolean;
  readonly blockLocalhost: boolean;
  readonly maxRequestSizeBytes: number;

  constructor(options: NetworkPolicyOptions = {}) {
    this.mode = options.mode ?? "allowlist";
    this.allowedDomains = Object.freeze(options.allowedDomains ?? [
      "api.openai.com",
      "api.anthropic.com",
      "api.github.com",
      "*.githubusercontent.com",
    ]);
    this.blockedDomains = Object.freeze(options.blockedDomains ?? [
      "*.pastebin.com",
      "*.requestbin.com",
      "*.webhook.site",
      "*.ngrok.io",
      "*.localtunnel.me",
    ]);
    this.allowedIPs = Object.freeze(options.allowedIPs ?? []);
    this.blockedIPs = Object.freeze(options.blockedIPs ?? []);
    this.blockPrivateIPs = options.blockPrivateIPs ?? true;
    this.blockLocalhost = options.blockLocalhost ?? true;
    this.maxRequestSizeBytes = options.maxRequestSizeBytes ?? 1_000_000;
  }
}

/** Private IP range patterns (RFC 1918 + loopback + link-local). */
const PRIVATE_IP_PATTERNS = [
  /^10\./,
  /^172\.(1[6-9]|2[0-9]|3[01])\./,
  /^192\.168\./,
  /^127\./,
  /^169\.254\./,
  /^0\./,
];

/** Enforces network security policy on outbound requests. */
export class NetworkGuard {
  private readonly policy: NetworkPolicy;

  constructor(policy: NetworkPolicy) {
    this.policy = policy;
  }

  /**
   * Check whether a URL is allowed by the network policy.
   *
   * @returns `[allowed, reason]` — `allowed` is `true` if the request may proceed.
   */
  checkURL(url: string): [boolean, string] {
    // Extract hostname using a simple regex to avoid needing DOM lib
    const match = /^(?:[a-z][a-z0-9+\-.]*:\/\/)?([^/:?#]+)/i.exec(url);
    const hostname = match ? match[1].toLowerCase() : "";

    // Localhost check
    if (this.policy.blockLocalhost) {
      if (["localhost", "127.0.0.1", "::1", "0.0.0.0"].includes(hostname)) {
        return [false, `Localhost access blocked: ${hostname}`];
      }
    }

    // Private IP check
    if (this.policy.blockPrivateIPs && this._isPrivateIP(hostname)) {
      return [false, `Private IP access blocked: ${hostname}`];
    }

    // Blocked domains (always enforced)
    for (const pattern of this.policy.blockedDomains) {
      if (this._matchDomain(hostname, pattern)) {
        return [false, `Domain blocked by policy: ${hostname} matches ${pattern}`];
      }
    }

    // Blocked IPs
    for (const pattern of this.policy.blockedIPs) {
      if (this._matchIP(hostname, pattern)) {
        return [false, `IP blocked by policy: ${hostname}`];
      }
    }

    if (this.policy.mode === "allowlist") {
      for (const pattern of this.policy.allowedDomains) {
        if (this._matchDomain(hostname, pattern)) return [true, "Domain in allowlist"];
      }
      for (const pattern of this.policy.allowedIPs) {
        if (this._matchIP(hostname, pattern)) return [true, "IP in allowlist"];
      }
      return [false, `Domain not in allowlist: ${hostname}`];
    }

    if (this.policy.mode === "blocklist") {
      return [true, "Domain not in blocklist"];
    }

    // monitor mode
    return [true, "Monitor mode - logging only"];
  }

  /**
   * Check whether an outbound request size is within the configured limit.
   *
   * @returns `[allowed, reason]`
   */
  checkRequestSize(sizeBytes: number): [boolean, string] {
    if (sizeBytes > this.policy.maxRequestSizeBytes) {
      return [false, `Request size ${sizeBytes} exceeds limit ${this.policy.maxRequestSizeBytes}`];
    }
    return [true, "Size OK"];
  }

  /** Match a hostname against a domain pattern (supports `*.example.com` wildcards). */
  private _matchDomain(hostname: string, pattern: string): boolean {
    if (pattern.startsWith("*.")) {
      const suffix = pattern.slice(1); // ".example.com"
      return hostname.endsWith(suffix) || hostname === pattern.slice(2);
    }
    // Exact match or simple glob via fnmatch-style conversion
    const re = new RegExp(
      "^" +
      pattern
        .replace(/[.+^${}()|[\]\\]/g, "\\$&")
        .replace(/\*/g, ".*")
        .replace(/\?/g, ".") +
      "$"
    );
    return re.test(hostname);
  }

  /** Match a hostname against an IP pattern (simple prefix match). */
  private _matchIP(hostname: string, pattern: string): boolean {
    return hostname.startsWith(pattern.replace(/\*$/, ""));
  }

  /** Check if a hostname looks like a private IP address. */
  private _isPrivateIP(hostname: string): boolean {
    return PRIVATE_IP_PATTERNS.some(re => re.test(hostname));
  }
}
