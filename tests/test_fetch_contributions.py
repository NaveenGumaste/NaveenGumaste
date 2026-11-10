"""Offline fixtures for the public contribution calendar collector.

Run from the repository root: python3 -m unittest discover -s tests -v
"""

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, date, timedelta
from email.message import Message
from http.client import IncompleteRead
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import Mock, call, patch
from urllib.error import HTTPError, URLError

from scripts import fetch_contributions as collector

# GitHub's usual table/tooltip structure, with fixture counts and dates.
# Tooltips deliberately precede cells and use a different order from the table.
TYPICAL_HTML = """
<div class="js-yearly-contributions">
  <tool-tip for="legend-zero">No contributions.</tool-tip>
  <tool-tip id="tooltip-29" for="contribution-day-component-1-4"
    popover="manual" data-type="label" class="sr-only position-absolute">
    No contributions on February 29th.
  </tool-tip>
  <tool-tip for="contribution-day-component-2-6">1,234 contributions on March 2nd.</tool-tip>
  <tool-tip for="contribution-day-component-1-3">
    <strong>12</strong> contributions on February 28th.
  </tool-tip>
  <tool-tip for="contribution-day-component-2-5">1 contribution on March 1st.</tool-tip>
  <table class="ContributionCalendar-grid" role="grid">
    <tbody><tr><td class="ContributionCalendar-label">Wednesday</td>
      <td tabindex="0" data-ix="1" aria-selected="false"
        aria-describedby="contribution-graph-legend-level-2" style="width: 10px"
        data-date="2024-02-28" id="contribution-day-component-1-3"
        data-level="2" data-count="999" role="gridcell" data-view-component="true"
        class="ContributionCalendar-day"></td>
      <td data-date="2024-03-02" data-level="4" id="contribution-day-component-2-6"></td>
      <td data-date="2024-02-29" data-level="0" id="contribution-day-component-1-4"></td>
      <td data-date="2024-03-01" data-level="1" id="contribution-day-component-2-5"></td>
      <td class="ContributionCalendar-day ContributionCalendar-day--empty"></td>
    </tr></tbody>
  </table>
</div>
"""


def cell(day: date, level: int = 0, cell_id: str | None = None) -> str:
    identifier = cell_id if cell_id is not None else f"day-{day}"
    return f'<td data-date="{day}" data-level="{level}" id="{identifier}"></td>'


def tooltip(day: date, text: str = "No contributions", cell_id: str | None = None) -> str:
    identifier = cell_id if cell_id is not None else f"day-{day}"
    return f'<tool-tip for="{identifier}">{text} on {day:%B %d}.</tool-tip>'


def calendar_fixture(start: date, end: date) -> str:
    days = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    return "<table><tr>" + "".join(cell(day) for day in reversed(days)) + "</tr></table>" + "".join(
        tooltip(day) for day in days
    )


class OfflineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        # Any accidental live request, even in a CLI test, is a test failure.
        self.network_guard = patch.object(
            collector, "urlopen", side_effect=AssertionError("Tests must not access the network")
        )
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)


