#!/usr/bin/env python3
"""Render validated contribution JSON as a self-contained animated SVG."""

import argparse
from datetime import date, timedelta
from html import escape
import json
from pathlib import Path
import sys

from fetch_contributions import summarise

ROOT = Path(__file__).resolve().parent.parent
PALETTE = ("#17252b", "#124733", "#16744c", "#20aa70", "#00ed99")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def render_svg(payload):
    days = payload["days"]
    start = date.fromisoformat(payload["period"]["start"])
    end = date.fromisoformat(payload["period"]["end"])
    fetched_date = date.fromisoformat(payload["fetched_at"][:10])
    span = (end - start).days + 1
    expected = [(start + timedelta(days=i)).isoformat() for i in range(span)]
    if not 1 <= span <= 371 or [item["date"] for item in days] != expected:
        raise ValueError("Contribution dates must form one complete supported calendar")
    for item in days:
        if type(item["count"]) is not int or item["count"] < 0:
            raise ValueError("Contribution counts must be nonnegative integers")
        if type(item["level"]) is not int or not 0 <= item["level"] <= 4:
            raise ValueError("Contribution levels must be between zero and four")
        if (item["count"] == 0) != (item["level"] == 0):
            raise ValueError("Contribution counts and intensity levels disagree")
    total = sum(item["count"] for item in days)
    if type(payload["total"]) is not int or total != payload["total"]:
        raise ValueError("Contribution total does not match the dated cells")
    stats = summarise(days, fetched_date)
    username = escape(payload["username"])
    period = f"{start.strftime('%d %b %Y')} — {end.strftime('%d %b %Y')}"
    anchor = start - timedelta(days=(start.weekday() + 1) % 7)
    columns = ((end - anchor).days // 7) + 1
    step = min(16, 858 / columns)
    cell_size = step - 4
    graph_x, graph_y = 76, 102
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="304" viewBox="0 0 1000 304" role="img" aria-labelledby="title desc">
  <title id="title">{username}'s GitHub contribution calendar</title>
  <desc id="desc">{total:,} contributions from {escape(period)}. {stats['active_days']} active days; longest streak {stats['longest_streak']} days. Counts fetched from GitHub on {fetched_date.isoformat()}. Each square represents one day.</desc>
  <defs>
    <linearGradient id="panel" x2="1" y2="1"><stop stop-color="#0c1820"/><stop offset="1" stop-color="#0b111b"/></linearGradient>
  </defs>
  <style>
    text {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .muted {{ fill: #9aaebe; font-size: 12px; }}
    .cell {{ animation: reveal .38s ease-out both; }}
    @keyframes reveal {{ from {{ opacity: .25; transform: translateY(-3px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    @media (prefers-reduced-motion: reduce) {{ .cell {{ animation: none; }} }}
  </style>
  <rect x=".5" y=".5" width="999" height="303" rx="18" fill="url(#panel)" stroke="#294351"/>
  <rect x="28" y="28" width="5" height="21" rx="2" fill="#00ed99"/>
  <text x="45" y="44" fill="#e7eff4" font-size="17" font-weight="600">CONTRIBUTION / LOG</text>
  <text x="972" y="43" text-anchor="end" fill="#00ed99" font-size="17">{total:,} contributions</text>
  <text x="28" y="67" class="muted">{escape(period)}</text>
''']
    for label, row in (("Mon", 1), ("Wed", 3), ("Fri", 5)):
        parts.append(f'  <text x="29" y="{graph_y + row * 16 + 10}" class="muted">{label}</text>\n')
    last_month = None
    last_label_x = -100
    for item in days:
        day = date.fromisoformat(item["date"])
        column = (day - anchor).days // 7
        row = (day.weekday() + 1) % 7
        x, y = graph_x + column * step, graph_y + row * 16
        if day.month != last_month:
            if x - last_label_x > 28:
                parts.append(f'  <text x="{x:.2f}" y="91" class="muted">{MONTHS[day.month - 1]}</text>\n')
                last_label_x = x
            last_month = day.month
        delay = column * .016 + row * .025
        title = escape(f"{item['date']}: {item['count']} contribution{'s' if item['count'] != 1 else ''}")
        parts.append(f'  <rect class="cell" x="{x:.2f}" y="{y}" width="{cell_size:.2f}" height="12" rx="3" fill="{PALETTE[item["level"]]}" style="animation-delay:{delay:.3f}s"><title>{title}</title></rect>\n')
    parts.append('  <path d="M28 235H972" stroke="#294351"/>\n')
    parts.append(f'  <text x="28" y="259" class="muted">ACTIVE DAYS <tspan fill="#e7eff4">{stats["active_days"]}</tspan></text>\n')
    parts.append(f'  <text x="267" y="259" class="muted">LONGEST STREAK <tspan fill="#e7eff4">{stats["longest_streak"]} days</tspan></text>\n')
    best = stats["best_day"]["count"] if stats["best_day"] else 0
    parts.append(f'  <text x="576" y="259" class="muted">BEST DAY <tspan fill="#e7eff4">{best}</tspan></text>\n')
    parts.append('  <text x="785" y="258" class="muted">Less</text>\n')
    for index, colour in enumerate(PALETTE):
        parts.append(f'  <rect x="{827 + index * 16}" y="248" width="12" height="12" rx="3" fill="{colour}"/>\n')
    parts.append('  <text x="918" y="258" class="muted">More</text>\n')
    parts.append(f'  <text x="28" y="284" class="muted">PUBLIC GITHUB CALENDAR · UPDATED {fetched_date.isoformat()}</text>\n')
    parts.append('  <text x="972" y="284" text-anchor="end" fill="#66a5ee" font-size="11">GENERATED HERE / NO STATS SERVICE</text>\n</svg>\n')
    return "".join(parts)


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--input", type=Path, default=ROOT / "data/contributions.json")
    cli.add_argument("--output", type=Path, default=ROOT / "assets/contrib-heatmap.svg")
    args = cli.parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        svg = render_svg(payload)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(svg, encoding="utf-8")
        temporary.replace(args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Could not render contribution heatmap: {error}", file=sys.stderr)
        return 1
    print(f"Rendered contribution calendar to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
