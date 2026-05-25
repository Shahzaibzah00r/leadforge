"""Tests for deduplication and export logic."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from leadforge.export import dedupe_leads


def test_dedupe_by_domain():
    leads = [
        {"website": "https://example.com", "email": "", "phone": ""},
        {"website": "https://example.com/about", "email": "", "phone": ""},
    ]
    unique, dups = dedupe_leads(leads)
    assert len(unique) == 1
    assert dups == 1


def test_dedupe_by_phone():
    leads = [
        {"website": "", "email": "", "phone": "(602) 431-2111"},
        {"website": "", "email": "", "phone": "(602) 431-2111"},
    ]
    unique, dups = dedupe_leads(leads)
    assert len(unique) == 1
    assert dups == 1


def test_dedupe_skips_chamber_domains():
    leads = [
        {
            "website": "https://business.phoenixchamber.com/list/member/x",
            "email": "",
            "phone": "(602) 111-2222",
        },
        {
            "website": "https://business.phoenixchamber.com/list/member/y",
            "email": "",
            "phone": "(602) 333-4444",
        },
    ]
    unique, dups = dedupe_leads(leads)
    assert len(unique) == 2
    assert dups == 0
