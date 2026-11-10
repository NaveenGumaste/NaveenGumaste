
"""Collect a complete 365-day public GitHub contribution calendar.

Uses only the Python 3.11+ standard library; no authentication is required.
GitHub serves one calendar year per response, so cross-year windows require
separate requests. Only requested dates are included, never future padding.

Reusable entry points: parse_calendar(html, start, end),
fetch_contributions(username=DEFAULT_USERNAME, end_date=None), and
write_contributions(document, output). Dates passed to these functions are
``datetime.date`` objects. Parsing and fetching raise ContributionError on
incomplete or ambiguous data; writing returns whether the file changed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from http.client import HTTPException
from pathlib import Path
from typing import TypedDict
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_USERNAME = "NaveenGumaste"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "contributions.json"
WINDOW_DAYS = 365
TIMEOUT_SECONDS = 30
_COUNT_PATTERN = re.compile(
    r"(No|[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+) contributions? on .+",
    re.IGNORECASE,
)


class DailyContribution(TypedDict):
    date: str
    count: int
    level: int


ContributionDocument = TypedDict(
    "ContributionDocument",
    {"username": str, "from": str, "to": str, "days": list[DailyContribution]},
)


class ContributionError(RuntimeError):
    """The requested calendar could not be collected reliably."""


def utc_today() -> date:
    return datetime.now(UTC).date()


def _iso_date(value: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError(f"expected YYYY-MM-DD, got {value!r}")
    return date.fromisoformat(value)


def date_window(end_date: date | None = None) -> tuple[date, date]:
    today = utc_today()
    end = today if end_date is None else end_date
    if end > today:
        raise ContributionError(f"End date {end} is after today ({today}, UTC)")
    try:
        return end - timedelta(days=WINDOW_DAYS - 1), end
    except OverflowError as exc:
        raise ContributionError(f"End date {end} cannot cover {WINDOW_DAYS} days") from exc


class _CalendarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cells: list[dict[str, str | None]] = []
        self.tooltips: dict[str, list[str]] = {}
        self.tooltip_target: str | None = None
        self.tooltip_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "td" and "data-date" in attributes:
            self.cells.append(attributes)
        if tag == "tool-tip":
            if self.tooltip_parts is not None:
                raise ContributionError("Malformed calendar: nested tool-tip elements")
            self.tooltip_target = attributes.get("for")
            self.tooltip_parts = []

    def handle_data(self, data: str) -> None:
        if self.tooltip_parts is not None:
            self.tooltip_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "tool-tip" and self.tooltip_parts is not None:
            if self.tooltip_target:
                self.tooltips.setdefault(self.tooltip_target, []).append(
                    "".join(self.tooltip_parts)
                )
            self.tooltip_target = None
            self.tooltip_parts = None


def parse_calendar(html: str, start: date, end: date) -> list[DailyContribution]:
    """Correlate dated cells with tooltip counts and require every requested day.

    Markup may be column-major and tooltips may precede or follow their cells.
    Cells outside the requested range are ignored, including future placeholders.
    Zero is accepted only when explicitly present in the matching tooltip.
    """
    if start > end:
        raise ContributionError(f"Invalid date range: {start} is after {end}")
    parser = _CalendarParser()
    parser.feed(html)
    parser.close()
    if parser.tooltip_parts is not None:
        raise ContributionError("Malformed calendar: unclosed tool-tip element")

    days: dict[date, DailyContribution] = {}
    seen_ids: set[str] = set()
    for cell in parser.cells:
        raw_date = cell.get("data-date")
        try:
            cell_date = _iso_date(raw_date or "")
        except ValueError as exc:
            raise ContributionError(f"Invalid calendar date: {raw_date!r}") from exc
        if not start <= cell_date <= end:
            continue
        if cell_date in days:
            raise ContributionError(f"Duplicate calendar date: {cell_date}")
        cell_id = cell.get("id")
        if not cell_id:
            raise ContributionError(f"Missing cell id for {cell_date}")
        if cell_id in seen_ids:
            raise ContributionError(f"Duplicate calendar cell id: {cell_id!r}")
        seen_ids.add(cell_id)
        raw_level = cell.get("data-level")
        if raw_level not in ("0", "1", "2", "3", "4"):
            raise ContributionError(f"Invalid contribution level {raw_level!r} for {cell_date}")
        level = int(raw_level)
        tooltips = parser.tooltips.get(cell_id, [])
        if not tooltips:
            raise ContributionError(f"Missing count tooltip for {cell_date} (id={cell_id!r})")
        if len(tooltips) != 1:
            raise ContributionError(f"Duplicate count tooltips for {cell_date} (id={cell_id!r})")
        text = " ".join(tooltips[0].split())
        match = _COUNT_PATTERN.fullmatch(text)
        if match is None:
            raise ContributionError(f"Unrecognized count tooltip for {cell_date}: {text!r}")
        raw_count = match.group(1)
        count = 0 if raw_count.lower() == "no" else int(raw_count.replace(",", ""))
        if (count == 0) != (level == 0):
            raise ContributionError(
                f"Count/level mismatch for {cell_date}: count={count}, level={level}"
            )
        days[cell_date] = {"date": cell_date.isoformat(), "count": count, "level": level}

    expected = (end - start).days + 1
    if len(days) != expected:
        missing = [
            (start + timedelta(days=offset)).isoformat()
            for offset in range(expected)
            if start + timedelta(days=offset) not in days
        ]
        preview = ", ".join(missing[:5])
        if len(missing) > 5:
            preview += ", ..."
        raise ContributionError(
            f"Incomplete calendar for {start} to {end}: expected {expected} days, "
            f"found {len(days)}; missing {len(missing)} days: {preview}"
        )
    return [days[day] for day in sorted(days)]


def fetch_calendar_html(username: str, start: date, end: date) -> str:
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", username):
        raise ContributionError(f"Invalid GitHub username: {username!r}")
    query = urlencode({"from": start.isoformat(), "to": end.isoformat()})
    url = f"https://github.com/users/{username}/contributions?{query}"
    request = Request(
        url,
        headers={
            "User-Agent": "public-profile-contribution-collector/1.0",
            "Accept": "text/html",
            "Accept-Language": "en-US",
        },
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            encoding = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(encoding)
    except HTTPError as exc:
        exc.close()
        raise ContributionError(f"HTTP {exc.code} {exc.reason} fetching {url}") from exc
    except URLError as exc:
        raise ContributionError(f"Network error fetching {url}: {exc.reason}") from exc
    except (OSError, HTTPException) as exc:
        raise ContributionError(f"Network error fetching {url}: {exc}") from exc
    except (UnicodeError, LookupError) as exc:
        raise ContributionError(f"Cannot decode calendar HTML from {url}: {exc}") from exc


def fetch_contributions(
    username: str = DEFAULT_USERNAME, end_date: date | None = None
) -> ContributionDocument:
    """Fetch exactly 365 UTC calendar days, including the chosen end date."""
    start, end = date_window(end_date)
    days: list[DailyContribution] = []
    segment_start = start
    while segment_start <= end:
        # A cross-year query silently returns only GitHub's ending calendar year.
        segment_end = min(date(segment_start.year, 12, 31), end)
        html = fetch_calendar_html(username, segment_start, segment_end)
        days.extend(parse_calendar(html, segment_start, segment_end))
        if segment_end == end:
            break
        segment_start = segment_end + timedelta(days=1)
    return {"username": username, "from": start.isoformat(), "to": end.isoformat(), "days": days}


def write_contributions(document: ContributionDocument, output: str | Path) -> bool:
    """Atomically replace output after success, leaving identical files untouched."""
    output = Path(output)
    content = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        if output.read_bytes() == content:
            return False
    except FileNotFoundError:
        pass
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=output.parent, prefix=f".{output.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def _cli_date(value: str) -> date:
    try:
        return _iso_date(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date {value!r}: use YYYY-MM-DD") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=DEFAULT_USERNAME, help="Public GitHub username")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Destination JSON file")
    parser.add_argument("--end-date", type=_cli_date, help="Inclusive end date (default: today in UTC)")
    args = parser.parse_args(argv)
    try:
        document = fetch_contributions(args.username, args.end_date)
        changed = write_contributions(document, args.output)
    except (ContributionError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    action = "Wrote" if changed else "Unchanged"
    print(
        f"{action} {args.output}: {WINDOW_DAYS} days "
        f"({document['from']} to {document['to']}) for {args.username}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
