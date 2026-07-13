from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import reporting
except ModuleNotFoundError:
    reporting = None


def dates_between(start: date, end: date) -> set[str]:
    return {
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    }


class ReportingContractTests(unittest.TestCase):
    def test_latest_weekly_window_backs_up_to_all_four_sources(self) -> None:
        self.assertIsNotNone(
            reporting,
            "reporting must expose latest_aligned_14_day_window for the weekly contract",
        )
        source_dates = {
            "ga4": dates_between(date(2026, 6, 1), date(2026, 7, 14)),
            "shopify": dates_between(date(2026, 6, 1), date(2026, 7, 14)),
            "google_ads": dates_between(date(2026, 6, 1), date(2026, 7, 14)),
            "gsc": dates_between(date(2026, 6, 1), date(2026, 7, 12)),
        }
        window = reporting.latest_aligned_14_day_window(source_dates)
        self.assertEqual(window.current_start, date(2026, 7, 6))
        self.assertEqual(window.current_end, date(2026, 7, 12))
        self.assertEqual(window.previous_start, date(2026, 6, 29))
        self.assertEqual(window.previous_end, date(2026, 7, 5))


if __name__ == "__main__":
    unittest.main()
