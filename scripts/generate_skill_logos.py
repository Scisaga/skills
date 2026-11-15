"""Draw original Scisaga characters inspired by the playful Keek icon style.

Soft two-tone silhouettes, expressive faces and transparent canvases keep the
set friendly and readable. All geometry is authored here; no external artwork,
fonts, filters or raster images are embedded.

python scripts/generate_skill_logos.py
python scripts/generate_skill_logos.py --check
python scripts/generate_skill_logos.py --output-dir out/icon-preview/candidates
"""

from __future__ import annotations

import argparse
import hashlib
import html
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INK = "#483653"
WHITE = "#FFFFFF"

# Existing UI brand, body, pale fill, darker structural fill, accent.
PALETTES = {
    "termux": ("#3B82F6", "#83BDF0", "#CDE7FB", "#5585C5", "#BEE9AF"),
    "slides": ("#A78BFA", "#B8A0EB", "#E4D9FA", "#8C70BF", "#FFC36C"),
    "dev-ops": ("#34D399", "#80CBB7", "#CCEEE2", "#4E9C8D", "#FFE192"),
    "domain-manager": ("#2563EB", "#87BBF0", "#D4E8FC", "#5D8CCE", "#A5DCCC"),
    "gitlab-issue": ("#FC6D26", "#F6B474", "#FFE5BE", "#D98D58", "#EB886B"),
    "pdf": ("#F43F5E", "#F0A0B3", "#FBE0E8", "#D47492", "#C76385"),
    "speech": ("#C084FC", "#C1A2E9", "#EBDDF9", "#9676BD", "#EDAFCC"),
    "subtitle-matcher": ("#38BDF8", "#87CEDF", "#D6F0F5", "#559BB3", "#B2DBA3"),
    "video": ("#FBBF24", "#F3CD77", "#FFF0BE", "#CCA24F", "#F0AD8C"),
}

TITLES = {
    "termux": ("Termux", "A smiling blue tablet with a mint terminal prompt on its screen."),
    "slides": ("Slides", "A friendly lavender presentation board with chart bars and a golden pointer."),
    "dev-ops": ("Dev Ops", "A mint server tower with a smiling status panel and a deployment arrow."),
    "domain-manager": ("Domain Manager", "A blue globe peeking over a mint domain address bar."),
    "gitlab-issue": ("GitLab Issue", "A peach issue card with a smiling face, a checkbox and an orange label."),
    "pdf": ("PDF", "A rosy folded document with a smiling face and a small red seal."),
    "speech": ("Speech I/O", "A lavender microphone with a friendly face and pink sound waves."),
    "subtitle-matcher": ("Subtitle Matcher", "Two friendly cyan caption bubbles with a green matching check."),
    "video": ("Video Toolkit", "A smiling golden clapperboard with an open striped arm and a play mark."),
}


def face(x: float, y: float, *, gap: float = 20, look: float = 0, smile: bool = True) -> str:
    """Draw the shared character language without text or font dependencies."""
    eyes = []
    for cx in (x - gap / 2, x + gap / 2):
        eyes.append(f'    <circle cx="{cx:g}" cy="{y:g}" r="5.8" fill="{WHITE}"/>')
        eyes.append(f'    <circle cx="{cx + look:g}" cy="{y + 0.5:g}" r="2.55" fill="{INK}"/>')
    mouth = (
        f'    <path d="M{x - 5.5:g} {y + 9:g}h11c-0.8 7.5-10.2 7.5-11 0Z" fill="{INK}"/>'
        if smile else
        f'    <path d="M{x - 4:g} {y + 10:g}q4 4 8 0" stroke="{INK}" stroke-width="2.5"/>'
    )
    return "\n".join(eyes + [mouth])