class ParseCalendarTests(OfflineTestCase):
    def test_typical_markup_with_out_of_order_tooltips_and_cells(self) -> None:
        self.assertEqual(
            collector.parse_calendar(TYPICAL_HTML, date(2024, 2, 28), date(2024, 3, 2)),
            [
                {"date": "2024-02-28", "count": 12, "level": 2},
                {"date": "2024-02-29", "count": 0, "level": 0},
                {"date": "2024-03-01", "count": 1, "level": 1},
                {"date": "2024-03-02", "count": 1234, "level": 4},
            ],
        )

    def test_explicit_zero_counts(self) -> None:
        day = date(2024, 2, 29)
        for text in ("No contributions", "0 contributions", "0 contribution"):
            with self.subTest(text=text):
                self.assertEqual(
                    collector.parse_calendar(cell(day) + tooltip(day, text), day, day),
                    [{"date": "2024-02-29", "count": 0, "level": 0}],
                )

    def test_entities_whitespace_and_nested_text(self) -> None:
        day = date(2024, 2, 29)
        html = cell(day, 4) + tooltip(day, "<strong>1,234</strong>&nbsp;\n contributions")
        self.assertEqual(collector.parse_calendar(html, day, day)[0]["count"], 1234)

    def test_empty_or_no_dated_cells_is_not_a_zero_calendar(self) -> None:
        day = date(2024, 2, 29)
        for html in ("", "<html>Sign in</html>", "<td></td>", tooltip(day)):
            with (
                self.subTest(html=html),
                self.assertRaisesRegex(collector.ContributionError, "expected 1 days, found 0"),
            ):
                collector.parse_calendar(html, day, day)

    def test_sparse_range_is_rejected(self) -> None:
        start, end = date(2024, 2, 28), date(2024, 3, 1)
        html = cell(start) + tooltip(start) + cell(end) + tooltip(end)
        with self.assertRaisesRegex(collector.ContributionError, "missing 1 days: 2024-02-29"):
            collector.parse_calendar(html, start, end)

    def test_inverted_range_is_rejected(self) -> None:
        with self.assertRaisesRegex(collector.ContributionError, "Invalid date range"):
            collector.parse_calendar("", date(2024, 3, 1), date(2024, 2, 29))

    def test_missing_tooltip_is_rejected_even_for_zero_level(self) -> None:
        day = date(2024, 2, 29)
        for level in (0, 1, 4):
            with (
                self.subTest(level=level),
                self.assertRaisesRegex(collector.ContributionError, "Missing count tooltip"),
            ):
                collector.parse_calendar(cell(day, level), day, day)

    def test_tooltip_must_reference_the_cell_id(self) -> None:
        day = date(2024, 2, 29)
        html = cell(day, 1) + tooltip(day, "3 contributions", "other-cell")
        with self.assertRaisesRegex(collector.ContributionError, "Missing count tooltip"):
            collector.parse_calendar(html, day, day)

    def test_duplicate_date_is_rejected_even_with_distinct_ids(self) -> None:
        day = date(2024, 2, 29)
        html = cell(day) + tooltip(day) + cell(day, cell_id="other") + tooltip(day, cell_id="other")
        with self.assertRaisesRegex(collector.ContributionError, "Duplicate calendar date"):
            collector.parse_calendar(html, day, day)

    def test_duplicate_cell_id_is_rejected(self) -> None:
        start, end = date(2024, 2, 28), date(2024, 2, 29)
        html = cell(start, cell_id="same") + cell(end, cell_id="same") + tooltip(start, cell_id="same")
        with self.assertRaisesRegex(collector.ContributionError, "Duplicate calendar cell id"):
            collector.parse_calendar(html, start, end)

    def test_duplicate_tooltip_is_rejected(self) -> None:
        day = date(2024, 2, 29)
        with self.assertRaisesRegex(collector.ContributionError, "Duplicate count tooltips"):
            collector.parse_calendar(cell(day) + tooltip(day) * 2, day, day)

    def test_missing_cell_id_is_rejected(self) -> None:
        day = date(2024, 2, 29)
        with self.assertRaisesRegex(collector.ContributionError, "Missing cell id"):
            collector.parse_calendar('<td data-date="2024-02-29" data-level="0"></td>', day, day)

    def test_invalid_levels_are_rejected(self) -> None:
        day = date(2024, 2, 29)
        for level in ("-1", "5", "", "low", "1.0", "01"):
            with self.subTest(level=level):
                html = cell(day).replace('data-level="0"', f'data-level="{level}"') + tooltip(day)
                with self.assertRaisesRegex(collector.ContributionError, "Invalid contribution level"):
                    collector.parse_calendar(html, day, day)
        with self.assertRaisesRegex(collector.ContributionError, "Invalid contribution level"):
            collector.parse_calendar(cell(day).replace('data-level="0"', "") + tooltip(day), day, day)

    def test_invalid_calendar_dates_are_explicit(self) -> None:
        day = date(2024, 2, 29)
        for invalid in ("2024-02-30", "20240229", "", "tomorrow"):
            with self.subTest(invalid=invalid):
                html = cell(day).replace('data-date="2024-02-29"', f'data-date="{invalid}"')
                with self.assertRaisesRegex(collector.ContributionError, "Invalid calendar date"):
                    collector.parse_calendar(html, day, day)

    def test_unrecognized_tooltips_are_not_guessed_from_level(self) -> None:
        day = date(2024, 2, 29)
        for text in ("", "Some contributions", "-1 contribution", "2.5 contributions", "1,23 contributions"):
            with (
                self.subTest(text=text),
                self.assertRaisesRegex(collector.ContributionError, "Unrecognized count tooltip"),
            ):
                collector.parse_calendar(cell(day, 1) + tooltip(day, text), day, day)

    def test_count_and_level_must_agree(self) -> None:
        day = date(2024, 2, 29)
        for level, text in ((0, "1 contribution"), (1, "No contributions"), (4, "0 contributions")):
            with (
                self.subTest(level=level, text=text),
                self.assertRaisesRegex(collector.ContributionError, "Count/level mismatch"),
            ):
                collector.parse_calendar(cell(day, level) + tooltip(day, text), day, day)

    def test_out_of_range_and_future_placeholders_are_ignored(self) -> None:
        day = date(2024, 2, 29)
        html = (
            '<td data-date="2024-02-28" data-level="0"></td>'
            + cell(day) + tooltip(day)
            + '<td data-date="2024-03-01" data-level="0"></td>'
        )
        self.assertEqual(len(collector.parse_calendar(html, day, day)), 1)
        with self.assertRaisesRegex(collector.ContributionError, "Missing cell id"):
            collector.parse_calendar(html, day, date(2024, 3, 1))

    def test_non_td_elements_do_not_supply_days(self) -> None:
        day = date(2024, 2, 29)
        html = cell(day).replace("td", "div") + tooltip(day)
        with self.assertRaisesRegex(collector.ContributionError, "found 0"):
            collector.parse_calendar(html, day, day)

    def test_unclosed_and_nested_tooltips_are_rejected(self) -> None:
        day = date(2024, 2, 29)
        for html, message in (
            (cell(day) + '<tool-tip for="day-2024-02-29">No contributions', "unclosed tool-tip"),
            ("<tool-tip><tool-tip>No contributions</tool-tip></tool-tip>", "nested tool-tip"),
        ):
            with self.subTest(html=html), self.assertRaisesRegex(collector.ContributionError, message):
                collector.parse_calendar(html, day, day)


