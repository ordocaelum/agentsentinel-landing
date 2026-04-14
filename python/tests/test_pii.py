"""Tests for PII detection (pii.py)."""

import pytest

from agentsentinel import PIIConfig, PIIMatch, PIIScanner, PIIType, luhn_check


# ---------------------------------------------------------------------------
# Luhn check
# ---------------------------------------------------------------------------

class TestLuhnCheck:
    def test_valid_visa_card(self):
        assert luhn_check("4532015112830366") is True

    def test_valid_mastercard(self):
        assert luhn_check("5425233430109903") is True

    def test_invalid_card(self):
        assert luhn_check("1234567890123456") is False

    def test_too_short(self):
        assert luhn_check("123456") is False

    def test_too_long(self):
        assert luhn_check("12345678901234567890") is False

    def test_with_separators(self):
        # Luhn check strips non-digits
        assert luhn_check("4532-0151-1283-0366") is True


# ---------------------------------------------------------------------------
# PIIScanner — credit cards
# ---------------------------------------------------------------------------

class TestCreditCardDetection:
    def setup_method(self):
        self.scanner = PIIScanner(PIIConfig(detect_types=[PIIType.CREDIT_CARD]))

    def test_detects_visa(self):
        matches = self.scanner.scan("Card: 4532015112830366")
        assert any(m.pii_type == PIIType.CREDIT_CARD for m in matches)

    def test_detects_mastercard(self):
        matches = self.scanner.scan("Pay with 5425233430109903")
        assert any(m.pii_type == PIIType.CREDIT_CARD for m in matches)

    def test_detects_amex(self):
        matches = self.scanner.scan("AMEX: 371449635398431")
        assert any(m.pii_type == PIIType.CREDIT_CARD for m in matches)

    def test_detects_card_with_separators(self):
        matches = self.scanner.scan("4532-0151-1283-0366")
        assert any(m.pii_type == PIIType.CREDIT_CARD for m in matches)

    def test_detects_card_in_dict(self):
        data = {"payment": {"card_number": "4532015112830366"}}
        matches = self.scanner.scan(data)
        assert any(m.pii_type == PIIType.CREDIT_CARD for m in matches)
        assert any("payment.card_number" in m.field_path for m in matches)

    def test_no_false_positive_random_string(self):
        matches = self.scanner.scan("Hello world, no sensitive data here.")
        assert len(matches) == 0


# ---------------------------------------------------------------------------
# PIIScanner — SSN
# ---------------------------------------------------------------------------

class TestSSNDetection:
    def setup_method(self):
        self.scanner = PIIScanner(PIIConfig(detect_types=[PIIType.SSN]))

    def test_detects_ssn_with_dashes(self):
        matches = self.scanner.scan("SSN: 123-45-6789")
        assert any(m.pii_type == PIIType.SSN for m in matches)

    def test_detects_ssn_with_spaces(self):
        matches = self.scanner.scan("SSN: 123 45 6789")
        assert any(m.pii_type == PIIType.SSN for m in matches)


# ---------------------------------------------------------------------------
# PIIScanner — private keys
# ---------------------------------------------------------------------------

