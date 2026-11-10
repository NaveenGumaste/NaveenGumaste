"""Render self-contained profile cards with embedded fonts (Python 3.11+)."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = {
    "name": "Naveen Gumaste",
    "username": "NaveenGumaste",
    "role": "DevOps Engineer & Web Developer",
    "location": "Karnataka, India",
}
# Website creative/dark tokens; see fonts/brand.json for the deployed sources.
BACKGROUND = "#0b0b0b"
SURFACE = "#171717"
FOREGROUND = "#fafafa"
PRIMARY = "#e5e5e5"
MUTED = "#a1a1a1"
BORDER = "#ffffff"
COLORS = ("#262626", "#454545", "#737373", "#a3a3a3", PRIMARY)
STARTS = {"hero": 0.0, "graph": .5, "activity": 1.35, "build": 2.2,
          "learn": 2.35, "connect": 2.5, "projects": 3.0, "stack": 4.1}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
PROJECTS = (
    {
        "slug": "keyskills", "name": "KeySkills", "category": "AI / DEVELOPER TOOLS",
        "repo": "keyskills", "url": "https://github.com/NaveenGumaste/keyskills",
        "lines": ("Portable skills for coding agents.", "SEO, design, git, cleanup, DevOps, and testing."),
        "stack": "Agent Skills / Markdown / Shell", "color": "#ff6b00", "icon": "code",
    },
    {
        "slug": "kairodash-devops", "name": "kairo Operations", "category": "FULL STACK / MARKET INTELLIGENCE",
        "repo": "kairodash-DevOps", "url": "https://github.com/NaveenGumaste/kairodash-DevOps",
        "lines": ("Watchlists, portfolios, alerts, and market operations.", "A dashboard with protected jobs and sync workflows."),
        "stack": "Next.js / TypeScript / Appwrite", "color": PRIMARY, "icon": "chart",
    },
    {
        "slug": "terraform-docker", "name": "Daymark / Terraform", "category": "INFRASTRUCTURE / CONTAINERS",
        "repo": "terraform-docker-03", "url": "https://github.com/NaveenGumaste/terraform-docker-03",
        "lines": ("A small todo app, with infrastructure in code.", "Terraform manages its local Docker container."),
        "stack": "Terraform / Docker / Bun / JavaScript", "color": PRIMARY, "icon": "grid",
    },
    {
        "slug": "bun-cicd", "name": "Bun / CI-CD", "category": "AUTOMATION / DELIVERY",
        "repo": "cicd-project-01", "url": "https://github.com/NaveenGumaste/cicd-project-01",
        "lines": ("A Bun web app with two delivery pipelines.", "Test, build, deploy, and check application health."),
        "stack": "Bun / GitHub Actions / Jenkins / Docker", "color": PRIMARY, "icon": "pipeline",
    },
)


def attrs(**values: object) -> str:
    return " ".join(f'{key.replace("_", "-")}="{escape(str(value), quote=True)}"' for key, value in values.items())


def text(x: float, y: float, value: object, css: str = "body", **extra: object) -> str:
    # Inline overrides outrank class rules; SVG presentation attributes do not.
    overrides = []
    for key in ("font_size", "font_weight", "letter_spacing", "fill"):
        if key in extra:
            value_css = str(extra.pop(key))
            if key in ("font_size", "letter_spacing"):
                value_css += "px"
            overrides.append(f'{key.replace("_", "-")}:{value_css}')
    if overrides:
        extra["style"] = ";".join(overrides)
    return f'<text {attrs(x=f"{x:g}", y=f"{y:g}", **{"class": css}, **extra)}>{escape(str(value))}</text>'


def rect(x: float, y: float, width: float, height: float, **extra: object) -> str:
    return f'<rect {attrs(x=f"{x:g}", y=f"{y:g}", width=f"{width:g}", height=f"{height:g}", **extra)}/>'


def group(content: str, css: str = "enter", delay: float = 0) -> str:
    return f'<g class="{css}" style="animation-delay:calc(var(--start) + {delay:.3f}s)">{content}</g>'


@lru_cache(maxsize=1)
def font_css() -> str:
    faces = (("Hanken Grotesk", "hanken-grotesk-latin-variable.woff", "100 900"),
             ("Space Mono", "space-mono-latin-400.woff", "400"))
    rules = []
    for family, filename, weight in faces:
        raw = (ROOT / "fonts" / filename).read_bytes()
        if not raw.startswith(b"wOFF"):
            raise ValueError(f"Expected a WOFF1 font: {filename}")
        encoded = base64.b64encode(raw).decode("ascii")
        rules.append(f'@font-face{{font-family:"{family}";font-style:normal;font-weight:{weight};'
                     f'src:url(data:font/woff;base64,{encoded}) format("woff");}}')
    return "\n".join(rules)


def smil_pair(animated: str, final: str, static: bool) -> str:
    # CSS cannot pause SMIL. Reduced motion hides its entire layer and displays
    # an independent, non-animated final state instead of sharing SMIL targets.
    if static:
        return final
    return (f'<g class="motion-layer" aria-hidden="true">{animated}</g>'
            f'<g class="still-layer" aria-hidden="true">{final}</g>')


def svg(width: int, height: int, title: str, description: str, content: str,
        static: bool, start: float = 0) -> str:
    animation = "" if static else """
    @keyframes enter { from { opacity:0; transform:translateY(9px) } to { opacity:1; transform:translateY(0) } }
    @keyframes cell { from { opacity:.2 } to { opacity:1 } }
    @keyframes grow { from { transform:scaleY(0) } to { transform:scaleY(1) } }
    @keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:.35 } }
    @keyframes orbit { to { stroke-dashoffset:-120 } }
    .card-enter { animation:enter .65s ease-out var(--start) both }
    .enter { animation:enter .7s ease-out both }
    .cell { animation:cell .55s ease-out both }
    .bar { transform-box:fill-box; transform-origin:center bottom; animation:grow .8s cubic-bezier(.2,.8,.2,1) both }
    .pulse { animation:pulse 3s ease-in-out var(--start) 3 }
    .orbit { animation:orbit 18s linear var(--start) 2 }
    .still-layer { display:none }
    @media (prefers-reduced-motion:reduce) {
      .card-enter,.enter,.cell,.bar,.pulse,.orbit { animation:none !important; transform:none !important; opacity:1 !important }
      .motion-layer { display:none !important }
      .still-layer { display:inline !important }
    }
