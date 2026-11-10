# Website brand fonts

Prepared from https://naveengumaste.me on 2026-11-10. These licensed font subsets are embedded by `scripts/render_readme_cards.py`. Detailed evidence, exact source URLs, SHA-256 hashes and project-link findings are in [brand.json](brand.json). Research snapshots and the isolated tooling environment live in the ignored `.preview/brand-research/` directory; they are not required to render cards.

## Actual default website brand

The default interface is **creative / dark**, not minimal mode. The deployed CSS and homepage components establish:

| Role | Value |
| --- | --- |
| Background | #0b0b0b |
| Foreground | oklch(98.5% 0 0), approximately #fafafa |
| Card/popover | oklch(20.5% 0 0), approximately #171717 |
| Primary | oklch(92.2% 0 0), approximately #e5e5e5 |
| Secondary/muted/accent surface | oklch(26.9% 0 0), approximately #262626 |
| Muted text | oklch(70.8% 0 0), approximately #a1a1a1 |
| Border | white at 22% opacity |
| Separator border / stripe | white at 25% / 18% opacity |

Original CSS values are authoritative; hex equivalents above are rounded 8-bit sRGB. The global accent token is neutral, not Catppuccin purple. Project-specific glow accents are KeySkills #ff6b00, UniTools #3b82f6, KairoCal #f59e0b, Caravan #10b981, CryptoZ #8b5cf6 and Orange Finance #ef4444. These are explicit glowColor values in the site project data, not a single global brand accent. Minimal mode has different theme tokens.

Body text and headings use **Hanken Grotesk**: normal body 400, project titles 600, hero name 700. Both font-offbit and font-pixelify alias Hanken Grotesk despite their names. **Space Mono** is an explicit site family for navigation and UI labels, with normal 400/700 faces deployed. The homepage role/location and other font-mono content instead use the platform-dependent ui-monospace/SFMono-Regular/Menlo/Monaco/Consolas/Liberation Mono/Courier New stack. There is no single redistributable exact system face; Space Mono is a verified site family for deterministic card labels, not a claim that the homepage role uses it. Departure Mono 400 is used by the small numeric counter. Allura and Caveat are decorative signature/handwriting fonts, not the body or heading face.

## Prepared assets

| File | Family / CSS weight | Bytes |
| --- | --- | ---: |
| [hanken-grotesk-latin-variable.woff](hanken-grotesk-latin-variable.woff) | Hanken Grotesk, normal, 100 900 variable | 32,584 |
| [space-mono-latin-400.woff](space-mono-latin-400.woff) | Space Mono, normal, 400 | 17,460 |

Total: **50,044 bytes**, about 48.9 KiB, before base64 encoding. Both are real WOFF1 containers, not WOFF2 files with renamed extensions. Hanken version 3.013 matches the deployed family version; the variable source preserves true 400/600/700 and intermediate weights without extra files. Space Mono version 1.003 matches the deployed face.

Both fonts are licensed under **SIL Open Font License 1.1**. Keep [OFL-Hanken-Grotesk.txt](OFL-Hanken-Grotesk.txt) and [OFL-Space-Mono.txt](OFL-Space-Mono.txt) with redistributed assets. Copyright and license name-table entries are retained in the subsets. No reserved font names are declared in these upstream license headers. The originals are not bundled in this directory.

The subset requests printable ASCII plus NBSP, middle dot, multiplication sign, en/em dash, curly single/double quotes, bullet, ellipsis, and right/northeast arrows (108 codepoints total). Space Mono covers all 108. Hanken has no U+2197 northeast arrow upstream, so it covers 107. The deployed Space Mono WOFF2 lacks both arrows; the complete same-version upstream TTF supplies them. For sans text use the fallback family order **Hanken Grotesk, Space Mono, sans-serif**, or draw arrows as SVG paths. Use Space Mono at weight 400; a bold face is not included. This is a deliberately small Latin/punctuation subset, not full Unicode coverage.

The renderer registers Hanken with `font-weight: 100 900` and Space Mono with `font-weight: 400`; both use `font-style: normal` and `format("woff")`. Its `font_css()` function builds each source URI with `"data:font/woff;base64," + base64.b64encode(font_bytes).decode("ascii")`. Every generated SVG embeds both fonts; no external font URL is needed.

## Exact reproduction

Run from the repository root. All installation and download paths remain under the research directory; no global installation is needed. FontTools 4.60.1 performs the subset; Brotli 1.2.0 is needed only for comparing the deployed WOFF2 files, not for generating these WOFF files from TTF. This run used Python 3.15.2 and zlib 1.2.12. Compressed-byte hashes can vary with a different zlib version.

