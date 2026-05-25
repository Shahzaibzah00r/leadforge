"""Tests for utility functions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from leadforge.utils import (
    matches_niche,
    normalize_domain,
    normalize_phone,
    score_lead,
)


def test_normalize_phone_ten_digits():
    assert normalize_phone("6024312111") == "(602) 431-2111"


def test_normalize_phone_eleven_digits():
    assert normalize_phone("16024312111") == "(602) 431-2111"


def test_normalize_phone_formatted():
    assert normalize_phone("(480) 573-0082") == "(480) 573-0082"


def test_normalize_domain():
    assert normalize_domain("https://www.example.com/path") == "example.com"
    assert normalize_domain("http://subdomain.example.co.uk") == "example.co.uk"


def test_matches_niche():
    assert matches_niche("Desert Hills Dental Care") is True
    assert matches_niche("Bob's Burgers") is False


def test_score_lead():
    assert score_lead({"business_name": "X", "website": "https://x.com"}) == 2
    assert score_lead({"phone": "(602) 555-1234", "email": "a@b.com"}) == 2
    assert score_lead({"city": "Phoenix", "state": "AZ"}) == 1
    assert score_lead({}) == 0
