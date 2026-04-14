/**
 * Content inspection for outbound data in AgentSentinel.
 */

import { PIIConfig, PIIMatch, PIIScanner } from "./pii";

/** Result of a content inspection. */
export enum InspectionResult {
  ALLOW = "allow",
  BLOCK = "block",
  REDACT = "redact",
  WARN = "warn",
}

/** Detailed report from a content inspection. */
export interface InspectionReport {
  result: InspectionResult;
  reason: string;
  piiMatches: PIIMatch[];
  redactedContent?: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  metadata: Record<string, any>;
}

/** Custom inspector function signature. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type InspectorFn = (content: any, toolName: string) => InspectionReport;

/** Configuration options for InspectorConfig. */
export interface InspectorConfigOptions {
  /** Master switch for content inspection. Default: true. */
  enabled?: boolean;
  /** PII detection configuration. */
  piiConfig?: PIIConfig;
  /** Maximum content size to inspect; larger content is blocked. Default: 10 MB. */
  maxContentSize?: number;
  /** Whether to inspect tool arguments before execution. Default: true. */
  inspectToolArgs?: boolean;
  /** Whether to inspect tool return values after execution. Default: true. */
  inspectToolResults?: boolean;
  /** Block the request if PII is detected. Default: true. */
  blockOnPII?: boolean;
  /** Additional inspection functions. */
  customInspectors?: InspectorFn[];
  /** Number of PII matches that triggers blocking when `blockOnPII` is false. Default: 1. */
  sensitiveDataThreshold?: number;
}

/** Immutable content inspector configuration value object. */
export class InspectorConfig {
  readonly enabled: boolean;
  readonly piiConfig: PIIConfig;
  readonly maxContentSize: number;
  readonly inspectToolArgs: boolean;
  readonly inspectToolResults: boolean;
  readonly blockOnPII: boolean;
  readonly customInspectors: readonly InspectorFn[];
  readonly sensitiveDataThreshold: number;

  constructor(options: InspectorConfigOptions = {}) {
    this.enabled = options.enabled ?? true;
    this.piiConfig = options.piiConfig ?? new PIIConfig();
    this.maxContentSize = options.maxContentSize ?? 10_000_000;
    this.inspectToolArgs = options.inspectToolArgs ?? true;
    this.inspectToolResults = options.inspectToolResults ?? true;
    this.blockOnPII = options.blockOnPII ?? true;
    this.customInspectors = Object.freeze(options.customInspectors ?? []);
    this.sensitiveDataThreshold = options.sensitiveDataThreshold ?? 1;
  }
}

/** Inspects content for sensitive data before allowing operations. */
export class ContentInspector {
  private readonly config: InspectorConfig;
  private readonly piiScanner: PIIScanner;

  constructor(config: InspectorConfig) {
    this.config = config;
    this.piiScanner = new PIIScanner(config.piiConfig);
  }

  /**
   * Inspect content for sensitive data.
   *
   * @param content   The content to inspect (string, object, or nested structure).
   * @param toolName  Name of the tool being used (for reporting).
   * @param direction `"outbound"` for data leaving the system, `"inbound"` for responses.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  inspect(content: any, toolName: string, direction: "outbound" | "inbound" = "outbound"): InspectionReport {
    if (!this.config.enabled) {
      return { result: InspectionResult.ALLOW, reason: "Inspection disabled", piiMatches: [], metadata: {} };
    }

    const contentStr = String(content);
    if (contentStr.length > this.config.maxContentSize) {
      return {
        result: InspectionResult.BLOCK,
        reason: `Content size ${contentStr.length} exceeds limit ${this.config.maxContentSize}`,
        piiMatches: [],
        metadata: { direction },
      };
    }

    const piiMatches = this.piiScanner.scan(content);

    if (piiMatches.length > 0) {
      if (this.config.blockOnPII || piiMatches.length >= this.config.sensitiveDataThreshold) {
        const topTypes = piiMatches.slice(0, 3).map(m => m.piiType).join(", ");
        return {
          result: InspectionResult.BLOCK,
          reason: `PII detected: ${piiMatches.length} matches (${topTypes}...)`,
          piiMatches,
          metadata: { direction },
        };
      } else {
        const redacted = this.piiScanner.redact(contentStr);
        return {
          result: InspectionResult.REDACT,
          reason: `PII redacted: ${piiMatches.length} matches`,
          piiMatches,
          redactedContent: redacted,
          metadata: { direction },
        };
      }
    }

    // Run custom inspectors
    for (const inspectorFn of this.config.customInspectors) {
      const report = inspectorFn(content, toolName);
      if (report.result === InspectionResult.BLOCK || report.result === InspectionResult.REDACT) {
        return report;
      }
    }

    return { result: InspectionResult.ALLOW, reason: "Content inspection passed", piiMatches: [], metadata: { direction } };
  }

  /** Inspect tool arguments before execution. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  inspectArgs(toolName: string, args: any[]): InspectionReport {
    if (!this.config.inspectToolArgs) {
      return { result: InspectionResult.ALLOW, reason: "Arg inspection disabled", piiMatches: [], metadata: {} };
    }
    return this.inspect({ args }, toolName, "outbound");
  }

  /** Inspect a tool result after execution. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  inspectResult(toolName: string, result: any): InspectionReport {
    if (!this.config.inspectToolResults) {
      return { result: InspectionResult.ALLOW, reason: "Result inspection disabled", piiMatches: [], metadata: {} };
    }
    return this.inspect(result, toolName, "inbound");
  }
}