class FetchTests(OfflineTestCase):
    def test_default_window_uses_utc_inclusively(self) -> None:
        with patch.object(collector, "utc_today", return_value=date(2026, 11, 10)):
            self.assertEqual(collector.date_window(), (date(2025, 11, 11), date(2026, 11, 10)))
        with patch.object(collector, "datetime") as clock:
            clock.now.return_value.date.return_value = date(2026, 11, 10)
            self.assertEqual(collector.utc_today(), date(2026, 11, 10))
            clock.now.assert_called_once_with(UTC)

    def test_leap_year_window_still_has_365_days(self) -> None:
        start, end = collector.date_window(date(2024, 3, 1))
        self.assertEqual(start, date(2023, 3, 3))
        self.assertEqual((end - start).days + 1, 365)

    def test_future_or_unrepresentable_window_is_rejected_before_network(self) -> None:
        with (
            patch.object(collector, "utc_today", return_value=date(2026, 11, 10)),
            self.assertRaisesRegex(collector.ContributionError, "after today"),
        ):
            collector.fetch_contributions(end_date=date(2026, 11, 11))
        with self.assertRaisesRegex(collector.ContributionError, "cannot cover 365 days"):
            collector.date_window(date(1, 1, 1))

    def test_cross_year_requests_and_exact_json_contract(self) -> None:
        with patch.object(collector, "fetch_calendar_html", side_effect=lambda user, start, end: calendar_fixture(start, end)) as fetch:
            document = collector.fetch_contributions(end_date=date(2024, 3, 1))
        self.assertEqual(
            fetch.call_args_list,
            [
                call("NaveenGumaste", date(2023, 3, 3), date(2023, 12, 31)),
                call("NaveenGumaste", date(2024, 1, 1), date(2024, 3, 1)),
            ],
        )
        self.assertEqual(set(document), {"username", "from", "to", "days"})
        self.assertEqual(document["username"], "NaveenGumaste")
        self.assertEqual(document["from"], "2023-03-03")
        self.assertEqual(document["to"], "2024-03-01")
        self.assertEqual(len(document["days"]), 365)
        for offset, day in enumerate(document["days"]):
            self.assertEqual(set(day), {"date", "count", "level"})
            self.assertEqual(day["date"], (date(2023, 3, 3) + timedelta(days=offset)).isoformat())
            self.assertIs(type(day["count"]), int)
            self.assertIs(type(day["level"]), int)

    def test_single_year_needs_one_request_and_honors_username(self) -> None:
        with patch.object(collector, "fetch_calendar_html", side_effect=lambda user, start, end: calendar_fixture(start, end)) as fetch:
            document = collector.fetch_contributions("octocat", date(2023, 12, 31))
        fetch.assert_called_once_with("octocat", date(2023, 1, 1), date(2023, 12, 31))
        self.assertEqual(document["username"], "octocat")

    def test_extra_full_year_cells_are_filtered(self) -> None:
        with patch.object(collector, "fetch_calendar_html", side_effect=lambda user, start, end: calendar_fixture(date(start.year, 1, 1), date(start.year, 12, 31))):
            document = collector.fetch_contributions(end_date=date(2024, 3, 1))
        self.assertEqual(len(document["days"]), 365)
        self.assertEqual(document["days"][-1]["date"], "2024-03-01")

    def test_partial_year_response_is_not_accepted(self) -> None:
        with (
            patch.object(collector, "fetch_calendar_html", return_value=TYPICAL_HTML),
            self.assertRaisesRegex(collector.ContributionError, "Incomplete calendar"),
        ):
            collector.fetch_contributions(end_date=date(2024, 3, 1))

    def test_request_headers_url_timeout_and_decode(self) -> None:
        response = Mock()
        response.headers = Message()
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        response.read.return_value = TYPICAL_HTML.encode("utf-8")
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(collector, "urlopen", return_value=response) as opener:
            self.assertEqual(collector.fetch_calendar_html("octocat", date(2024, 1, 1), date(2024, 3, 1)), TYPICAL_HTML)
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, "https://github.com/users/octocat/contributions?from=2024-01-01&to=2024-03-01")
        self.assertTrue(request.get_header("User-agent"))
        self.assertEqual(request.get_header("Accept-language"), "en-US")
        self.assertEqual(opener.call_args.kwargs, {"timeout": 30})
        self.assertNotIn("Authorization", request.headers)
        response.__exit__.assert_called_once()

    def test_network_errors_include_url_and_precise_reason(self) -> None:
        url = "https://github.com/users/NaveenGumaste/contributions?from=2024-01-01&to=2024-01-01"
        for error, message in (
            (HTTPError(url, 403, "Forbidden", Message(), BytesIO()), "HTTP 403 Forbidden"),
            (HTTPError(url, 401, "Unauthorized", Message(), BytesIO()), "HTTP 401 Unauthorized"),
            (URLError("network access blocked"), "network access blocked"),
            (TimeoutError("timed out"), "timed out"),
        ):
            with self.subTest(error=error):
                with (
                    patch.object(collector, "urlopen", side_effect=error),
                    self.assertRaises(collector.ContributionError) as raised,
                ):
                    collector.fetch_calendar_html("NaveenGumaste", date(2024, 1, 1), date(2024, 1, 1))
                self.assertIn(message, str(raised.exception))
                self.assertIn(url, str(raised.exception))

    def test_invalid_username_is_rejected_without_request(self) -> None:
        for username in ("", "../other", "a/b", "-name", "name-", "a" * 40):
            with (
                self.subTest(username=username),
                self.assertRaisesRegex(collector.ContributionError, "Invalid GitHub username"),
            ):
                collector.fetch_calendar_html(username, date(2024, 1, 1), date(2024, 1, 1))

    def test_truncated_response_is_explicit_and_closed(self) -> None:
        response = Mock()
        response.headers = Message()
        response.read.side_effect = IncompleteRead(b"partial", 100)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with (
            patch.object(collector, "urlopen", return_value=response),
            self.assertRaisesRegex(collector.ContributionError, "Network error.*IncompleteRead"),
        ):
            collector.fetch_calendar_html("NaveenGumaste", date(2024, 1, 1), date(2024, 1, 1))
        response.__exit__.assert_called_once()

    def test_decode_errors_are_explicit(self) -> None:
        response = Mock()
        response.headers = Message()
        response.read.return_value = b"\xff"
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with (
            patch.object(collector, "urlopen", return_value=response),
            self.assertRaisesRegex(collector.ContributionError, "Cannot decode calendar HTML"),
        ):
            collector.fetch_calendar_html("NaveenGumaste", date(2024, 1, 1), date(2024, 1, 1))


