"""Tests for api.py - validation and response parsing."""
import pytest

from JLCImport.api import validate_lcsc_id


class TestValidateLcscId:
    def test_valid_id_with_prefix(self):
        assert validate_lcsc_id("C427602") == "C427602"

    def test_valid_id_without_prefix(self):
        assert validate_lcsc_id("427602") == "C427602"

    def test_valid_id_lowercase(self):
        assert validate_lcsc_id("c427602") == "C427602"

    def test_valid_id_with_whitespace(self):
        assert validate_lcsc_id("  C427602  ") == "C427602"

    def test_valid_single_digit(self):
        assert validate_lcsc_id("C1") == "C1"

    def test_valid_12_digits(self):
        assert validate_lcsc_id("C123456789012") == "C123456789012"

    def test_invalid_empty(self):
        with pytest.raises(ValueError, match="Invalid LCSC part number"):
            validate_lcsc_id("")

    def test_invalid_no_digits(self):
        with pytest.raises(ValueError, match="Invalid LCSC part number"):
            validate_lcsc_id("CABC")

    def test_invalid_too_many_digits(self):
        with pytest.raises(ValueError, match="Invalid LCSC part number"):
            validate_lcsc_id("C1234567890123")  # 13 digits

    def test_invalid_special_chars(self):
        with pytest.raises(ValueError, match="Invalid LCSC part number"):
            validate_lcsc_id("C123/../../etc")

    def test_invalid_url_injection(self):
        with pytest.raises(ValueError, match="Invalid LCSC part number"):
            validate_lcsc_id("C123?param=value")

    def test_invalid_mixed_alpha_numeric(self):
        with pytest.raises(ValueError, match="Invalid LCSC part number"):
            validate_lcsc_id("C12AB34")

    def test_whitespace_only(self):
        with pytest.raises(ValueError, match="Invalid LCSC part number"):
            validate_lcsc_id("   ")
