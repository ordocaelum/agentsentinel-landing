/**
 * PII and sensitive data detection for AgentSentinel.
 */

/** Categories of personally identifiable information. */
export enum PIIType {
  CREDIT_CARD = "credit_card",
  SSN = "ssn",
  EMAIL = "email",
  PHONE = "phone",
  PRIVATE_KEY = "private_key",
  API_KEY = "api_key",
  AWS_CREDENTIALS = "aws_credentials",
  BANK_ACCOUNT = "bank_account",
  PASSPORT = "passport",
  DRIVERS_LICENSE = "drivers_license",
  IP_ADDRESS = "ip_address",
  CRYPTO_WALLET = "crypto_wallet",
  CUSTOM = "custom",
}

/** A detected PII match. */
export interface PIIMatch {
  /** The category of PII detected. */
  piiType: PIIType;
  /** The actual matched text (will be redacted in logs). */
  matchedText: string;
  /** Where in the data structure it was found, e.g. "args.body.cc_number". */
  fieldPath: string;
  /** Confidence score between 0.0 and 1.0. */
  confidence: number;
}

/** Configuration for PII detection. */
export interface PIIConfigOptions {
  /** Master switch for PII detection. Default: true. */
  enabled?: boolean;
  /**
   * If true, raise PIIDetectedError when PII is found in outbound data.
   * If false, just log a warning. Default: true.
   */
  blockOnDetection?: boolean;
  /** Which PII types to scan for. Default is all high-risk types. */
  detectTypes?: PIIType[];
  /** Additional regex patterns (name → pattern string) to detect as PII. */
  customPatterns?: Record<string, string>;
  /** Field paths that are allowed to contain PII. */
  allowlistedFields?: string[];
  /** Minimum confidence threshold (0.0–1.0) to trigger detection. Default: 0.7. */
  minConfidence?: number;
}

/** Immutable PII configuration value object. */
export class PIIConfig {
  readonly enabled: boolean;
  readonly blockOnDetection: boolean;
  readonly detectTypes: readonly PIIType[];
  readonly customPatterns: Readonly<Record<string, string>>;
  readonly allowlistedFields: readonly string[];
  readonly minConfidence: number;

  constructor(options: PIIConfigOptions = {}) {
    this.enabled = options.enabled ?? true;
    this.blockOnDetection = options.blockOnDetection ?? true;
    this.detectTypes = Object.freeze(options.detectTypes ?? [
      PIIType.CREDIT_CARD,
      PIIType.SSN,
      PIIType.PRIVATE_KEY,
      PIIType.API_KEY,
      PIIType.AWS_CREDENTIALS,
      PIIType.BANK_ACCOUNT,
      PIIType.CRYPTO_WALLET,
    ]);
    this.customPatterns = Object.freeze(options.customPatterns ?? {});
    this.allowlistedFields = Object.freeze(options.allowlistedFields ?? []);
    this.minConfidence = options.minConfidence ?? 0.7;
  }
}

/** Built-in detection patterns: PIIType → list of [pattern, confidence] tuples. */
const PII_PATTERNS: Partial<Record<PIIType, Array<[RegExp, number]>>> = {
  [PIIType.CREDIT_CARD]: [
    [/\b4[0-9]{3}[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}\b/gi, 0.95],  // Visa
    [/\b5[1-5][0-9]{2}[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}\b/gi, 0.95],  // Mastercard
    [/\b3[47][0-9]{2}[- ]?[0-9]{6}[- ]?[0-9]{5}\b/gi, 0.95],  // Amex
    [/\b6(?:011|5[0-9]{2})[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}\b/gi, 0.95],  // Discover
  ],
  [PIIType.SSN]: [
    [/\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b/g, 0.9],
    [/\b[0-9]{3} [0-9]{2} [0-9]{4}\b/g, 0.85],
  ],
  [PIIType.PRIVATE_KEY]: [
    [/-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----/gi, 0.99],
    [/-----BEGIN PGP PRIVATE KEY BLOCK-----/gi, 0.99],
  ],
  [PIIType.API_KEY]: [
    [/\b(?:sk-[a-zA-Z0-9]{48})\b/g, 0.95],   // OpenAI
    [/\b(?:sk-ant-[a-zA-Z0-9-]{95})\b/g, 0.95], // Anthropic
    [/\bAIza[0-9A-Za-z_-]{35}\b/g, 0.95],    // Google API
    [/\bghp_[a-zA-Z0-9]{36}\b/g, 0.95],      // GitHub PAT
    [/\bghr_[a-zA-Z0-9]{36}\b/g, 0.95],      // GitHub refresh token
    [/\bgho_[a-zA-Z0-9]{36}\b/g, 0.95],      // GitHub OAuth
  ],
  [PIIType.AWS_CREDENTIALS]: [
    [/\bAKIA[0-9A-Z]{16}\b/g, 0.95],   // AWS Access Key
    [/\bASIA[0-9A-Z]{16}\b/g, 0.95],   // AWS Temp Access Key
    [/\b[0-9a-zA-Z/+=]{40}\b/g, 0.6],  // AWS Secret Key (lower confidence)
  ],
  [PIIType.BANK_ACCOUNT]: [
    [/\b[A-Z]{2}[0-9]{2}[A-Z0-9]{4}[0-9]{7}(?:[A-Z0-9]?){0,16}\b/g, 0.9], // IBAN
  ],
  [PIIType.CRYPTO_WALLET]: [
    [/\b0x[a-fA-F0-9]{40}\b/g, 0.9],             // Ethereum
    [/\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b/g, 0.85], // Bitcoin
    [/\bbc1[a-zA-HJ-NP-Z0-9]{39,59}\b/g, 0.9],   // Bitcoin Bech32
  ],
  [PIIType.EMAIL]: [
    [/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, 0.8],
  ],
  [PIIType.PHONE]: [
    [/\b\+?1?[-.\s]?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b/g, 0.75],
  ],
  [PIIType.IP_ADDRESS]: [
    [/\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b/g, 0.7],
  ],
};

