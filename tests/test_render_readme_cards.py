"""Offline renderer tests. Run: python3 -m unittest discover -s tests -v."""

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from copy import deepcopy
from datetime import date, timedelta
from html.parser import HTMLParser
from itertools import pairwise
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

from scripts import render_readme_cards as renderer

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_readme_cards.py"
SVG = "{http://www.w3.org/2000/svg}"
REPOSITORIES = {
    "keyskills": "https://github.com/NaveenGumaste/keyskills",
    "kairodash-devops": "https://github.com/NaveenGumaste/kairodash-DevOps",
    "terraform-docker": "https://github.com/NaveenGumaste/terraform-docker-03",
    "bun-cicd": "https://github.com/NaveenGumaste/cicd-project-01",
}
CARD_STARTS = {
    "hero.svg": 0, "graph.svg": .5, "activity.svg": 1.35,
    "build.svg": 2.2, "learn.svg": 2.35, "connect.svg": 2.5,
    **{f"project-{slug}.svg": 3 + index * .22 for index, slug in enumerate(REPOSITORIES)},
    "stack.svg": 4.1,
}
CARD_NAMES = set(CARD_STARTS)
FONT_FILES = ("hanken-grotesk-latin-variable.woff", "space-mono-latin-400.woff")
GRAPH_COLORS = ("#262626", "#454545", "#737373", "#a3a3a3", "#e5e5e5")
FONT_URI = r"data:font/woff;base64,[A-Za-z0-9+/=]+"
MONTH_DAYS = [
    ("2023-12", 17), ("2024-01", 31), ("2024-02", 29), ("2024-03", 31),
    ("2024-04", 30), ("2024-05", 31), ("2024-06", 30), ("2024-07", 31),
    ("2024-08", 31), ("2024-09", 30), ("2024-10", 31), ("2024-11", 30),
    ("2024-12", 13),
]


def calendar_fixture(counts=None, start=date(2023, 12, 15)):
    counts = [0] * 365 if counts is None else counts
    return {
        "username": "NaveenGumaste",
        "from": start.isoformat(),
        "to": (start + timedelta(days=364)).isoformat(),
        "days": [
            {"date": (start + timedelta(days=index)).isoformat(),
             "count": count, "level": 0 if count == 0 else 1 + index % 4}
            for index, count in enumerate(counts)
        ],
    }