# Slightly curved edges, offset layers and restrained details create depth
# without heavy outlines, gradients, generic app tiles or decorative clutter.
BODIES = {
    "termux": '''  <path d="M31 19c22-3 51-3 72 0 6 1 9 5 10 11 2 18 2 43 0 61-1 7-4 11-11 12H35c-8 0-12-5-12-12V32c0-7 2-11 8-13Z" fill="{light}"/>
  <path d="M25 27c22-3 49-3 70 0 7 1 11 5 11 12 2 16 2 36 0 52-1 8-5 12-13 13-21 2-44 2-65 0-9-1-13-5-14-13-2-16-2-36 0-51 1-8 4-12 11-13Z" fill="{main}"/>
  <path d="M28 58c20-2 42-2 62 0 4 0 6 3 6 7v23c0 4-2 6-6 7-20 2-42 2-62 0-4-1-6-3-6-7V65c0-4 2-7 6-7Z" fill="#354963"/>
  <path d="m35 68 10 8-10 8m22 0h14" stroke="{accent}" stroke-width="4.5"/>
  <path d="M111 48v15" stroke="{shade}" stroke-width="3.5"/>
  {face}
''',
    "slides": '''  <path d="M61 76v21m-18 12 18-12 18 12" stroke="{shade}" stroke-width="6"/>
  <path d="M24 27h81v51c0 7-4 11-11 11H33c-6 0-9-3-9-9Z" fill="{shade}"/>
  <path d="M26 23c22-2 47-2 69 0 7 1 10 4 10 11v39c0 7-4 10-10 11-22 2-47 2-69 0-7-1-10-4-10-11V34c0-7 3-10 10-11Z" fill="{main}"/>
  <path d="M17 23h88" stroke="{light}" stroke-width="8"/>
  <path d="M29 70V60m11 10V54m11 16V48" stroke="{light}" stroke-width="7"/>
  <path d="m92 92 15-22" stroke="{accent}" stroke-width="6"/>
  <circle cx="108" cy="68" r="4.5" fill="{accent}"/>
  {face}
''',
    "dev-ops": '''  <path d="M40 19h39c8 0 12 5 12 12v70c0 7-4 11-11 11H40Z" fill="{shade}"/>
  <path d="M36 17c11-2 24-2 36 0 6 1 10 5 10 12v70c0 7-4 11-10 12-12 2-25 2-36 0-6-1-10-5-10-12V29c0-7 4-11 10-12Z" fill="{main}"/>
  <path d="M36 64h36M36 82h36" stroke="{shade}" stroke-width="2.5"/>
  <path d="M37 71h14m-14 18h14" stroke="{light}" stroke-width="3"/>
  <circle cx="70" cy="72" r="2.8" fill="{accent}"/>
  <circle cx="70" cy="90" r="2.8" fill="{accent}"/>
  <path d="M40 111v4m30-4v4" stroke="{shade}" stroke-width="5"/>
  <path d="M91 104V82H81c-3 0-4-3-2-5l17-17c2-2 4-2 6 0l16 17c2 2 1 5-2 5h-10v22c0 3-2 5-5 5h-5c-3 0-5-2-5-5Z" fill="{accent}"/>
  {face}
''',
    "domain-manager": '''  <circle cx="62" cy="54" r="39" fill="{main}"/>
  <path d="M25 41c23 5 51 5 74 0M25 67c23-5 51-5 74 0" stroke="{light}" stroke-width="2.4"/>
  <ellipse cx="62" cy="54" rx="19" ry="39" stroke="{light}" stroke-width="2.4"/>
  <path d="M24 84h80c7 0 11 4 11 10v8c0 7-4 10-11 10H24c-7 0-11-3-11-10v-8c0-6 4-10 11-10Z" fill="{shade}"/>
  <path d="M22 79h79c7 0 11 4 11 10v8c0 6-4 10-11 10H22c-7 0-11-4-11-10v-8c0-6 4-10 11-10Z" fill="{accent}"/>
  <circle cx="26" cy="93" r="3.5" fill="#417868"/>
  <path d="M38 93h29m17-5 7 5-7 5" stroke="#417868" stroke-width="3.5"/>
  {face}
''',
    "gitlab-issue": '''  <g transform="rotate(5 68 66)">
    <rect x="37" y="25" width="67" height="84" rx="12" fill="{shade}"/>
  </g>
  <path d="M29 18c17-2 37-2 53 0 7 1 10 5 10 12v68c0 7-3 11-10 12-16 2-36 2-53 0-7-1-10-5-10-12V30c0-7 3-11 10-12Z" fill="{light}"/>
  <path d="M38 15h32c4 0 6 3 6 6v4H32v-4c0-3 2-6 6-6Z" fill="{main}"/>
  <rect x="29" y="76" width="14" height="14" rx="4" fill="{main}"/>
  <path d="m33 82 3 3 5-6M52 79h25m-25 9h16" stroke="{shade}" stroke-width="2.6"/>
  <path d="m87 50 17-6c3-1 6 0 7 3l6 17c1 3-1 6-4 7l-17 6-12-9c-2-1-3-4-2-6Z" fill="{accent}"/>
  <circle cx="91" cy="62" r="3" fill="{light}"/>
  {face}
''',
    "pdf": '''  <path d="M33 24h42l23 23v57c0 7-4 11-11 11H33c-7 0-11-4-11-11V35c0-7 4-11 11-11Z" fill="{shade}"/>
  <path d="M38 14h34l25 26v56c0 7-4 11-11 11H38c-7 0-11-4-11-11V25c0-7 4-11 11-11Z" fill="{light}"/>
  <path d="M72 14v16c0 7 4 10 10 10h15Z" fill="{main}"/>
  <path d="M40 81h36m-36 10h23" stroke="{main}" stroke-width="3"/>
  <path d="m87 106-3 12 9-4 8 4-2-13" fill="{shade}"/>
  <path d="m94 80 5 3 6 1 2 6 3 5-3 6-2 6-6 1-5 3-6-3-6-1-1-6-3-6 3-5 1-6 6-1Z" fill="{accent}"/>
  <path d="m88 95 4 4 8-9" stroke="{light}" stroke-width="3.5"/>
  {face}
''',
    "speech": '''  <path d="M35 60v8a29 29 0 0 0 58 0v-8" stroke="{light}" stroke-width="6"/>
  <path d="M64 97v13m-19 2h38" stroke="{shade}" stroke-width="6"/>
  <path d="M64 15c14 0 23 10 23 24v28c0 14-9 23-23 23S41 81 41 67V39c0-14 9-24 23-24Z" fill="{main}"/>
  <path d="M54 29h20m-23 8h26" stroke="{shade}" stroke-width="2.5"/>
  <path d="M24 44c-5 8-5 18 0 26m80-26c5 8 5 18 0 26" stroke="{accent}" stroke-width="4.5"/>
  {face}
''',
    "subtitle-matcher": '''  <path d="M48 19h53c7 0 11 4 11 11v34c0 7-4 11-11 11h-5v12L81 75H48c-7 0-11-4-11-11V30c0-7 4-11 11-11Z" fill="{shade}"/>
  <path d="M45 17h54c6 0 10 4 10 10v34c0 6-4 10-10 10h-8v12L77 71H45c-6 0-10-4-10-10V27c0-6 4-10 10-10Z" fill="{light}"/>
  <path d="M24 37c19-2 40-2 58 0 7 1 11 5 11 12v38c0 7-4 11-11 12H45l-19 14V99h-2c-7-1-11-5-11-12V49c0-7 4-11 11-12Z" fill="{main}"/>
  <path d="M29 84h19m7 0h19" stroke="{light}" stroke-width="4"/>
  <circle cx="98" cy="94" r="16" fill="{accent}"/>
  <path d="m91 94 5 5 9-11" stroke="#497955" stroke-width="3.5"/>
  {face}
''',
    "video": '''  <path d="M24 49h80c5 0 9 4 9 9v39c0 8-4 12-12 13-24 2-48 2-72 0-8-1-12-5-12-13V58c0-5 3-9 7-9Z" fill="{main}"/>
  <path d="M20 49h88v12H20Z" fill="{shade}"/>
  <path d="M31 49h13L34 61H21Zm27 0h13L61 61H48Zm27 0h13L88 61H75Z" fill="{light}"/>
  <g transform="rotate(-13 20 45)">
    <rect x="17" y="27" width="95" height="18" rx="6" fill="{shade}"/>
    <path d="M32 27h13L34 45H21Zm28 0h13L62 45H49Zm28 0h13L90 45H77Z" fill="{light}"/>
    <circle cx="24" cy="36" r="2.7" fill="{main}"/>
  </g>
  <path d="m91 93 9 5-9 5Z" fill="{light}"/>
  {face}
''',
}

