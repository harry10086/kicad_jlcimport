"""Tests for api.py - validation and response parsing."""

from unittest.mock import patch
from urllib.error import URLError

import pytest

from kicad_jlcimport.easyeda.api import fetch_product_image, filter_by_min_stock, filter_by_type, validate_lcsc_id


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

    @patch("kicad_jlcimport.easyeda.api._urlopen", side_effect=URLError("network down"))
    def test_allows_jlcpcb_domain(self, mock_urlopen):
        # Should pass SSRF validation and attempt the fetch (mock returns URLError)
        result = fetch_product_image("https://jlcpcb.com/product/C427602")
        assert result is None
        mock_urlopen.assert_called_once()

    @patch("kicad_jlcimport.easyeda.api._urlopen", side_effect=URLError("network down"))
    def test_allows_lcsc_domain(self, mock_urlopen):
        result = fetch_product_image("https://lcsc.com/product/C427602")
        assert result is None
        mock_urlopen.assert_called_once()


class TestFilterByMinStock:
    """Test minimum stock count filtering."""

    _SAMPLE_RESULTS = [
        {"lcsc": "C1", "stock": 0, "model": "R1"},
        {"lcsc": "C2", "stock": 5, "model": "R2"},
        {"lcsc": "C3", "stock": 50, "model": "R3"},
        {"lcsc": "C4", "stock": 500, "model": "R4"},
        {"lcsc": "C5", "stock": 5000, "model": "R5"},
        {"lcsc": "C6", "stock": 50000, "model": "R6"},
        {"lcsc": "C7", "stock": None, "model": "R7"},
    ]

    def test_min_stock_zero_returns_all(self):
        result = filter_by_min_stock(self._SAMPLE_RESULTS, 0)
        assert len(result) == 7

    def test_min_stock_one_excludes_zero_and_none(self):
        result = filter_by_min_stock(self._SAMPLE_RESULTS, 1)
        assert len(result) == 5
        codes = [r["lcsc"] for r in result]
        assert "C1" not in codes  # stock=0
        assert "C7" not in codes  # stock=None

    def test_min_stock_10(self):
        result = filter_by_min_stock(self._SAMPLE_RESULTS, 10)
        assert len(result) == 4
        codes = [r["lcsc"] for r in result]
        assert "C2" not in codes  # stock=5

    def test_min_stock_100(self):
        result = filter_by_min_stock(self._SAMPLE_RESULTS, 100)
        assert len(result) == 3
        codes = [r["lcsc"] for r in result]
        assert set(codes) == {"C4", "C5", "C6"}

    def test_min_stock_1000(self):
        result = filter_by_min_stock(self._SAMPLE_RESULTS, 1000)
        assert len(result) == 2
        codes = [r["lcsc"] for r in result]
        assert set(codes) == {"C5", "C6"}

    def test_min_stock_10000(self):
        result = filter_by_min_stock(self._SAMPLE_RESULTS, 10000)
        assert len(result) == 1
        assert result[0]["lcsc"] == "C6"

    def test_min_stock_higher_than_all_returns_empty(self):
        result = filter_by_min_stock(self._SAMPLE_RESULTS, 100000)
        assert result == []

    def test_empty_input(self):
        result = filter_by_min_stock([], 100)
        assert result == []

    def test_negative_min_stock_returns_all(self):
        result = filter_by_min_stock(self._SAMPLE_RESULTS, -5)
        assert len(result) == 7

    def test_does_not_mutate_input(self):
        original = [{"lcsc": "C1", "stock": 10}]
        filter_by_min_stock(original, 100)
        assert len(original) == 1

    def test_missing_stock_key_treated_as_zero(self):
        results = [{"lcsc": "C1", "model": "R1"}]
        assert filter_by_min_stock(results, 1) == []

    def test_exact_threshold_included(self):
        results = [{"lcsc": "C1", "stock": 100}]
        assert len(filter_by_min_stock(results, 100)) == 1


class TestFilterByType:
    """Test part type filtering."""

    _SAMPLE_RESULTS = [
        {"lcsc": "C1", "type": "Basic", "stock": 100},
        {"lcsc": "C2", "type": "Extended", "stock": 200},
        {"lcsc": "C3", "type": "Basic", "stock": 50},
        {"lcsc": "C4", "type": "Extended", "stock": 300},
        {"lcsc": "C5", "type": "Extended", "stock": 10},
    ]

    def test_empty_type_returns_all(self):
        result = filter_by_type(self._SAMPLE_RESULTS, "")
        assert len(result) == 5

    def test_none_type_returns_all(self):
        result = filter_by_type(self._SAMPLE_RESULTS, None)
        assert len(result) == 5

    def test_filter_basic(self):
        result = filter_by_type(self._SAMPLE_RESULTS, "Basic")
        assert len(result) == 2
        assert all(r["type"] == "Basic" for r in result)

    def test_filter_extended(self):
        result = filter_by_type(self._SAMPLE_RESULTS, "Extended")
        assert len(result) == 3
        assert all(r["type"] == "Extended" for r in result)

    def test_unmatched_type_returns_empty(self):
        result = filter_by_type(self._SAMPLE_RESULTS, "Unknown")
        assert result == []

    def test_empty_input(self):
        result = filter_by_type([], "Basic")
        assert result == []

    def test_does_not_mutate_input(self):
        original = [{"lcsc": "C1", "type": "Basic"}]
        filter_by_type(original, "Extended")
        assert len(original) == 1

    def test_missing_type_key_excluded(self):
        results = [{"lcsc": "C1", "stock": 10}]
        assert filter_by_type(results, "Basic") == []
