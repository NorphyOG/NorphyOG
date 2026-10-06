"""Contract tests for public calendar parsing and the generated SVG."""

from copy import deepcopy
from datetime import date
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetch_contributions import parse_calendar, summarise  # noqa: E402
from render_heatmap_svg import render_svg  # noqa: E402


def fixture():
    # DOM order is weekday-major, not chronological. Tooltips are ID-linked.
    return '''<h2 id="js-contribution-activity-description">1,001 contributions in 2026</h2>
<div class="js-calendar-graph" data-from="2026-01-01 00:00:00 UTC" data-to="2026-01-03 23:59:59 UTC">
<td class="ContributionCalendar-day" id="third" data-date="2026-01-03" data-level="1"></td>
<td class="ContributionCalendar-day" id="first" data-date="2026-01-01" data-level="4"></td>
<td class="ContributionCalendar-day" id="second" data-date="2026-01-02" data-level="0"></td>
<tool-tip for="first">1,000 contributions on January 1st.</tool-tip>
<tool-tip for="second">No contributions on January 2nd.</tool-tip>
<tool-tip for="third">1 contribution on January 3rd.</tool-tip>
</div>'''


def payload():
    days, total, start, end = parse_calendar(fixture())
    return {"username": "NorphyOG", "days": days, "total": total,
            "fetched_at": "2026-01-03T12:00:00+00:00",
            "period": {"start": start.isoformat(), "end": end.isoformat()}}


class CalendarTests(unittest.TestCase):
    def test_tooltips_map_counts_to_dates_and_sort(self):
        days, total, start, end = parse_calendar(fixture())
        self.assertEqual(total, 1001)
        self.assertEqual([item["count"] for item in days], [1000, 0, 1])
        self.assertEqual(start, date(2026, 1, 1))
        self.assertEqual(end, date(2026, 1, 3))

    def test_error_page_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_calendar("<html><h1>Please log in</h1></html>")

    def test_missing_count_is_not_silently_zero(self):
        broken = fixture().replace('<tool-tip for="second">No contributions on January 2nd.</tool-tip>', '')
        with self.assertRaisesRegex(ValueError, "Missing count"):
            parse_calendar(broken)

    def test_tooltip_date_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            parse_calendar(fixture().replace("January 3rd", "January 2nd"))

    def test_missing_day_is_rejected(self):
        broken = fixture().replace('<td class="ContributionCalendar-day" id="second" data-date="2026-01-02" data-level="0"></td>', '')
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_calendar(broken)

    def test_total_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "total"):
            parse_calendar(fixture().replace("1,001 contributions", "999 contributions"))

    def test_intensity_is_not_treated_as_count(self):
        with self.assertRaisesRegex(ValueError, "disagree"):
            parse_calendar(fixture().replace('id="first" data-date="2026-01-01" data-level="4"',
                                             'id="first" data-date="2026-01-01" data-level="0"'))

    def test_streak_ignores_future_days_and_allows_empty_today(self):
        days = [{"date": f"2026-01-{n:02}", "count": count, "level": int(count > 0)}
                for n, count in enumerate([0, 2, 3, 0, 0, 0], 1)]
        result = summarise(days, date(2026, 1, 4))
        self.assertEqual(result["current_streak"], 2)
        self.assertEqual(result["longest_streak"], 2)
        self.assertEqual(result["monthly_totals"], {"2026-01": 5})
        self.assertEqual(result["active_days"], 2)
        self.assertEqual(summarise(days, date(2026, 2, 1))["current_streak"], 0)


class RenderingTests(unittest.TestCase):
    def test_svg_is_accessible_self_contained_and_dates_remain_exact(self):
        svg = render_svg(payload())
        document = ET.fromstring(svg)
        ns = {"s": "http://www.w3.org/2000/svg"}
        self.assertEqual(document.get("role"), "img")
        self.assertEqual(document.get("aria-labelledby"), "title desc")
        self.assertIsNotNone(document.find("s:title", ns))
        self.assertIsNotNone(document.find("s:desc", ns))
        cells = [element for element in document.findall("s:rect", ns)
                 if element.get("class") == "cell"]
        self.assertEqual(len(cells), 3)
        self.assertEqual(cells[0].find("s:title", ns).text, "2026-01-01: 1000 contributions")
        self.assertNotIn("<script", svg)
        self.assertNotIn("<image", svg)
        self.assertNotIn("opacity: 0", svg)
        self.assertIn("prefers-reduced-motion", svg)
        self.assertNotIn("infinite", svg)

    def test_tampered_json_is_rejected(self):
        document = deepcopy(payload())
        document["total"] += 1
        with self.assertRaisesRegex(ValueError, "total"):
            render_svg(document)
        document = deepcopy(payload())
        document["days"][0]["count"] = -1
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            render_svg(document)


if __name__ == "__main__":
    unittest.main()