class WriteAndCliTests(OfflineTestCase):
    def setUp(self) -> None:
        super().setUp()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.output = self.directory / "contributions.json"
        self.document: collector.ContributionDocument = {
            "username": "NaveenGumaste", "from": "2023-01-01", "to": "2023-12-31",
            "days": [{"date": "2023-01-01", "count": 0, "level": 0}],
        }

    def test_atomic_write_in_destination_directory(self) -> None:
        self.output.write_text("previous data", encoding="utf-8")
        real_replace = collector.os.replace

        def inspect_replace(source: Path, destination: Path) -> None:
            self.assertEqual(source.parent, self.output.parent)
            self.assertEqual(destination, self.output)
            self.assertEqual(self.output.read_text(encoding="utf-8"), "previous data")
            self.assertEqual(json.loads(source.read_text(encoding="utf-8")), self.document)
            real_replace(source, destination)

        with patch.object(collector.os, "replace", side_effect=inspect_replace) as replace:
            self.assertTrue(collector.write_contributions(self.document, self.output))
        replace.assert_called_once()
        self.assertEqual(json.loads(self.output.read_text(encoding="utf-8")), self.document)
        self.assertEqual(list(self.directory.iterdir()), [self.output])

    def test_identical_data_does_not_change_mtime_or_replace_file(self) -> None:
        collector.write_contributions(self.document, self.output)
        before = self.output.stat()
        with patch.object(collector.os, "replace") as replace:
            self.assertFalse(collector.write_contributions(self.document, self.output))
        replace.assert_not_called()
        after = self.output.stat()
        self.assertEqual((before.st_mtime_ns, before.st_ino), (after.st_mtime_ns, after.st_ino))

    def test_replace_or_flush_failure_preserves_old_file_and_cleans_temp(self) -> None:
        self.output.write_bytes(b"previous data")
        for function in ("replace", "fsync"):
            with self.subTest(function=function):
                with (
                    patch.object(collector.os, function, side_effect=OSError("disk error")),
                    self.assertRaisesRegex(OSError, "disk error"),
                ):
                    collector.write_contributions(self.document, self.output)
                self.assertEqual(self.output.read_bytes(), b"previous data")
                self.assertEqual(list(self.directory.iterdir()), [self.output])

    def test_output_parent_is_created_after_successful_collection(self) -> None:
        output = self.directory / "nested" / "calendar.json"
        self.assertTrue(collector.write_contributions(self.document, output))
        self.assertTrue(output.is_file())

    def test_cli_defaults_are_repository_relative(self) -> None:
        expected = Path(__file__).resolve().parents[1] / "data" / "contributions.json"
        self.assertEqual(collector.DEFAULT_OUTPUT, expected)
        with (
            patch.object(collector, "fetch_contributions", return_value=self.document) as fetch,
            patch.object(collector, "write_contributions", return_value=False) as write,
            redirect_stdout(StringIO()) as stdout,
        ):
            self.assertEqual(collector.main([]), 0)
        fetch.assert_called_once_with("NaveenGumaste", None)
        write.assert_called_once_with(self.document, expected)
        self.assertIn("Unchanged", stdout.getvalue())

    def test_cli_overrides(self) -> None:
        with (
            patch.object(collector, "fetch_contributions", return_value=self.document) as fetch,
            redirect_stdout(StringIO()) as stdout,
        ):
            result = collector.main(["--username", "octocat", "--output", str(self.output), "--end-date", "2023-12-31"])
        self.assertEqual(result, 0)
        fetch.assert_called_once_with("octocat", date(2023, 12, 31))
        self.assertIn("Wrote", stdout.getvalue())
        self.assertTrue(self.output.is_file())

    def test_cli_fetch_failure_preserves_existing_data_or_leaves_no_file(self) -> None:
        for existing in (False, True):
            with self.subTest(existing=existing):
                if existing:
                    self.output.write_bytes(b"previous data")
                with (
                    patch.object(
                        collector,
                        "fetch_contributions",
                        side_effect=collector.ContributionError("HTTP 403 Forbidden fetching public calendar"),
                    ),
                    redirect_stderr(StringIO()) as stderr,
                ):
                    result = collector.main(["--output", str(self.output)])
                self.assertEqual(result, 1)
                self.assertIn("HTTP 403 Forbidden", stderr.getvalue())
                self.assertEqual(self.output.exists(), existing)
                if existing:
                    self.assertEqual(self.output.read_bytes(), b"previous data")

    def test_second_year_failure_cannot_replace_existing_output(self) -> None:
        self.output.write_bytes(b"previous data")

        def respond(username: str, start: date, end: date) -> str:
            if start.year == 2024:
                raise collector.ContributionError("HTTP 403 Forbidden fetching second year")
            return calendar_fixture(start, end)

        with (
            patch.object(collector, "fetch_calendar_html", side_effect=respond),
            redirect_stderr(StringIO()) as stderr,
        ):
            result = collector.main(["--output", str(self.output), "--end-date", "2024-03-01"])
        self.assertEqual(result, 1)
        self.assertIn("second year", stderr.getvalue())
        self.assertEqual(self.output.read_bytes(), b"previous data")

    def test_cli_parse_failure_does_not_replace_existing_output(self) -> None:
        self.output.write_bytes(b"previous data")
        with (
            patch.object(collector, "fetch_calendar_html", return_value="<html>No calendar</html>"),
            redirect_stderr(StringIO()) as stderr,
        ):
            result = collector.main(["--output", str(self.output), "--end-date", "2024-03-01"])
        self.assertEqual(result, 1)
        self.assertIn("Incomplete calendar", stderr.getvalue())
        self.assertEqual(self.output.read_bytes(), b"previous data")

    def test_cli_write_failure_is_explicit(self) -> None:
        with (
            patch.object(collector, "fetch_contributions", return_value=self.document),
            patch.object(collector, "write_contributions", side_effect=PermissionError("permission denied")),
            redirect_stderr(StringIO()) as stderr,
        ):
            self.assertEqual(collector.main(["--output", str(self.output)]), 1)
        self.assertIn("permission denied", stderr.getvalue())

    def test_cli_invalid_dates_are_usage_errors(self) -> None:
        for value in ("2024-02-30", "20240301", "2024-W09-5", "not-a-date"):
            with self.subTest(value=value):
                with (
                    redirect_stderr(StringIO()) as stderr,
                    self.assertRaises(SystemExit) as raised,
                ):
                    collector.main(["--end-date", value])
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("use YYYY-MM-DD", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