FACES = {
    "termux": face(59, 39, gap=22, look=0.5),
    "slides": face(80, 48, gap=19, look=-0.6),
    "dev-ops": face(54, 37, gap=20, look=0.4),
    "domain-manager": face(62, 51, gap=22),
    "gitlab-issue": face(54, 47, gap=22, look=0.6),
    "pdf": face(60, 56, gap=22),
    "speech": face(64, 54, gap=20),
    "subtitle-matcher": face(53, 59, gap=23, look=0.5, smile=False),
    "video": face(63, 80, gap=25),
}


def icon(name: str) -> str:
    _brand, main, light, shade, accent = PALETTES[name]
    title, desc = TITLES[name]
    body = BODIES[name].format(
        main=main, light=light, shade=shade, accent=accent, face=FACES[name]
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128" fill="none" role="img" aria-labelledby="{name}-title {name}-desc" stroke-linecap="round" stroke-linejoin="round">
  <title id="{name}-title">{html.escape(title)}</title>
  <desc id="{name}-desc">{html.escape(desc)}</desc>
{body}</svg>
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skill", choices=list(PALETTES), action="append", help="Generate only this skill; repeat for multiple skills.")
    parser.add_argument("--output-dir", type=Path, help="Write NAME.svg files here instead of updating skill assets.")
    parser.add_argument("--check", action="store_true", help="Check that the selected SVG assets match the design source.")
    args = parser.parse_args()
    names = list(dict.fromkeys(args.skill or PALETTES))
    digest = hashlib.sha256()
    failures = []
    for name in names:
        data = icon(name).encode("utf-8")
        digest.update(name.encode("utf-8") + b"\0" + data)
        target = args.output_dir / f"{name}.svg" if args.output_dir else ROOT / "skills" / name / "assets" / "logo.svg"
        if args.check:
            if not target.is_file() or target.read_bytes() != data:
                failures.append(name)
                print(f"OUT OF DATE: {target}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            print(f"Wrote {target} ({len(data):,} bytes)")
    print(f"Icons: {len(names)}; design SHA-256: {digest.hexdigest()}")
    if failures:
        print("Regenerate the outdated icons: " + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
