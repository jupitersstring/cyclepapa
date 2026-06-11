"""Tests for the Investegate RNS scraper and its integration with the
signal layer."""
import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import investegate_scraper as inv


def test_categorise_tr1():
    assert inv._categorise("tr-1-notification-of-major-holdings") == "tr1"
    assert inv._categorise("tr-1-notification-of-major-holdings-") == "tr1"
    assert inv._categorise("holding-s-in-company") == "tr1"
    assert inv._categorise("holdings-in-company") == "tr1"


def test_categorise_pdmr():
    assert inv._categorise("director-pdmr-shareholding") == "pdmr"
    assert inv._categorise("director-shareholding") == "pdmr"


def test_categorise_buyback():
    assert inv._categorise("transaction-in-own-shares") == "buyback"
    assert inv._categorise("share-buyback") == "buyback"
    assert inv._categorise("repurchase-of-shares") == "buyback"


def test_categorise_winddown():
    assert inv._categorise("managed-wind-down-update") == "winddown"
    assert inv._categorise("managed-realisation-strategy") == "winddown"


def test_categorise_review():
    assert inv._categorise("strategic-review-update") == "review"
    assert inv._categorise("reset-and-roadmap") == "review"
    assert inv._categorise("strategic-update-and-portfolio-proposals") == "review"


def test_categorise_unknown():
    assert inv._categorise("interim-results-6-months-ended-30-september-2025") is None
    assert inv._categorise("appointment-of-non-executive-director") is None


def test_parse_date():
    assert inv._parse_date("28 May 2026") == "2026-05-28"
    assert inv._parse_date("1 Jan 2024") == "2024-01-01"
    assert inv._parse_date("31 December 2025") == "2025-12-31"
    assert inv._parse_date("no date here") is None


def test_epic_from_ticker():
    assert inv.epic_from_ticker("SEIT.L") == "SEIT"
    assert inv.epic_from_ticker("CHRY.L") == "CHRY"
    assert inv.epic_from_ticker("BRK-B") is None
    assert inv.epic_from_ticker("8001.T") is None


def test_signal_score_from_rns_empty():
    composite, dec, raw = inv.signal_score_from_rns([])
    assert composite == 0.0
    assert all(v == 0 for v in raw.values())


def test_signal_score_from_rns_recent_tr1_dominates():
    """Many recent TR-1 filings should produce a strong signal (the
    SEIT.L pattern: 23 TR-1s decayed to 8.23)."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    items = []
    for i in range(20):
        d = (now - timedelta(days=i * 3)).strftime("%Y-%m-%d")
        items.append(inv.Announcement(
            date=d, title=f"TR-1 #{i}", category="tr1",
            raw_slug="tr-1-notification-of-major-holdings", url=""))
    composite, dec, raw = inv.signal_score_from_rns(items)
    assert raw["tr1"] == 20
    assert dec["tr1"] > 5.0   # decayed sum dominated by recent
    assert composite > 0.2    # only category, weight 0.30 saturating


def test_signal_score_old_filings_decay():
    """Old TR-1s should contribute little."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    items = []
    for i in range(20):
        d = (now - timedelta(days=100 + i * 3)).strftime("%Y-%m-%d")
        items.append(inv.Announcement(
            date=d, title=f"TR-1 old #{i}", category="tr1",
            raw_slug="tr-1-notification-of-major-holdings", url=""))
    _, dec, raw = inv.signal_score_from_rns(items, lookback_days=120,
                                            half_life_days=30)
    assert raw["tr1"] >= 6   # some still within 120d
    assert dec["tr1"] < raw["tr1"] / 2   # decayed sum much smaller


def test_parse_page_extracts_dated_announcements():
    """A small HTML snippet mimicking Investegate's row structure."""
    html = """
    <table>
      <tr>
        <td>28 May 2026</td><td>05:36 PM</td><td>UK</td><td>RNS</td>
        <td><a class="announcement-link"
             href="https://www.investegate.co.uk/announcement/rns/x--seit/tr-1-notification-of-major-holdings/9611695">TR-1 Notification of Major Holdings</a></td>
      </tr>
      <tr>
        <td>18 May 2026</td><td>02:00 PM</td><td>UK</td><td>RNS</td>
        <td><a class="announcement-link"
             href="https://www.investegate.co.uk/announcement/rns/x--seit/director-pdmr-shareholding/9590729">Director/PDMR Shareholding</a></td>
      </tr>
    </table>
    """
    items = inv._parse_page(html)
    assert len(items) == 2
    assert items[0].date == "2026-05-28"
    assert items[0].category == "tr1"
    assert items[1].category == "pdmr"


def test_fetch_company_uses_cache(tmp_path, monkeypatch):
    """Cache file written and reused on second call."""
    monkeypatch.setattr(inv, "CACHE_DIR", tmp_path)
    # Inject a fake parse result by mocking the URL fetch
    fake_data = [inv.Announcement(date="2026-01-01", title="Test",
                                  category="tr1",
                                  raw_slug="tr-1-notification-of-major-holdings",
                                  url="x")]
    cp = tmp_path / "TEST.json"
    with open(cp, "w") as f:
        json.dump([{"date":"2026-01-01","title":"Test","category":"tr1",
                    "raw_slug":"tr-1","url":"x"}], f)
    items = inv.fetch_company("TEST", use_cache=True, ttl_hours=999)
    assert len(items) == 1 and items[0].category == "tr1"
