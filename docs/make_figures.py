#!/usr/bin/env python3
"""Regenerate docs/img/ for skill-package-spec (hand-built SVG, no deps).

    python3 docs/make_figures.py
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "img")
os.makedirs(IMG, exist_ok=True)

INK, MUTE, LINE, PAPER = "#1f2933", "#6b7580", "#c3cbd3", "#ffffff"
ACCENT, ABG = "#0b7285", "#e3f2f4"
OK, OKB = "#2b8a3e", "#e8f5ec"
WARN = "#b25a00"
FONT = "'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "'Cascadia Code','Consolas',monospace"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def anatomy():
    W, H = 900, 560
    b = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="{FONT}">',
         f'<rect width="{W}" height="{H}" fill="{PAPER}"/>',
         f'<text x="30" y="40" font-size="23" font-weight="700" fill="{INK}">'
         'Anatomy of a skill package</text>',
         f'<text x="30" y="64" font-size="13" fill="{MUTE}">One skill.yaml manifest '
         'carries the six properties a static-playback skill leaves implicit.</text>']
    blocks = [
        ("identity", "name · version (semver) · content id", "standardisation", ACCENT),
        ("provenance", "author · source · captured_on · episodes (hashed) · derived_from", "lineage you can trace", ACCENT),
        ("embodiment + adaptation", "source arm · joint_map · frame_transform · unit_conversion · requires", "portability as a contract", ACCENT),
        ("safety", "force / speed / clearance limits · preconditions · postconditions · verified", "checked before it moves", WARN),
        ("composition", "sequence of sub-skills · pre/postcondition handoff", "composed, not concatenated", ACCENT),
        ("integrity", "sha256 of every payload file", "tamper-evident", OK),
    ]
    y = 92
    for i, (title, body, tag, col) in enumerate(blocks):
        b.append(f'<rect x="30" y="{y}" width="840" height="64" rx="9" '
                 f'fill="{ABG if col==ACCENT else (OKB if col==OK else "#fdf0e2")}" '
                 f'stroke="{col}" stroke-width="1.8"/>')
        b.append(f'<text x="48" y="{y+27}" font-size="16" font-weight="700" fill="{INK}">'
                 f'{esc(title)}</text>')
        b.append(f'<text x="48" y="{y+50}" font-size="12.5" fill="{MUTE}" '
                 f'font-family="{MONO}">{esc(body)}</text>')
        b.append(f'<text x="852" y="{y+27}" font-size="12.5" fill="{col}" '
                 f'text-anchor="end" font-style="italic">{esc(tag)}</text>')
        y += 76
    b.append("</svg>")
    open(os.path.join(IMG, "anatomy.svg"), "w").write("\n".join(b))
    print("wrote anatomy.svg")


def flow():
    W, H = 960, 300
    steps = [
        ("validate", "schema + semver", ACCENT),
        ("verify", "payload hashes", OK),
        ("portability", "every remap declared?", ACCENT),
        ("adapt", "apply the remaps", ACCENT),
        ("compose", "handoff conditions", ACCENT),
    ]
    b = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="{FONT}">',
         f'<rect width="{W}" height="{H}" fill="{PAPER}"/>',
         '<defs><marker id="a" markerWidth="9" markerHeight="9" refX="7" refY="3" '
         f'orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="{MUTE}"/></marker></defs>',
         f'<text x="30" y="42" font-size="22" font-weight="700" fill="{INK}">'
         'Each step is a gate</text>',
         f'<text x="30" y="66" font-size="13" fill="{MUTE}">A skill that fails any '
         'check is refused with a reason; it never runs on best effort.</text>']
    x, y, bw, bh = 30, 110, 160, 84
    for i, (name, sub, col) in enumerate(steps):
        b.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="10" '
                 f'fill="{ABG if col==ACCENT else OKB}" stroke="{col}" stroke-width="2"/>')
        b.append(f'<text x="{x+bw/2}" y="{y+36}" font-size="16" font-weight="700" '
                 f'fill="{INK}" text-anchor="middle" font-family="{MONO}">{esc(name)}</text>')
        b.append(f'<text x="{x+bw/2}" y="{y+60}" font-size="12" fill="{MUTE}" '
                 f'text-anchor="middle">{esc(sub)}</text>')
        if i < len(steps) - 1:
            b.append(f'<line x1="{x+bw}" y1="{y+bh/2}" x2="{x+bw+28}" y2="{y+bh/2}" '
                     f'stroke="{MUTE}" stroke-width="1.8" marker-end="url(#a)"/>')
        x += bw + 28
    b.append(f'<text x="30" y="{y+bh+50}" font-size="12.5" fill="{MUTE}">'
             'refuse points: bad semver · hash mismatch · undeclared remap · '
             'limit above the robot’s · unmet handoff precondition</text>')
    b.append("</svg>")
    open(os.path.join(IMG, "flow.svg"), "w").write("\n".join(b))
    print("wrote flow.svg")


if __name__ == "__main__":
    anatomy()
    flow()