class TestPrivateKeyDetection:
    def setup_method(self):
        self.scanner = PIIScanner(PIIConfig(detect_types=[PIIType.PRIVATE_KEY]))

    def test_detects_rsa_private_key(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA..."
        matches = self.scanner.scan(text)
        assert any(m.pii_type == PIIType.PRIVATE_KEY for m in matches)

    def test_detects_generic_private_key(self):
        text = "-----BEGIN PRIVATE KEY-----\nMIIEpAIBAAKCAQEA..."
        matches = self.scanner.scan(text)
        assert any(m.pii_type == PIIType.PRIVATE_KEY for m in matches)

    def test_detects_pgp_private_key(self):
        text = "-----BEGIN PGP PRIVATE KEY BLOCK-----\nVersion: GnuPG"
        matches = self.scanner.scan(text)
        assert any(m.pii_type == PIIType.PRIVATE_KEY for m in matches)


# ---------------------------------------------------------------------------
# PIIScanner — API keys
# ---------------------------------------------------------------------------

class TestAPIKeyDetection:
    def setup_method(self):
        self.scanner = PIIScanner(PIIConfig(detect_types=[PIIType.API_KEY]))

    def test_detects_github_pat(self):
        token = "ghp_" + "a" * 36
        matches = self.scanner.scan(f"Authorization: Bearer {token}")
        assert any(m.pii_type == PIIType.API_KEY for m in matches)

    def test_detects_google_api_key(self):
        key = "AIza" + "A" * 35
        matches = self.scanner.scan(f"key={key}")
        assert any(m.pii_type == PIIType.API_KEY for m in matches)


# ---------------------------------------------------------------------------
# PIIScanner — AWS credentials
# ---------------------------------------------------------------------------

class TestAWSCredentialsDetection:
    def setup_method(self):
        self.scanner = PIIScanner(PIIConfig(detect_types=[PIIType.AWS_CREDENTIALS]))

    def test_detects_aws_access_key(self):
        matches = self.scanner.scan("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE")
        assert any(m.pii_type == PIIType.AWS_CREDENTIALS for m in matches)

    def test_detects_aws_temp_key(self):
        matches = self.scanner.scan("ASIA" + "A" * 16)
        assert any(m.pii_type == PIIType.AWS_CREDENTIALS for m in matches)


# ---------------------------------------------------------------------------
# PIIScanner — crypto wallets
# ---------------------------------------------------------------------------

class TestCryptoWalletDetection:
    def setup_method(self):
        self.scanner = PIIScanner(PIIConfig(detect_types=[PIIType.CRYPTO_WALLET]))

    def test_detects_ethereum_address(self):
        matches = self.scanner.scan("Send to 0x742d35Cc6634C0532925a3b844Bc454e4438f44e")
        assert any(m.pii_type == PIIType.CRYPTO_WALLET for m in matches)

    def test_detects_bitcoin_bech32(self):
        matches = self.scanner.scan("bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq")
        assert any(m.pii_type == PIIType.CRYPTO_WALLET for m in matches)


# ---------------------------------------------------------------------------
# PIIScanner — nested structures
# ---------------------------------------------------------------------------

class TestNestedScan:
    def setup_method(self):
        self.scanner = PIIScanner(PIIConfig(
            detect_types=[PIIType.CREDIT_CARD, PIIType.SSN],
        ))

    def test_scans_nested_dict(self):
        data = {
            "user": {
                "name": "Alice",
                "ssn": "123-45-6789",
                "payment": {
                    "card": "4532015112830366",
                },
            },
        }
        matches = self.scanner.scan(data)
        types = {m.pii_type for m in matches}
        assert PIIType.SSN in types
        assert PIIType.CREDIT_CARD in types

    def test_scans_list(self):
        data = ["normal text", "SSN: 123-45-6789", "more normal text"]
        matches = self.scanner.scan(data)
        assert any(m.pii_type == PIIType.SSN for m in matches)

    def test_field_path_reported_correctly(self):
        data = {"billing": {"cc": "4532015112830366"}}
        matches = self.scanner.scan(data)
        assert any("billing.cc" in m.field_path for m in matches)


# ---------------------------------------------------------------------------
# PIIScanner — allowlisting
# ---------------------------------------------------------------------------

class TestAllowlisting:
    def test_allowlisted_field_not_scanned(self):
        config = PIIConfig(
            detect_types=[PIIType.CREDIT_CARD],
            allowlisted_fields=["root.payment.card"],
        )
        scanner = PIIScanner(config)
        data = {"payment": {"card": "4532015112830366"}}
        matches = scanner.scan(data)
        assert len(matches) == 0

    def test_non_allowlisted_field_still_scanned(self):
        config = PIIConfig(
            detect_types=[PIIType.CREDIT_CARD],
            allowlisted_fields=["root.payment.card"],
        )
        scanner = PIIScanner(config)
        data = {"payment": {"other_card": "4532015112830366"}}
        matches = scanner.scan(data)
        assert len(matches) > 0


# ---------------------------------------------------------------------------
# PIIScanner — custom patterns
# ---------------------------------------------------------------------------

class TestCustomPatterns:
    def test_custom_pattern_detected(self):
        config = PIIConfig(
            detect_types=[],
            custom_patterns={"employee_id": r'EMP-[0-9]{6}'},
        )
        scanner = PIIScanner(config)
        matches = scanner.scan("Employee EMP-123456 submitted expense")
        assert any(m.pii_type == PIIType.CUSTOM for m in matches)


# ---------------------------------------------------------------------------
# PIIScanner — redact
# ---------------------------------------------------------------------------

class TestRedact:
    def test_redacts_ssn(self):
        scanner = PIIScanner(PIIConfig(detect_types=[PIIType.SSN]))
        result = scanner.redact("My SSN is 123-45-6789 please keep secret")
        assert "123-45-6789" not in result
        assert "[REDACTED-SSN]" in result

    def test_redacts_credit_card(self):
        scanner = PIIScanner(PIIConfig(detect_types=[PIIType.CREDIT_CARD]))
        result = scanner.redact("Card: 4532015112830366")
        assert "4532015112830366" not in result
        assert "[REDACTED-CREDIT_CARD]" in result


# ---------------------------------------------------------------------------
# PIIScanner — disabled
# ---------------------------------------------------------------------------

class TestDisabledScanner:
    def test_disabled_scanner_returns_no_matches(self):
        config = PIIConfig(enabled=False)
        scanner = PIIScanner(config)
        matches = scanner.scan("SSN: 123-45-6789 Card: 4532015112830366")
        assert len(matches) == 0


# ---------------------------------------------------------------------------
# PIIScanner — confidence threshold
# ---------------------------------------------------------------------------

class TestConfidenceThreshold:
    def test_high_threshold_filters_low_confidence(self):
        # AWS secret key pattern has confidence 0.6
        config = PIIConfig(
            detect_types=[PIIType.AWS_CREDENTIALS],
            min_confidence=0.9,
        )
        scanner = PIIScanner(config)
        # AKIA keys have confidence 0.95 so should still be detected
        matches = scanner.scan("AKIAIOSFODNN7EXAMPLE")
        assert any(m.pii_type == PIIType.AWS_CREDENTIALS for m in matches)