"""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="--start:{start:.3f}s" role="img" aria-labelledby="title description">
<title id="title">{escape(title)}</title>
<desc id="description">{escape(description)}</desc>
<style>
{font_css()}
    text {{ font-family:"Hanken Grotesk","Space Mono",sans-serif; fill:{FOREGROUND} }}
    .body {{ font-size:22px }}
    .muted {{ fill:{MUTED}; font-size:20px }}
    .label {{ font-family:"Space Mono",monospace; font-size:15px; letter-spacing:1.5px; fill:{MUTED} }}
    .mono {{ font-family:"Space Mono",monospace; font-size:17px; fill:{MUTED} }}
    .small {{ font-size:16px; fill:{MUTED} }}
{animation}
</style>
{rect(1, 1, width - 2, height - 2, rx=18, fill=SURFACE, stroke=BORDER, stroke_opacity=.22, stroke_width=1)}
<g class="card-enter">{content}</g>
</svg>
'''


def hero(static: bool) -> str:
    content = text(40, 44, "NAVEEN / ENGINEER & BUILDER", "label")
    content += '<circle cx="730" cy="39" r="3" fill="#e5e5e5" class="pulse"/>'
    content += text(744, 44, PROFILE["location"].upper(), "label", letter_spacing=.5, font_size=14)
    content += group(
        text(40, 125, PROFILE["name"] + ".", font_size=68, font_weight=700, letter_spacing=-2.5)
        + text(42, 174, "Thoughtful interfaces.", font_size=34, fill=PRIMARY)
        + text(42, 217, "Reliable workflows.", font_size=34, fill=PRIMARY), delay=.08)
    content += group(text(42, 267, PROFILE["role"], "mono", font_size=20)
                     + text(42, 298, "From the browser to the cloud.", "muted"), delay=.2)
    content += '<path d="M40 323H920" stroke="#ffffff" stroke-opacity=".18"/>'
    content += text(42, 354, "WEB / DEVOPS / DEVELOPER TOOLS", "mono", font_size=15)
    content += text(918, 354, "naveengumaste.me", "mono", text_anchor="end", fill=PRIMARY, font_size=15)
    art = '''<circle cx="803" cy="183" r="86" fill="none" stroke="#454545"/>
<circle cx="803" cy="183" r="105" fill="none" stroke="#737373" stroke-dasharray="5 13" class="orbit"/>
<path d="M697 183H720M886 183H909M803 77V101M803 265V288" stroke="#737373" stroke-width="2"/>
<rect x="728" y="119" width="150" height="109" rx="10" fill="#0b0b0b" stroke="#737373"/>
<path d="M728 146H878" stroke="#454545"/>
<circle cx="743" cy="133" r="3" fill="#a1a1a1"/><circle cx="755" cy="133" r="3" fill="#737373"/><circle cx="767" cy="133" r="3" fill="#454545"/>
<path d="M764 166L749 179L764 192M842 166L857 179L842 192M814 160L793 199" fill="none" stroke="#fafafa" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
<rect x="762" y="241" width="82" height="26" rx="6" fill="#262626" stroke="#454545"/>
<circle cx="777" cy="254" r="3" fill="#fafafa" class="pulse"/>'''
    art += text(788, 259, "ship", "mono", fill=PRIMARY, font_size=16)
    final_ring = '<circle cx="803" cy="183" r="86" fill="none" stroke="#e5e5e5" opacity=".2"/>'
    moving_ring = '''<circle cx="803" cy="183" r="86" fill="none" stroke="#e5e5e5" opacity=".2">
<animate attributeName="r" values="86;105;86" begin="0.6s" dur="2.4s" repeatCount="2"/>
<animate attributeName="opacity" values=".2;.55;.2" begin="0.6s" dur="2.4s" repeatCount="2"/>
</circle>'''
    art += smil_pair(moving_ring, final_ring, static)
    content += group(art, delay=.28)
    return svg(960, 380, f'{PROFILE["name"]} — {PROFILE["role"]}',
               "Based in Karnataka, India. Building thoughtful interfaces and reliable workflows, from the browser to the cloud.",
               content, static, STARTS["hero"])


def navigation(name: str, number: str, subtitle: str, color: str, static: bool) -> str:
    start = STARTS[name.lower()]
    content = rect(24, 25, 34, 3, rx=1.5, fill=color)
    content += text(270, 35, number, "mono", text_anchor="end")
    content += group(text(24, 91, name, font_size=38, font_weight=600, fill=color)
                     + text(24, 130, subtitle, font_size=21, fill=MUTED), delay=.08)
    arrow = f'<path d="M251 77H271V97M251 97L271 77" stroke="{color}" stroke-width="2" fill="none"/>'
    moving_arrow = (f'<g><animateTransform attributeName="transform" type="translate" values="0 0;3 -3;0 0" '
                    f'begin="{start + .6:.2f}s" dur="1.4s" repeatCount="2"/>{arrow}</g>')
    content += smil_pair(moving_arrow, arrow, static)
    return svg(300, 160, f"{name} — {subtitle}", "Follow the linked card to " + subtitle.lower() + ".", content, static, start)


def project_icon(kind: str, color: str) -> str:
    paths = {
        "code": '<path d="M386 78L376 88L386 98M410 78L420 88L410 98M403 73L393 103"/>',
        "grid": '<rect x="376" y="73" width="17" height="17" rx="3"/><rect x="402" y="73" width="17" height="17" rx="3"/><rect x="376" y="99" width="17" height="17" rx="3"/><path d="M402 107H419M410 99V116"/>',
        "chart": '<path d="M376 111H420M381 101V91M397 101V81M413 101V69"/>',
        "pipeline": '<circle cx="378" cy="88" r="8"/><circle cx="400" cy="88" r="8"/><circle cx="422" cy="88" r="8"/><path d="M386 88H392M408 88H414M400 96V114M392 109L400 117L408 109"/>',
    }
    return (f'<g transform="translate(480 0)" fill="none" stroke="{color}" stroke-width="2.5" '
            f'stroke-linecap="round" stroke-linejoin="round">{paths[kind]}</g>')


def project_card(project: dict, index: int, static: bool) -> str:
    color = project["color"]
    content = text(34, 38, project["category"], "label", font_size=13, letter_spacing=1)
    content += text(924, 38, project["repo"], "mono", font_size=14, text_anchor="end")
    content += rect(34, 61, 4, 39, rx=2, fill=color)
    content += text(52, 94, project["name"], font_size=43, font_weight=600, fill=color, letter_spacing=-1)
    content += project_icon(project["icon"], color)
    for i, line in enumerate(project["lines"]):
        content += text(34, 141 + i * 32, line, "body", font_size=26)
    content += '<path d="M34 193H924" stroke="#ffffff" stroke-opacity=".18"/>'
    content += text(34, 222, project["stack"], "mono", font_size=17)
    content += text(924, 222, "OPEN REPO ↗", "mono", font_size=15, text_anchor="end", fill=PRIMARY)
    return svg(960, 244, project["name"],
               " ".join(project["lines"]) + " Built with " + project["stack"] + ". Repository: " + project["url"],
               content, static, STARTS["projects"] + index * .22)


def stack_card(static: bool) -> str:
    content = text(34, 42, "THE TOOLBOX", "label")
    rows = (
        ("01", "INTERFACES", "JavaScript · TypeScript · React · Next.js · Tailwind CSS"),
        ("02", "INFRASTRUCTURE", "Linux · Docker · AWS · Terraform · Ansible"),
        ("03", "WORKFLOW", "Git · GitHub Actions · Vite · Bun · pnpm"),
    )
    for index, (number, label, tools) in enumerate(rows):
        y = 91 + index * 78
        line = text(34, y, number, "mono", fill=PRIMARY)
        line += text(78, y, label, "label", fill=PRIMARY, font_size=14)
        line += text(78, y + 31, tools, "body", font_size=24)
        if index < 2:
            line += f'<path d="M78 {y + 47}H924" stroke="#ffffff" stroke-opacity=".18"/>'
        content += group(line, delay=index * .08)
    return svg(960, 294, "Tools I work with", " ".join(f"{row[1]}: {row[2]}." for row in rows), content, static, STARTS["stack"])


def load_contributions(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("username"), str):
        raise TypeError("Contribution data must contain a username and calendar")
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", data["username"]):
        raise ValueError("Invalid contribution username")
    try:
        start, end = date.fromisoformat(data["from"]), date.fromisoformat(data["to"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Contribution range must use ISO dates") from exc
    days = data.get("days")
    if (end - start).days != 364 or not isinstance(days, list) or len(days) != 365:
        raise ValueError("Expected exactly 365 contiguous contribution days")
    for index, day in enumerate(days):
        expected = (start + timedelta(days=index)).isoformat()
        if not isinstance(day, dict) or day.get("date") != expected:
            raise ValueError(f"Missing or out-of-order contribution day: {expected}")
        count, level = day.get("count"), day.get("level")
        if type(count) is not int or count < 0 or type(level) is not int or not 0 <= level <= 4:
            raise ValueError(f"Invalid contribution count or level on {expected}")
        if (count == 0) != (level == 0):
            raise ValueError(f"Contribution count/level mismatch on {expected}")
    return data


def summarize(data: dict) -> dict:
    days = data["days"]
    months: dict[str, int] = defaultdict(int)
    streak = longest = 0
    for day in days:
        months[day["date"][:7]] += day["count"]
        streak = streak + 1 if day["count"] else 0
        longest = max(longest, streak)
    return {
        "total": sum(day["count"] for day in days),
        "active": sum(day["count"] > 0 for day in days),
        "longest": longest,
        "busiest": max(days, key=lambda day: day["count"]),
        "months": list(months.items()),
    }


def short_date(value: str) -> str:
    day = date.fromisoformat(value)
    return f"{day.day:02d} {MONTHS[day.month - 1]} {day.year}"


def graph_card(data: dict, static: bool) -> str:
    content = text(34, 41, "THE CONTRIBUTION TRAIL", "label")
    content += text(924, 41, data["username"], "mono", text_anchor="end", font_size=15)
    start = date.fromisoformat(data["from"])
    monday = start - timedelta(days=start.weekday())
    for row, label in ((0, "M"), (2, "W"), (4, "F")):
        content += text(25, 97 + row * 16, label, "small", font_size=12)
    headers: list[tuple[int, str]] = []
    for index, day in enumerate(data["days"]):
        current = date.fromisoformat(day["date"])
        column = (current - monday).days // 7
        x, y = 54 + column * 16, 86 + current.weekday() * 16
        if index == 0 or current.day == 1:
            # A short leading month can share a week with the next month's label.
            if headers and x - headers[-1][0] < 32:
                headers.pop()
            headers.append((x, MONTHS[current.month - 1]))
        label = f'{day["date"]}: {day["count"]} contributions'
        cell = rect(x, y, 12, 12, rx=3, fill=COLORS[day["level"]],
                    **{"class": "cell", "style": f"animation-delay:calc(var(--start) + {.15 + column * .008:.3f}s)"})
        content += f'<g><title>{escape(label)}</title>{cell}</g>'
    content += "".join(text(x, 67, label, "small", font_size=12) for x, label in headers)
    content += text(35, 235, f'{short_date(data["from"])} — {short_date(data["to"])} · UTC', "small", font_size=14)
    content += text(756, 235, "less", "small", font_size=13, text_anchor="end")
    for level, color in enumerate(COLORS):
        content += rect(767 + level * 18, 224, 12, 12, rx=3, fill=color)
    content += text(865, 235, "more", "small", font_size=13)
    description = (f'{data["username"]}: 365 daily contribution counts from {data["from"]} to {data["to"]}. '
                   'The graphite-to-silver scale matches the website primary colour. Counts reflect the public profile calendar, not only commits.')
    return svg(960, 260, "GitHub contribution graph", description, content, static, STARTS["graph"])


def activity_card(data: dict, static: bool) -> str:
    stats = summarize(data)
    content = text(34, 42, "MONTH BY MONTH", "label")
    content += text(924, 42, "ROLLING 365 DAYS", "label", font_size=12, text_anchor="end", letter_spacing=1)
    metrics = (("CONTRIBUTIONS", f'{stats["total"]:,}'), ("ACTIVE DAYS", stats["active"]),
               ("LONGEST STREAK", f'{stats["longest"]} days'))
    for index, (label, value) in enumerate(metrics):
        x = 35 + index * 306
        content += group(text(x, 90, value, font_size=36, font_weight=600, fill=PRIMARY)
                         + text(x, 114, label, "label", font_size=12, letter_spacing=1), delay=index * .06)
    busiest = stats["busiest"]
    peak_label = (f'Busiest day: {short_date(busiest["date"])} / {busiest["count"]} contributions'
                  if busiest["count"] else "No contributions in this window")
    content += text(35, 150, peak_label, "small", font_size=17)
    months = stats["months"]
    highest = max(total for _, total in months)
    step = 868 / len(months)
    for index, (month, total) in enumerate(months):
        x = 44 + index * step
        height = 0 if highest == 0 else 85 * total / highest
        is_best = highest > 0 and total == highest
        bar = rect(x, 266 - height, step - 18, height, rx=4,
                   fill=PRIMARY if is_best else "#454545",
                   **{"class": "bar", "style": f"animation-delay:calc(var(--start) + {.15 + index * .035:.3f}s)"})
        content += f'<g><title>{month}: {total} contributions</title>{bar}</g>'
        center = x + (step - 18) / 2
        content += text(center, 289, MONTHS[int(month[5:]) - 1], "small", text_anchor="middle", font_size=14)
        if index == 0 or month.endswith("-01") or index == len(months) - 1:
            content += text(center, 305, month[:4], "small", text_anchor="middle", font_size=11)
        if is_best:
            content += text(center, 258 - height, f"{total:,}", "small", text_anchor="middle", fill=PRIMARY, font_size=14)
    content += '<path d="M35 267H924" stroke="#ffffff" stroke-opacity=".18"/>'
    content += text(35, 341, f'{short_date(data["from"])} — {short_date(data["to"])} · UTC', "small", font_size=13)
    content += text(924, 341, "365 days · boundary months are partial", "small", font_size=13, text_anchor="end")
    description = (f'{data["username"]}: {stats["total"]:,} contributions across {stats["active"]} active days. '
                   f'Longest streak within this 365-day window: {stats["longest"]} days. '
                   f'{peak_label}. Window: {data["from"]} to {data["to"]}, including the end date. '
                   'Monthly totals include partial boundary months. Counts reflect the public profile calendar, not only commits.')
    return svg(960, 360, "Monthly GitHub contribution activity", description, content, static, STARTS["activity"])


def render_cards(data: dict, static: bool = False) -> dict[str, str]:
    if data["username"].lower() != PROFILE["username"].lower():
        raise ValueError("Calendar username does not match PROFILE; update the profile or re-fetch its data")
    cards = {
        "hero.svg": hero(static),
        "graph.svg": graph_card(data, static),
        "activity.svg": activity_card(data, static),
        "build.svg": navigation("Build", "01", "Explore my projects", PRIMARY, static),
        "learn.svg": navigation("Learn", "02", "Read the field notes", PRIMARY, static),
        "connect.svg": navigation("Connect", "03", "Start a conversation", PRIMARY, static),
    }
    for index, project in enumerate(PROJECTS):
        cards[f'project-{project["slug"]}.svg'] = project_card(project, index, static)
    cards["stack.svg"] = stack_card(static)
    return cards


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "contributions.json")
    parser.add_argument("--output", type=Path, default=ROOT / "cards")
    parser.add_argument("--static", action="store_true", default=os.environ.get("STATIC") == "1",
                        help="Render final frames without CSS or SMIL animation (also STATIC=1)")
    args = parser.parse_args()
    try:
        cards = render_cards(load_contributions(args.data), static=args.static)
        args.output.mkdir(parents=True, exist_ok=True)
        changed = 0
        for name, content in cards.items():
            path = args.output / name
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                path.write_text(content, encoding="utf-8")
                changed += 1
        print(f"Rendered {len(cards)} cards ({changed} changed) into {args.output}")
    except (OSError, TypeError, ValueError) as exc:
        print(f"Cannot render README cards: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
