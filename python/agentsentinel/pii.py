# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""PII and sensitive data detection for AgentSentinel."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple


class PIIType(Enum):
    """Categories of personally identifiable information."""
    CREDIT_CARD = "credit_card"
    SSN = "ssn"
    EMAIL = "email"
    PHONE = "phone"
    PRIVATE_KEY = "private_key"
    API_KEY = "api_key"
    AWS_CREDENTIALS = "aws_credentials"
    BANK_ACCOUNT = "bank_account"
    PASSPORT = "passport"
    DRIVERS_LICENSE = "drivers_license"
    IP_ADDRESS = "ip_address"
    CRYPTO_WALLET = "crypto_wallet"
    CUSTOM = "custom"


@dataclass
class PIIMatch:
    """A detected PII match."""
    pii_type: PIIType
    matched_text: str  # The actual matched text (for logging, will be redacted)
    field_path: str    # Where in the data it was found (e.g., "args.body.cc_number")
    confidence: float  # 0.0 - 1.0 confidence score


@dataclass
class PIIConfig:
    """Configuration for PII detection.

    Parameters
    ----------
    enabled:
        Master switch for PII detection. Default True.
    block_on_detection:
        If True, raise PIIDetectedError when PII found in outbound data.
        If False, just log a warning and redact from audit logs.
    detect_types:
        Which PII types to scan for. Default is all high-risk types.
    custom_patterns:
        Additional regex patterns to detect as PII.
    allowlisted_fields:
        Field paths that are allowed to contain PII (e.g., "args.user_email"
        when the tool legitimately needs an email).
    min_confidence:
        Minimum confidence threshold (0.0-1.0) to trigger detection.
    """
    enabled: bool = True
    block_on_detection: bool = True

    detect_types: List[PIIType] = field(default_factory=lambda: [
        PIIType.CREDIT_CARD,
        PIIType.SSN,
        PIIType.PRIVATE_KEY,
        PIIType.API_KEY,
        PIIType.AWS_CREDENTIALS,
        PIIType.BANK_ACCOUNT,
        PIIType.CRYPTO_WALLET,
    ])

    custom_patterns: Dict[str, str] = field(default_factory=dict)
    allowlisted_fields: List[str] = field(default_factory=list)
    min_confidence: float = 0.7


