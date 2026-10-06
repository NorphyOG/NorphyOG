#!/usr/bin/env python3
"""Fetch and validate GitHub's public contribution calendar; no token required."""

import argparse
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
MONTHS = {name: index for index, name in enumerate(
    ("January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"), 1)}


class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells = {}
        self.tooltips = {}
        self.heading = []
        self.in_heading = False
        self.tooltip_id = None
        self.tooltip_text = []
        self.start = None
        self.end = None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        classes = attrs.get("class", "").split()
        if "js-calendar-graph" in classes and "data-from" in attrs:
            self.start = date.fromisoformat(attrs["data-from"][:10])
            self.end = date.fromisoformat(attrs["data-to"][:10])
        if "ContributionCalendar-day" in classes and "data-date" in attrs:
            cell_id = attrs.get("id")
            if not cell_id or cell_id in self.cells:
                raise ValueError("Contribution cell has a missing or duplicate ID")
            self.cells[cell_id] = attrs
        if tag == "h2" and attrs.get("id") == "js-contribution-activity-description":
            self.in_heading = True
        if tag == "tool-tip" and attrs.get("for"):
            self.tooltip_id = attrs["for"]
            self.tooltip_text = []

    def handle_data(self, text):
        if self.in_heading:
            self.heading.append(text)
        if self.tooltip_id is not None:
            self.tooltip_text.append(text)

    def handle_endtag(self, tag):
        if tag == "h2":
            self.in_heading = False
        if tag == "tool-tip" and self.tooltip_id is not None:
            if self.tooltip_id in self.tooltips:
                raise ValueError("Contribution cell has duplicate tooltips")
            self.tooltips[self.tooltip_id] = " ".join(
                "".join(self.tooltip_text).split())
            self.tooltip_id = None


def tooltip_count(text, day):
    """Use tooltip counts, never infer counts from GitHub's intensity level."""
    match = re.fullmatch(
        r"(No|[\d,]+) contributions? on ([A-Za-z]+) (\d{1,2})"
        r"(?:st|nd|rd|th)?(?:,? (\d{4}))?\.?", text)
    if not match:
        raise ValueError(f"Unrecognized contribution tooltip for {day}")
    count, month, number, year = match.groups()
    if MONTHS.get(month) != day.month or int(number) != day.day:
        raise ValueError(f"Tooltip date does not match cell date {day}")
    if year and int(year) != day.year:
        raise ValueError(f"Tooltip year does not match cell date {day}")
    return 0 if count == "No" else int(count.replace(",", ""))


def parse_calendar(document):
    parser = CalendarParser()
    parser.feed(document)
    if not parser.cells or parser.start is None or parser.end is None:
        raise ValueError("Response contains no complete GitHub contribution calendar")
    span = (parser.end - parser.start).days + 1
    if not 1 <= span <= 371:
        raise ValueError("Unexpected contribution calendar date range")
    total_match = re.search(r"([\d,]+)\s+contributions?\b", " ".join(parser.heading))
    if not total_match:
        raise ValueError("Missing contribution total in GitHub calendar heading")
    total = int(total_match.group(1).replace(",", ""))
    days = []
    for cell_id, attrs in parser.cells.items():
        day = date.fromisoformat(attrs["data-date"])
        level = int(attrs["data-level"])
        if not 0 <= level <= 4:
            raise ValueError(f"Unexpected contribution intensity for {day}")
        if cell_id not in parser.tooltips:
            raise ValueError(f"Missing count tooltip for {day}")
        count = tooltip_count(parser.tooltips[cell_id], day)
        if (count == 0) != (level == 0):
            raise ValueError(f"Contribution count and intensity disagree for {day}")
        days.append({"date": day.isoformat(), "count": count, "level": level})
    days.sort(key=lambda item: item["date"])
    expected = [(parser.start + timedelta(days=i)).isoformat() for i in range(span)]
    if [item["date"] for item in days] != expected:
        raise ValueError("Calendar dates are incomplete, duplicated or outside its range")
    if sum(item["count"] for item in days) != total:
        raise ValueError("Day counts do not match GitHub's displayed contribution total")
    return days, total, parser.start, parser.end


def summarise(days, as_of):
    monthly = {}
    longest = current_run = 0
    visible = [item for item in days if item["date"] <= as_of.isoformat()]
    for item in visible:
        month = item["date"][:7]
        monthly[month] = monthly.get(month, 0) + item["count"]
        current_run = current_run + 1 if item["count"] else 0
        longest = max(longest, current_run)
    streak = 0
    end = len(visible) - 1
    # An empty current day need not break a streak that is still in progress.
    if end >= 0 and visible[end]["date"] == as_of.isoformat() and not visible[end]["count"]:
        end -= 1
    if end >= 0 and visible[end]["date"] < (as_of - timedelta(days=1)).isoformat():
        end = -1
    while end >= 0 and visible[end]["count"]:
        streak += 1
        end -= 1
    return {
        "active_days": sum(item["count"] > 0 for item in visible),
        "longest_streak": longest,
        "current_streak": streak,
        "best_day": max(visible, key=lambda item: item["count"]) if visible else None,
        "monthly_totals": monthly,
    }


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--username", default="NorphyOG")
    cli.add_argument("--year", type=int, help="Calendar year instead of the current rolling calendar")
    cli.add_argument("--output", type=Path, default=ROOT / "data/contributions.json")
    args = cli.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", args.username):
        cli.error("username must be a valid GitHub username")
    today = datetime.now(timezone.utc).date()
    url = f"https://github.com/users/{args.username}/contributions"
    if args.year is not None:
        if not 2008 <= args.year <= today.year:
            cli.error("year must be between 2008 and the current year")
        url += "?" + urlencode({"from": f"{args.year}-01-01", "to": f"{args.year}-12-31"})
    try:
        request = Request(url, headers={"User-Agent": "NorphyOG-profile-art/1.0", "Accept": "text/html"})
        with urlopen(request, timeout=30) as response:
            if response.geturl().split("/", 3)[2] != "github.com":
                raise ValueError("GitHub redirected outside the expected source host")
            document = response.read(2_000_001)
        if len(document) > 2_000_000:
            raise ValueError("GitHub contribution response is unexpectedly large")
        days, total, start, end = parse_calendar(document.decode("utf-8"))
        fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        payload = {
            "schema_version": 1,
            "username": args.username,
            "source": url,
            "fetched_at": fetched_at,
            "period": {"start": start.isoformat(), "end": end.isoformat(),
                       "kind": "calendar_year" if args.year else "rolling"},
            "total": total,
            "stats": summarise(days, today),
            "days": days,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.output)
    except (HTTPError, URLError, OSError, ValueError, KeyError) as error:
        print(f"Could not refresh contribution data: {error}", file=sys.stderr)
        return 1
    print(f"Saved {len(days)} verified days and {total} contributions to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