~~~sh
python3 -m venv .preview/brand-research/venv
.preview/brand-research/venv/bin/python -m pip install --no-cache-dir "fonttools==4.60.1"
curl -fL --max-time 45 -A "Mozilla/5.0" "https://raw.githubusercontent.com/marcologous/hanken-grotesk/1ab416e82130b2d3ddb7710abf7ceabf07156a13/fonts/variable/HankenGrotesk%5Bwght%5D.ttf" -o .preview/brand-research/HankenGrotesk-variable.ttf
curl -fL --max-time 45 -A "Mozilla/5.0" "https://raw.githubusercontent.com/googlefonts/spacemono/329858c2c4dbd3476f972a4ae00624b018cf4b81/fonts/ttf/SpaceMono-Regular.ttf" -o .preview/brand-research/SpaceMono-upstream-Regular.ttf
.preview/brand-research/venv/bin/pyftsubset .preview/brand-research/HankenGrotesk-variable.ttf --output-file=fonts/hanken-grotesk-latin-variable.woff --flavor=woff --unicodes=U+0020-007E,U+00A0,U+00B7,U+00D7,U+2013-2014,U+2018-2019,U+201C-201D,U+2022,U+2026,U+2192,U+2197 --layout-features="*" --name-IDs="*" --name-legacy --name-languages="*" --notdef-glyph --notdef-outline --recommended-glyphs --canonical-order --no-recalc-timestamp
.preview/brand-research/venv/bin/pyftsubset .preview/brand-research/SpaceMono-upstream-Regular.ttf --output-file=fonts/space-mono-latin-400.woff --flavor=woff --unicodes=U+0020-007E,U+00A0,U+00B7,U+00D7,U+2013-2014,U+2018-2019,U+201C-201D,U+2022,U+2026,U+2192,U+2197 --layout-features="*" --name-IDs="*" --name-legacy --name-languages="*" --notdef-glyph --notdef-outline --recommended-glyphs --canonical-order --no-recalc-timestamp
curl -fL --max-time 45 -A "Mozilla/5.0" "https://raw.githubusercontent.com/marcologous/hanken-grotesk/1ab416e82130b2d3ddb7710abf7ceabf07156a13/OFL.txt" -o fonts/OFL-Hanken-Grotesk.txt
curl -fL --max-time 45 -A "Mozilla/5.0" "https://raw.githubusercontent.com/googlefonts/spacemono/329858c2c4dbd3476f972a4ae00624b018cf4b81/OFL.txt" -o fonts/OFL-Space-Mono.txt
~~~

Pinned upstream commits:

- Hanken Grotesk: 1ab416e82130b2d3ddb7710abf7ceabf07156a13, fonts/variable/HankenGrotesk[wght].ttf.
- Space Mono: 329858c2c4dbd3476f972a4ae00624b018cf4b81, fonts/ttf/SpaceMono-Regular.ttf.

Input SHA-256:

- Hanken TTF: 813b3f8fa0965405669a89b38e51bbefd95eef6b8e20d1cb2d8c10cce062662f
- Space Mono TTF: 95837e182baeeada83368f7748db28357f0a1b75c6b84ff7065b5edf933c8e18

Output SHA-256:

- Hanken WOFF: e8a3f8ac5dd182748a53e0084cca64be193b65d2bfeb665b9a72a07149188f2c
- Space Mono WOFF: e1ba39509cb3910f59877e8158bc0cd8621a082b0e90966c9ff49daf248d1a40

## Validation

The saved audit is .preview/brand-research/font-validation.json; rerun with:

~~~sh
.preview/brand-research/venv/bin/python .preview/brand-research/validate_fonts.py
~~~

The existing research venv includes Brotli 1.2.0. If recreating it for the audit, install that exact version locally. The audit uses downloaded website WOFF2 references saved beside the source TTFs; their full source URLs are in brand.json.

Checks passed: WOFF signatures and table checksum loading; all 108 requested characters covered across the faces; all existing card text covered; source glyph outlines and advances preserved; license metadata retained; variable weight range 100–900 retained; total WOFF size under 100 KB. Against the deployed faces, Hanken 400 and Space Mono 400 match all 106 overlapping selected codepoints. At Hanken 700, the variable/static dot of lowercase j differs by one font unit at its right edge due to integer rounding; advances match. This known rounding difference is recorded, not described as byte-identical fonts.

## Verified project repository links

- **KeySkills:** https://github.com/NaveenGumaste/keyskills — present as codeRepository and visible GitHub links on the live KeySkills website; the URL returns HTTP 200, and its public repository homepage matches the live site.
- **UniTools, KairoCal, Caravan, CryptoZ, Orange Finance:** no project repository URL exposed by the checked portfolio project-data/detail code or downloaded live project HTML/application chunks. None is present in the public NaveenGumaste repository listing. KairoCal links only to the author profile; Orange Finance links to the legacy author profile, whose public repository list is empty. Do not invent repository URLs or treat third-party framework GitHub links as project repositories. Verified portfolio and live URLs for all six projects are in brand.json.

The portfolio marks KeySkills, KairoCal and UniTools featured; Caravan, CryptoZ and Orange Finance are listed but not marked featured.