# Built-in detection patterns with confidence scores
PII_PATTERNS: Dict[PIIType, List[Tuple[str, float]]] = {
    PIIType.CREDIT_CARD: [
        # Visa, Mastercard, Amex, Discover with optional separators
        (r'\b4[0-9]{3}[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}\b', 0.95),  # Visa
        (r'\b5[1-5][0-9]{2}[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}\b', 0.95),  # Mastercard
        (r'\b3[47][0-9]{2}[- ]?[0-9]{6}[- ]?[0-9]{5}\b', 0.95),  # Amex
        (r'\b6(?:011|5[0-9]{2})[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}\b', 0.95),  # Discover
    ],
    PIIType.SSN: [
        (r'\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b', 0.9),
        (r'\b[0-9]{3} [0-9]{2} [0-9]{4}\b', 0.85),
    ],
    PIIType.PRIVATE_KEY: [
        (r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', 0.99),
        (r'-----BEGIN PGP PRIVATE KEY BLOCK-----', 0.99),
    ],
    PIIType.API_KEY: [
        (r'\b(?:sk-[a-zA-Z0-9]{48})\b', 0.95),  # OpenAI
        (r'\b(?:sk-ant-[a-zA-Z0-9-]{95})\b', 0.95),  # Anthropic
        (r'\bAIza[0-9A-Za-z_-]{35}\b', 0.95),  # Google API
        (r'\bghp_[a-zA-Z0-9]{36}\b', 0.95),  # GitHub PAT
        (r'\bghr_[a-zA-Z0-9]{36}\b', 0.95),  # GitHub refresh token
        (r'\bgho_[a-zA-Z0-9]{36}\b', 0.95),  # GitHub OAuth
    ],
    PIIType.AWS_CREDENTIALS: [
        (r'\bAKIA[0-9A-Z]{16}\b', 0.95),  # AWS Access Key
        (r'\bASIA[0-9A-Z]{16}\b', 0.95),  # AWS Temp Access Key
        (r'\b[0-9a-zA-Z/+=]{40}\b', 0.6),  # AWS Secret Key (lower confidence, many false positives)
    ],
    PIIType.BANK_ACCOUNT: [
        # US routing + account
        (r'\b[0-9]{9}\b.*\b[0-9]{10,17}\b', 0.7),
        # IBAN
        (r'\b[A-Z]{2}[0-9]{2}[A-Z0-9]{4}[0-9]{7}(?:[A-Z0-9]?){0,16}\b', 0.9),
    ],
    PIIType.CRYPTO_WALLET: [
        (r'\b0x[a-fA-F0-9]{40}\b', 0.9),  # Ethereum
        (r'\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b', 0.85),  # Bitcoin
        (r'\bbc1[a-zA-HJ-NP-Z0-9]{39,59}\b', 0.9),  # Bitcoin Bech32
    ],
    PIIType.EMAIL: [
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 0.8),
    ],
    PIIType.PHONE: [
        (r'\b\+?1?[-.\s]?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b', 0.75),
    ],
    PIIType.IP_ADDRESS: [
        (r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b', 0.7),
    ],
}


class PIIScanner:
    """Scans data structures for PII."""

    def __init__(self, config: PIIConfig):
        self.config = config
        self._compiled_patterns: Dict[PIIType, List[Tuple[re.Pattern, float]]] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for performance."""
        for pii_type in self.config.detect_types:
            if pii_type in PII_PATTERNS:
                self._compiled_patterns[pii_type] = [
                    (re.compile(pattern, re.IGNORECASE), confidence)
                    for pattern, confidence in PII_PATTERNS[pii_type]
                ]

        # Add custom patterns
        for name, pattern in self.config.custom_patterns.items():
            self._compiled_patterns[PIIType.CUSTOM] = self._compiled_patterns.get(PIIType.CUSTOM, [])
            self._compiled_patterns[PIIType.CUSTOM].append(
                (re.compile(pattern, re.IGNORECASE), 0.9)
            )

    def scan(self, data: Any, path: str = "root") -> List[PIIMatch]:
        """Recursively scan data for PII.

        Parameters
        ----------
        data:
            The data to scan (str, dict, list, or nested combination).
        path:
            Current path in the data structure for reporting.

        Returns
        -------
        List[PIIMatch]
            All PII matches found.
        """
        if not self.config.enabled:
            return []

        matches: List[PIIMatch] = []

        if isinstance(data, str):
            matches.extend(self._scan_string(data, path))
        elif isinstance(data, dict):
            for key, value in data.items():
                child_path = f"{path}.{key}"
                if child_path not in self.config.allowlisted_fields:
                    matches.extend(self.scan(value, child_path))
        elif isinstance(data, (list, tuple)):
            for i, item in enumerate(data):
                matches.extend(self.scan(item, f"{path}[{i}]"))

        return [m for m in matches if m.confidence >= self.config.min_confidence]

    def _scan_string(self, text: str, path: str) -> List[PIIMatch]:
        """Scan a string for PII patterns."""
        matches = []

        for pii_type, patterns in self._compiled_patterns.items():
            for regex, confidence in patterns:
                for match in regex.finditer(text):
                    matches.append(PIIMatch(
                        pii_type=pii_type,
                        matched_text=match.group(),
                        field_path=path,
                        confidence=confidence,
                    ))

        return matches

    def contains_pii(self, data: Any) -> bool:
        """Quick check if data contains any PII."""
        return len(self.scan(data)) > 0

    def redact(self, text: str) -> str:
        """Redact all PII from text."""
        result = text
        for pii_type, patterns in self._compiled_patterns.items():
            for regex, _ in patterns:
                result = regex.sub(f"[REDACTED-{pii_type.value.upper()}]", result)
        return result


def luhn_check(card_number: str) -> bool:
    """Validate credit card number using Luhn algorithm.

    This reduces false positives by verifying the checksum.
    """
    digits = [int(d) for d in card_number if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False

    # Luhn algorithm
    checksum = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit

    return checksum % 10 == 0