/** Scans data structures for PII. */
export class PIIScanner {
  private readonly config: PIIConfig;
  private readonly compiledPatterns: Map<PIIType, Array<[RegExp, number]>>;

  constructor(config: PIIConfig) {
    this.config = config;
    this.compiledPatterns = this._buildPatterns();
  }

  private _buildPatterns(): Map<PIIType, Array<[RegExp, number]>> {
    const result = new Map<PIIType, Array<[RegExp, number]>>();

    for (const piiType of this.config.detectTypes) {
      const patterns = PII_PATTERNS[piiType];
      if (patterns) {
        // Clone regexes to reset lastIndex between calls
        result.set(piiType, patterns.map(([re, conf]) => [new RegExp(re.source, re.flags), conf]));
      }
    }

    // Custom patterns
    const customEntries: Array<[RegExp, number]> = [];
    for (const [, pattern] of Object.entries(this.config.customPatterns)) {
      customEntries.push([new RegExp(pattern, "gi"), 0.9]);
    }
    if (customEntries.length > 0) {
      result.set(PIIType.CUSTOM, customEntries);
    }

    return result;
  }

  /**
   * Recursively scan data for PII.
   *
   * @param data  The data to scan (string, object, array, or nested combination).
   * @param path  Current path in the data structure for reporting.
   * @returns     All PII matches found above the configured confidence threshold.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  scan(data: any, path = "root"): PIIMatch[] {
    if (!this.config.enabled) return [];

    const matches: PIIMatch[] = [];

    if (typeof data === "string") {
      matches.push(...this._scanString(data, path));
    } else if (data !== null && typeof data === "object" && !Array.isArray(data)) {
      for (const [key, value] of Object.entries(data)) {
        const childPath = `${path}.${key}`;
        if (!this.config.allowlistedFields.includes(childPath)) {
          matches.push(...this.scan(value, childPath));
        }
      }
    } else if (Array.isArray(data)) {
      for (let i = 0; i < data.length; i++) {
        matches.push(...this.scan(data[i], `${path}[${i}]`));
      }
    }

    return matches.filter(m => m.confidence >= this.config.minConfidence);
  }

  private _scanString(text: string, path: string): PIIMatch[] {
    const matches: PIIMatch[] = [];

    for (const [piiType, patterns] of this.compiledPatterns) {
      for (const [regex, confidence] of patterns) {
        regex.lastIndex = 0; // reset stateful regex
        let match: RegExpExecArray | null;
        while ((match = regex.exec(text)) !== null) {
          matches.push({
            piiType,
            matchedText: match[0],
            fieldPath: path,
            confidence,
          });
        }
      }
    }

    return matches;
  }

  /** Quick check if data contains any PII. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  containsPII(data: any): boolean {
    return this.scan(data).length > 0;
  }

  /** Redact all PII from a string. */
  redact(text: string): string {
    let result = text;
    for (const [piiType, patterns] of this.compiledPatterns) {
      for (const [regex] of patterns) {
        const freshRegex = new RegExp(regex.source, regex.flags);
        result = result.replace(freshRegex, `[REDACTED-${piiType.toUpperCase()}]`);
      }
    }
    return result;
  }
}

/**
 * Validate a credit card number using the Luhn algorithm.
 *
 * Returns `true` if the number has a valid checksum, reducing false positives.
 */
export function luhnCheck(cardNumber: string): boolean {
  const digits = cardNumber.replace(/\D/g, "").split("").map(Number);
  if (digits.length < 13 || digits.length > 19) return false;

  let checksum = 0;
  for (let i = 0; i < digits.length; i++) {
    let digit = digits[digits.length - 1 - i];
    if (i % 2 === 1) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    checksum += digit;
  }

  return checksum % 10 === 0;
}
