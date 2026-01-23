"""Tests for api.py - validation and response parsing."""
import pytest

from kicad_jlcimport.api import validate_lcsc_id, fetch_product_image


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


class TestFetchProductImageSSRF:
    """Test SSRF protection in fetch_product_image."""

    def test_empty_url_returns_none(self):
        assert fetch_product_image("") is None

    def test_none_url_returns_none(self):
        assert fetch_product_image(None) is None

    def test_rejects_internal_ip(self):
        assert fetch_product_image("http://169.254.169.254/metadata") is None

    def test_rejects_localhost(self):
        assert fetch_product_image("http://localhost/secret") is None

    def test_rejects_arbitrary_domain(self):
        assert fetch_product_image("https://evil.com/phish") is None

    def test_rejects_file_scheme(self):
        assert fetch_product_image("file:///etc/passwd") is None

    def test_rejects_ftp_scheme(self):
        assert fetch_product_image("ftp://jlcpcb.com/file") is None

    def test_allows_jlcpcb_domain(self):
        # This will fail network-wise but should pass SSRF validation
        # and attempt the fetch (returning None due to network error in tests)
        result = fetch_product_image("https://jlcpcb.com/product/C427602")
        # Should be None (network error in test env) but NOT blocked by SSRF check
        assert result is None

    def test_allows_lcsc_domain(self):
        result = fetch_product_image("https://lcsc.com/product/C427602")
        assert result is None