class OfflineTestCase(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection", "socket.socket.connect"):
            guard = patch(target, side_effect=AssertionError("Tests must remain offline"))
            guard.start()
            self.addCleanup(guard.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def write_data(self, data):
        path = self.directory / "contributions.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path


class LoadContributionsTests(OfflineTestCase):
    def assert_invalid(self, data):
        with self.assertRaises((TypeError, ValueError)):
            renderer.load_contributions(self.write_data(data))

    def test_valid_rolling_365_days_including_leap_day(self):
        data = calendar_fixture([index % 13 for index in range(365)])
        self.assertEqual(renderer.load_contributions(self.write_data(data)), data)
        self.assertEqual(len(data["days"]), 365)
        self.assertIn("2024-02-29", [day["date"] for day in data["days"]])
        self.assertEqual(data["days"][0]["date"], data["from"])
        self.assertEqual(data["days"][-1]["date"], data["to"])

    def test_missing_top_level_fields(self):
        for key in ("username", "from", "to", "days"):
            with self.subTest(key=key):
                data = calendar_fixture()
                del data[key]
                self.assert_invalid(data)

    def test_wrong_document_and_field_types(self):
        for value in (None, [], "calendar", 42, True):
            with self.subTest(document=value):
                self.assert_invalid(value)
        for key, values in {
            "username": (None, 123, True, []),
            "from": (None, 20231215, True, []),
            "to": (None, 20241213, False, {}),
            "days": (None, {}, "365", 365, True),
        }.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    data = calendar_fixture()
                    data[key] = value
                    self.assert_invalid(data)

    def test_invalid_usernames(self):
        for username in ("", "-user", "user-", "a" * 40, "user name", "a/b"):
            with self.subTest(username=username):
                data = calendar_fixture()
                data["username"] = username
                self.assert_invalid(data)

    def test_wrong_day_types_and_missing_day_fields(self):
        for value in (None, [], "2023-12-15", 1, True):
            with self.subTest(day=value):
                data = calendar_fixture()
                data["days"][0] = value
                self.assert_invalid(data)
        for key in ("date", "count", "level"):
            with self.subTest(missing=key):
                data = calendar_fixture()
                del data["days"][0][key]
                self.assert_invalid(data)

    def test_counts_and_levels_require_non_boolean_integers_in_range(self):
        for key, values in {
            "count": (-1, 1.5, "1", None, [], True, False),
            "level": (-1, 5, 1.5, "1", None, {}, True, False),
        }.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    data = calendar_fixture()
                    data["days"][0][key] = value
                    self.assert_invalid(data)

    def test_zero_count_and_level_must_agree(self):
        for count, level in ((0, 1), (0, 4), (1, 0), (999, 0)):
            with self.subTest(count=count, level=level):
                data = calendar_fixture()
                data["days"][0].update(count=count, level=level)
                self.assert_invalid(data)

    def test_invalid_dates_and_ranges(self):
        for key in ("from", "to"):
            for value in ("", "yesterday", "2023-02-29", "2024-13-01"):
                with self.subTest(key=key, value=value):
                    data = calendar_fixture()
                    data[key] = value
                    self.assert_invalid(data)
        for end in ("2024-12-12", "2024-12-14", "2023-12-14"):
            with self.subTest(end=end):
                data = calendar_fixture()
                data["to"] = end
                self.assert_invalid(data)

    def test_missing_extra_duplicate_out_of_order_and_out_of_range_days(self):
        valid = calendar_fixture()
        variants = {}
        variants["missing"] = valid["days"][:-1]
        variants["extra"] = valid["days"] + [deepcopy(valid["days"][-1])]
        for label, replacement in (
            ("gap", "2023-12-17"), ("outside", "2023-12-14"),
            ("invalid", "2023-02-29"), ("wrong type", 20231216),
        ):
            days = deepcopy(valid["days"])
            days[1]["date"] = replacement
            variants[label] = days
        days = deepcopy(valid["days"])
        days[1] = deepcopy(days[0])
        variants["duplicate"] = days
        days = deepcopy(valid["days"])
        days[1], days[2] = days[2], days[1]
        variants["order"] = days
        for label, days in variants.items():
            with self.subTest(case=label):
                self.assert_invalid({**valid, "days": days})

    def test_corrupt_json_is_rejected_without_modifying_input(self):
        path = self.directory / "corrupt.json"
        original = b'{"username": "NaveenGumaste", "days": ['
        path.write_bytes(original)
        with self.assertRaises(json.JSONDecodeError):
            renderer.load_contributions(path)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(set(self.directory.iterdir()), {path})


class SummarizeTests(OfflineTestCase):
    def test_zero_activity(self):
        data = calendar_fixture()
        stats = renderer.summarize(data)
        self.assertEqual((stats["total"], stats["active"], stats["longest"]), (0, 0, 0))
        self.assertEqual(stats["busiest"], data["days"][0])
        self.assertEqual(stats["months"], [(month, 0) for month, _ in MONTH_DAYS])

    def test_all_active_and_monthly_groups_cross_year_and_leap_day(self):
        data = calendar_fixture([1] * 365)
        before = deepcopy(data)
        stats = renderer.summarize(data)
        self.assertEqual((stats["total"], stats["active"], stats["longest"]), (365, 365, 365))
        self.assertEqual(stats["months"], MONTH_DAYS)
        self.assertEqual(data, before)

    def test_mixed_counts_tied_busiest_and_streak_through_last_day(self):
        counts = [2, 1, 0, 7, 7, 7] + [0] * 354 + [1, 2, 3, 4, 5]
        data = calendar_fixture(counts)
        stats = renderer.summarize(data)
        self.assertEqual((stats["total"], stats["active"], stats["longest"]), (39, 10, 5))
        self.assertEqual(stats["busiest"], data["days"][3])
        self.assertEqual(stats["months"], [
            (month, 24 if index == 0 else 15 if index == 12 else 0)
            for index, (month, _) in enumerate(MONTH_DAYS)
        ])

    def test_longest_streak_is_not_just_the_final_streak(self):
        counts = [1] * 7 + [0] * 356 + [1, 1]
        stats = renderer.summarize(calendar_fixture(counts))
        self.assertEqual((stats["total"], stats["active"], stats["longest"]), (9, 9, 7))


class RenderCardsTests(OfflineTestCase):
    def test_exactly_eleven_accessible_self_contained_xml_svgs_in_each_mode(self):
        for static in (False, True):
            cards = renderer.render_cards(calendar_fixture(), static=static)
            self.assertEqual(set(cards), CARD_NAMES)
            for name, source in cards.items():
                with self.subTest(static=static, card=name):
                    root = ET.fromstring(source)
                    self.assertEqual(root.tag, SVG + "svg")
                    self.assertEqual(root.get("role"), "img")
                    elements = list(root.iter())
                    parents = {child: parent for parent in elements for child in parent}
                    ids = [element.get("id") for element in elements if element.get("id")]
                    self.assertEqual(len(ids), len(set(ids)))
                    title, description = root.find(SVG + "title"), root.find(SVG + "desc")
                    assert title is not None, "SVG needs an accessible title"
                    assert description is not None, "SVG needs an accessible description"
                    self.assertTrue((title.text or "").strip())
                    self.assertTrue((description.text or "").strip())
                    self.assertTrue(title.get("id"))
                    self.assertTrue(description.get("id"))
                    self.assertEqual(set(root.get("aria-labelledby", "").split()),
                                     {title.get("id"), description.get("id")})
                    self.assertNotRegex(source, r"(?i)<!DOCTYPE|<!ENTITY")
                    for element in elements:
                        tag = element.tag.rsplit("}", 1)[-1].lower()
                        self.assertNotIn(tag, {"script", "foreignobject", "image", "iframe", "set"})
                        if tag.startswith("animate"):
                            self.assertFalse(static, "Static SVGs cannot contain SMIL")
                            self.assertIn(tag, {"animate", "animatetransform"})
                            ancestors = []
                            parent = parents.get(element)
                            while parent is not None:
                                ancestors.extend(parent.get("class", "").split())
                                parent = parents.get(parent)
                            self.assertIn("motion-layer", ancestors)
                        for key, value in element.attrib.items():
                            attribute = key.rsplit("}", 1)[-1].lower()
                            self.assertFalse(attribute.startswith("on"), key)
                            if attribute in ("href", "src"):
                                self.assertTrue(value.startswith("#"), value)
                                self.assertIn(value[1:], ids)
                    self.assertNotRegex(source, r"(?i)@import")
                    for reference in re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", source, re.IGNORECASE):
                        if reference.startswith("data:font/woff;base64,"):
                            self.assertIsNotNone(re.fullmatch(FONT_URI, reference), "Invalid font URI")
                        else:
                            self.assertTrue(reference.startswith("#"), reference[:120])
                            self.assertIn(reference[1:], ids)
                    for element in elements:
                        for attribute in ("aria-labelledby", "aria-describedby"):
                            for reference in element.get(attribute, "").split():
                                self.assertIn(reference, ids)

    def test_animation_reduced_motion_and_static_final_frames(self):
        for static in (False, True):
            for name, source in renderer.render_cards(calendar_fixture(), static=static).items():
                with self.subTest(static=static, card=name):
                    root = ET.fromstring(source)
                    styles = "\n".join(element.text or "" for element in root.iter(SVG + "style"))
                    styles += "\n" + "\n".join(element.get("style", "") for element in root.iter())
                    styles = re.sub(FONT_URI, "embedded-font", styles)
                    declarations = re.findall(r"(?:^|[;{\n])\s*(animation[\w-]*)\s*:\s*([^;}]+)", styles)
                    if static:
                        self.assertNotRegex(styles, r"@(?:-\w+-)?keyframes\b")
                        self.assertTrue(all(key == "animation-delay" or value.strip().startswith("none")
                                            for key, value in declarations), declarations)
                        self.assertNotRegex(styles, r"\bopacity\s*:\s*0(?:\D|$)")
                    else:
                        self.assertIn("animation", [key for key, _ in declarations])
                        self.assertIn("@keyframes", styles)
                        reduced = re.search(
                            r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)\s*\{(.*?)\}\s*\}",
                            styles, re.DOTALL,
                        )
                        assert reduced is not None, "Animated cards need a reduced-motion fallback"
                        rules = re.findall(r"([^{}]+)\{([^{}]+)\}", reduced.group(1) + "}")
                        for css in ("card-enter", "enter", "cell", "bar", "pulse", "orbit"):
                            body = " ".join(body for selectors, body in rules
                                            if re.search(r"\." + css + r"\b", selectors))
                            for property_name, value in (("animation", "none"), ("transform", "none"), ("opacity", "1")):
                                self.assertRegex(body, property_name + r"\s*:\s*" + value + r"\s*!important")
                        for css, display in (("motion-layer", "none"), ("still-layer", "(?:inline|block)")):
                            body = " ".join(body for selectors, body in rules if "." + css in selectors)
                            self.assertRegex(body, r"display\s*:\s*" + display + r"(?:\s*!important)?\s*(?:;|$)")
                        motion = [element for element in root.iter()
                                  if "motion-layer" in element.get("class", "").split()]
                        still = [element for element in root.iter()
                                 if "still-layer" in element.get("class", "").split()]
                        if any(element.tag.rsplit("}", 1)[-1].startswith("animate") for element in root.iter()):
                            self.assertTrue(motion)
                            self.assertTrue(still, "SMIL needs a final-frame reduced-motion counterpart")
                            for layer in still:
                                self.assertTrue(len(layer), "Final-frame layer cannot be empty")
                                self.assertFalse(any(element.tag.rsplit("}", 1)[-1].startswith("animate")
                                                     for element in layer.iter()))

    def test_geometry_fits_viewbox(self):
        for static in (False, True):
            for name, source in renderer.render_cards(calendar_fixture(), static=static).items():
                with self.subTest(static=static, card=name):
                    root = ET.fromstring(source)
                    left, top, width, height = map(float, root.attrib["viewBox"].split())
                    self.assertEqual((float(root.attrib["width"]), float(root.attrib["height"])), (width, height))
                    for element in root.iter():
                        if element.tag == SVG + "rect":
                            x, y, w, h = (float(element.get(key, "0")) for key in ("x", "y", "width", "height"))
                            self.assertGreaterEqual(w, 0)
                            self.assertGreaterEqual(h, 0)
                            bounds = (x, y, x + w, y + h)
                        elif element.tag == SVG + "circle":
                            x, y, radius = (float(element.attrib[key]) for key in ("cx", "cy", "r"))
                            bounds = (x - radius, y - radius, x + radius, y + radius)
                        elif element.tag == SVG + "text":
                            x, y = (float(element.attrib[key]) for key in ("x", "y"))
                            bounds = (x, y, x, y)
                        else:
                            continue
                        self.assertGreaterEqual(bounds[0], left)
                        self.assertGreaterEqual(bounds[1], top)
                        self.assertLessEqual(bounds[2], left + width)
                        self.assertLessEqual(bounds[3], top + height)

    def test_separate_graph_and_monthly_activity_use_only_supplied_data(self):
        for counts, longest in (([0] * 365, 0), ([1] * 365, 365),
                                ([index % 11 for index in range(365)], 10)):
            data = calendar_fixture(counts)
            for static in (False, True):
                with self.subTest(static=static, total=sum(counts)):
                    cards = renderer.render_cards(data, static=static)
                    root = ET.fromstring(cards["graph.svg"])
                    self.assertEqual(root.get("viewBox"), "0 0 960 260")
                    cells = root.findall(f'.//{SVG}rect[@class="cell"]')
                    self.assertEqual(len(cells), 365)
                    groups = [group for group in root.iter(SVG + "g")
                              if group.find(f'{SVG}rect[@class="cell"]') is not None]
                    self.assertEqual(len(groups), 365)
                    start = date.fromisoformat(data["from"])
                    monday = start - timedelta(days=start.weekday())
                    for group, day in zip(groups, data["days"]):
                        cell = group.find(SVG + "rect")
                        assert cell is not None
                        current = date.fromisoformat(day["date"])
                        self.assertEqual(group.findtext(SVG + "title", default=""),
                                         f'{day["date"]}: {day["count"]} contributions')
                        self.assertEqual(float(cell.attrib["x"]), 54 + ((current - monday).days // 7) * 16)
                        self.assertEqual(float(cell.attrib["y"]), 86 + current.weekday() * 16)
                        self.assertEqual((cell.get("width"), cell.get("height")), ("12", "12"))
                        self.assertEqual(cell.get("fill"), GRAPH_COLORS[day["level"]])
                    labels = [element.text for element in root.iter(SVG + "text") if element.get("y") == "67"]
                    with self.subTest(chart="graph month labels"):
                        for month, _ in MONTH_DAYS:
                            self.assertIn(renderer.MONTHS[int(month[5:]) - 1], labels)
                    legend = [element for element in root.iter(SVG + "rect")
                              if float(element.get("y", "0")) > 194 and element.get("fill") in GRAPH_COLORS]
                    self.assertEqual([element.get("fill") for element in legend], list(GRAPH_COLORS))
                    self.assertFalse(root.findall(f'.//{SVG}rect[@class="bar"]'))
                    root = ET.fromstring(cards["activity.svg"])
                    self.assertEqual(root.get("viewBox"), "0 0 960 360")
                    self.assertFalse(root.findall(f'.//{SVG}rect[@class="cell"]'))
                    expected_months = [(month, sum(day["count"] for day in data["days"]
                                                  if day["date"].startswith(month)))
                                       for month, _ in MONTH_DAYS]
                    bars = [group for group in root.iter(SVG + "g")
                            if group.find(f'{SVG}rect[@class="bar"]') is not None]
                    self.assertEqual(len(bars), len(expected_months))
                    highest = max(total for _, total in expected_months)
                    for index, (group, (month, total)) in enumerate(zip(bars, expected_months)):
                        self.assertEqual(group.findtext(SVG + "title", default=""), f"{month}: {total} contributions")
                        bar = group.find(SVG + "rect")
                        assert bar is not None
                        height = float(bar.attrib["height"])
                        step = 868 / len(expected_months)
                        self.assertAlmostEqual(height, 85 * total / highest if highest else 0, places=3)
                        self.assertAlmostEqual(float(bar.attrib["x"]), 44 + index * step, places=3)
                        self.assertAlmostEqual(float(bar.attrib["y"]) + height, 266, places=3)
                        self.assertAlmostEqual(float(bar.attrib["width"]), step - 18, places=3)
                        self.assertEqual(bar.get("rx"), "4")
                    visible_text = [element.text for element in root.iter(SVG + "text")]
                    for value in (f"{sum(counts):,}", str(sum(count > 0 for count in counts)), f"{longest} days"):
                        self.assertIn(value, visible_text)
                    description = root.findtext(SVG + "desc", default="")
                    self.assertIn(f"Longest streak within this 365-day window: {longest} days", description)
                    self.assertIn(f"{sum(counts):,} contributions", description)
                    self.assertIn(f"{sum(count > 0 for count in counts)} active days", description)
                    self.assertIn(f'Window: {data["from"]} to {data["to"]}, including the end date', description)
                    busiest = max(data["days"], key=lambda day: day["count"])
                    peak_label = (f'Busiest day: {renderer.short_date(busiest["date"])} / {busiest["count"]} contributions'
                                  if busiest["count"] else "No contributions in this window")
                    self.assertIn(peak_label, description)
                    self.assertIn(peak_label, [element.text for element in root.iter(SVG + "text")
                                               if element.get("y") == "150"])

    def test_month_headers_do_not_overlap_at_rolling_window_boundaries(self):
        starts = (date(2025, 12, 30), date(2025, 12, 24), date(2025, 12, 15), date(2024, 2, 29))
        for start in starts:
            for static in (False, True):
                with self.subTest(start=start, static=static):
                    root = ET.fromstring(renderer.graph_card(calendar_fixture(start=start), static))
                    labels = [element for element in root.iter(SVG + "text") if element.get("y") == "67"]
                    positions = [float(element.attrib["x"]) for element in labels]
                    self.assertTrue(all(right - left >= 32 for left, right in pairwise(positions)))
                    self.assertEqual(len(root.findall(f'.//{SVG}rect[@class="cell"]')), 365)
                    if start == date(2025, 12, 30):
                        self.assertEqual((labels[0].text, positions[0]), ("Jan", 54))
                    if start == date(2025, 12, 15):
                        self.assertEqual((labels[0].text, positions[0]), ("Dec", 54))

    def test_embedded_font_faces_are_exact_committed_woff_bytes(self):
        expected = [(ROOT / "fonts" / name).read_bytes() for name in FONT_FILES]
        sources = {"font_css": renderer.font_css()}
        for static in (False, True):
            sources.update({f"{static}/{name}": source for name, source
                            in renderer.render_cards(calendar_fixture(), static=static).items()})
        for name, source in sources.items():
            with self.subTest(source=name):
                faces = re.findall(r"@font-face\s*\{([^}]+)\}", source)
                self.assertEqual(len(faces), 2)
                for family, weight, font in zip(
                    ("Hanken Grotesk", "Space Mono"), ("100 900", "400"), expected,
                ):
                    matching = [face for face in faces if re.search(r"font-family\s*:\s*['\"]?" + family, face)]
                    self.assertEqual(len(matching), 1, family)
                    face = matching[0]
                    declarations = re.sub(FONT_URI, "embedded-font", face)
                    self.assertRegex(declarations, r"font-weight\s*:\s*" + weight + r"(?:\s*;|\s*$)")
                    self.assertRegex(declarations, r"format\(\s*['\"]woff['\"]\s*\)")
                    uris = re.findall(FONT_URI, face)
                    self.assertEqual(len(uris), 1)
                    decoded = base64.b64decode(uris[0].split(",", 1)[1], validate=True)
                    self.assertTrue(decoded.startswith(b"wOFF"), "Expected a WOFF1 signature")
                    self.assertTrue(decoded == font, "Embedded font differs from committed asset")

    def test_public_repository_constants_and_neutral_website_theme(self):
        self.assertEqual(tuple(renderer.COLORS), GRAPH_COLORS)
        self.assertEqual([project["slug"] for project in renderer.PROJECTS], list(REPOSITORIES))
        for project in renderer.PROJECTS:
            self.assertTrue({"name", "slug", "repo", "url", "lines", "stack", "color", "icon"} <= project.keys())
            self.assertEqual(project["url"], REPOSITORIES[project["slug"]])
            for key in ("name", "repo", "lines", "stack", "icon"):
                self.assertTrue(project[key], key)
            color = project["color"].lower()
            if project["slug"] == "keyskills":
                self.assertEqual(color, "#ff6b00")
            else:
                self.assertRegex(color, r"^#([0-9a-f]{2})\1\1$")
        source = re.sub(FONT_URI, "embedded-font", "\n".join(renderer.render_cards(calendar_fixture()).values()))
        for color in ("#0b0b0b", "#171717", "#fafafa", "#e5e5e5", "#262626", "#a1a1a1"):
            self.assertIn(color, source)

    def assert_staged_artwork(self, root):
        wrappers = [element for element in root.iter()
                    if "card-enter" in element.get("class", "").split()]
        self.assertEqual(len(wrappers), 1, "Artwork needs exactly one entrance root or wrapper")
        wrapper = wrappers[0]
        if wrapper is root:
            return
        self.assertEqual(wrapper.tag, SVG + "g")
        self.assertIn(wrapper, list(root), "Artwork wrapper must inherit timing directly from the SVG root")
        self.assertTrue(len(wrapper), "An empty entrance wrapper does not stage artwork")
        metadata = {SVG + tag for tag in ("title", "desc", "style", "defs", "metadata")}
        outside = [element for element in root if element is not wrapper and element.tag not in metadata]
        self.assertLessEqual(len(outside), 1, "Only the fixed background frame may sit outside the wrapper")
        if outside:
            frame = outside[0]
            self.assertEqual(frame.tag, SVG + "rect", "Visible content escaped the entrance wrapper")
            self.assertEqual(len(frame), 0, "The fixed frame cannot contain motion or artwork")
            left, top, width, height = map(float, root.attrib["viewBox"].split())
            bounds = tuple(float(frame.get(key, "0")) for key in ("x", "y", "width", "height"))
            self.assertEqual(bounds, (left + 1, top + 1, width - 2, height - 2))
            self.assertEqual(frame.get("fill"), "#171717")

    def test_staged_root_starts_and_helper_offsets(self):
        for static in (False, True):
            for name, source in renderer.render_cards(calendar_fixture(), static=static).items():
                with self.subTest(static=static, card=name):
                    root = ET.fromstring(source)
                    self.assert_staged_artwork(root)
                    start = re.search(r"--start\s*:\s*([\d.]+)s", root.get("style", ""))
                    assert start is not None, "SVG root needs --start in seconds"
                    self.assertAlmostEqual(float(start.group(1)), CARD_STARTS[name])
        content = renderer.text(10, 20, "Staged artwork")
        root = ET.fromstring(renderer.svg(100, 100, "Title", "Description", content, False, start=1.25))
        self.assert_staged_artwork(root)
        start = re.search(r"--start\s*:\s*([\d.]+)s", root.get("style", ""))
        assert start is not None, "svg() must preserve its explicit start value"
        self.assertEqual(float(start.group(1)), 1.25)
        group = ET.fromstring(renderer.group("", delay=.25))
        delay = re.search(r"animation-delay\s*:\s*calc\(var\(--start\)\s*\+\s*([\d.]+)s\)", group.get("style", ""))
        assert delay is not None, "Helper delay must add to the inherited start"
        self.assertEqual(float(delay.group(1)), .25)
        if "card-enter" not in root.get("class", "").split():
            escaped = deepcopy(root)
            escaped.append(ET.fromstring(content))
            with self.assertRaises(AssertionError):
                self.assert_staged_artwork(escaped)

    def test_render_is_deterministic_and_does_not_mutate_data(self):
        data = calendar_fixture([index % 5 for index in range(365)])
        before = deepcopy(data)
        for static in (False, True):
            self.assertEqual(renderer.render_cards(data, static=static), renderer.render_cards(data, static=static))
        self.assertEqual(data, before)

    def test_username_match_is_case_insensitive_but_mismatch_fails_before_rendering(self):
        data = calendar_fixture()
        data["username"] = "naveengumaste"
        self.assertEqual(set(renderer.render_cards(data)), CARD_NAMES)
        data["username"] = "octocat"
        with (
            patch.object(renderer, "hero", side_effect=AssertionError("Must reject before rendering")),
            self.assertRaisesRegex(ValueError, "username"),
        ):
            renderer.render_cards(data)

    def test_text_and_attribute_helpers_escape_xml_and_use_inline_overrides(self):
        value = '<tag> & "quoted" \'single\''
        source = renderer.text(12.5, 25, value, "body", data_note=value,
                               font_size=37, font_weight=750, letter_spacing=-1.5, fill="#123456")
        element = ET.fromstring(source)
        self.assertEqual(element.text, value)
        self.assertEqual(element.get("data-note"), value)
        self.assertEqual(element.get("class"), "body")
        self.assertEqual((element.get("x"), element.get("y")), ("12.5", "25"))
        declarations = dict(part.split(":", 1) for part in element.attrib["style"].split(";"))
        self.assertEqual(declarations, {"font-size": "37px", "font-weight": "750",
                                        "letter-spacing": "-1.5px", "fill": "#123456"})
        for attribute in declarations:
            self.assertNotIn(attribute, element.attrib)
        self.assertIn("&lt;tag&gt; &amp;", source)
        self.assertIn("&quot;quoted&quot;", source)
        attribute = ET.fromstring("<g " + renderer.attrs(data_label=value, aria_label=value) + "/>")
        self.assertEqual(attribute.attrib, {"data-label": value, "aria-label": value})
        root = ET.fromstring(renderer.svg(100, 100, value, value, source, static=True))
        self.assertEqual(root.findtext(SVG + "title", default=""), value)
        self.assertEqual(root.findtext(SVG + "desc", default=""), value)


class CliTests(OfflineTestCase):
    def run_cli(self, output, *arguments, static_env=None):
        environment = os.environ.copy()
        environment.pop("STATIC", None)
        if static_env is not None:
            environment["STATIC"] = static_env
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--data", str(self.directory / "contributions.json"),
             "--output", str(output), *arguments],
            cwd=self.directory, env=environment, capture_output=True, text=True, timeout=20, check=False,
        )

    def snapshot(self, output):
        return {path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ino)
                for path in output.iterdir()}

    def test_cli_animated_static_flag_and_static_environment_are_deterministic_without_rewrites(self):
        data = calendar_fixture([index % 7 for index in range(365)])
        self.write_data(data)
        for mode, arguments, environment, static in (
            ("animated", (), None, False), ("flag", ("--static",), None, True),
            ("environment", (), "1", True),
        ):
            with self.subTest(mode=mode):
                output = self.directory / mode / "cards"
                result = self.run_cli(output, *arguments, static_env=environment)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("11 cards (11 changed)", result.stdout)
                self.assertEqual({path.name for path in output.iterdir()}, CARD_NAMES)
                for name, content in renderer.render_cards(data, static=static).items():
                    path = output / name
                    self.assertEqual(path.read_text(encoding="utf-8"), content)
                    ET.fromstring(path.read_bytes())
                    os.utime(path, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
                before = self.snapshot(output)
                result = self.run_cli(output, *arguments, static_env=environment)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("11 cards (0 changed)", result.stdout)
                self.assertEqual(self.snapshot(output), before)

    def test_invalid_input_and_username_mismatch_never_write_or_replace_cards(self):
        self.write_data(calendar_fixture())
        existing = self.directory / "existing"
        result = self.run_cli(existing)
        self.assertEqual(result.returncode, 0, result.stderr)
        before = self.snapshot(existing)
        wrong_count = calendar_fixture()
        wrong_count["days"][-1]["count"] = -1
        wrong_username = calendar_fixture()
        wrong_username["username"] = "octocat"
        wrong_range = calendar_fixture()
        wrong_range["to"] = "2024-12-12"
        for label, contents in (
            ("corrupt", '{"days": ['), ("count", json.dumps(wrong_count)),
            ("username", json.dumps(wrong_username)), ("range", json.dumps(wrong_range)),
        ):
            for output in (existing, self.directory / label / "new-cards"):
                with self.subTest(case=label, existing=output == existing):
                    (self.directory / "contributions.json").write_text(contents, encoding="utf-8")
                    result = self.run_cli(output)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Cannot render README cards:", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(self.snapshot(existing), before)
                    if output != existing:
                        self.assertFalse(output.parent.exists())


class ReadmeReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []
        self.images = []
        self.image_records = []
        self.link = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a":
            self.link = attributes.get("href")
        target = attributes.get("src" if tag == "img" else "href" if tag == "a" else "")
        if target:
            self.targets.append(target)
            if tag == "img":
                self.images.append(target)
                self.image_records.append({**attributes, "link": self.link})

    def handle_endtag(self, tag):
        if tag == "a":
            self.link = None


class ReadmeTests(OfflineTestCase):
    def test_tile_widths_fullwidth_repository_links_and_staged_readme_order(self):
        references = ReadmeReferences()
        references.feed((ROOT / "README.md").read_text(encoding="utf-8"))
        records = references.image_records
        names = [Path(unquote(urlsplit(record["src"]).path)).name for record in records]
        self.assertEqual(names, list(CARD_STARTS))
        starts = [CARD_STARTS[name] for name in names]
        self.assertEqual(starts, sorted(starts))
        for record, name in zip(records, names):
            with self.subTest(card=name):
                self.assertTrue(record.get("alt", "").strip(), "README images need alt text")
                expected_width = "32.5%" if name in {"build.svg", "learn.svg", "connect.svg"} else "100%"
                self.assertEqual(record.get("width"), expected_width)
                if name.startswith("project-"):
                    self.assertEqual(record["link"], REPOSITORIES[name[len("project-"):-4]])

    def test_local_readme_image_and_link_targets_exist(self):
        source = (ROOT / "README.md").read_text(encoding="utf-8")
        references = ReadmeReferences()
        references.feed(source)
        targets = references.targets + re.findall(r"!?\[[^\]]*\]\(([^\s)]+)\)", source)
        local = []
        for target in targets:
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            with self.subTest(target=target):
                path = (ROOT / unquote(parsed.path)).resolve()
                self.assertTrue(path.is_relative_to(ROOT), target)
                self.assertTrue(path.exists(), f"Missing README target: {target}")
                local.append(path)
        self.assertTrue(local)
        self.assertEqual({unquote(urlsplit(target).path) for target in references.images},
                         {"./cards/" + name for name in CARD_NAMES})


if __name__ == "__main__":
    unittest.main()
