"""Tests for text/schema extractors."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arizona_leads.extractors import (
    extract_address_from_text,
    extract_emails,
    extract_phones,
)


def test_extract_emails_basic():
    text = "Contact us at hello@acme.com or support@test.org for help."
    assert set(extract_emails(text)) == {"hello@acme.com", "support@test.org"}


def test_extract_emails_filters_noise():
    text = "noreply@spam.com and real@business.com"
    assert extract_emails(text) == ["real@business.com"]


def test_extract_phones():
    text = "Call (602) 431-2111 or 480.573.0082"
    phones = extract_phones(text)
    assert "(602) 431-2111" in phones
    assert "480.573.0082" in phones


def test_extract_address_from_text():
    text = "We are located at 1234 E Camelback Rd, Phoenix, AZ 85018"
    result = extract_address_from_text(text)
    assert result is not None
    assert result["city"] == "Phoenix"
    assert result["state"] == "AZ"
