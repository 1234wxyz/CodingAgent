#!/usr/bin/env python3
"""Generate architecture diagram SVG for README.

Usage:
    python scripts/generate_architecture.py
    -> writes assets/architecture.svg
"""

from html import escape
from pathlib import Path

# ── Layout constants ──────────────────────────────────────────────
W = 820          # canvas width
PAD = 30         # outer padding
RX = 10          # corner radius
ROW_GAP = 8      # gap between rows

# Colors
BG       = "#FFFFFF"
BORDER   = "#D1D5DB"
ACCENT   = "#3B82F6"   # blue  – Agent Runtime
ACCENT2  = "#10B981"   # green – Tools
ACCENT3  = "#F59E0B"   # amber – Middleware
ACCENT4  = "#8B5CF6"   # violet – LLM
ACCENT5  = "#6366F1"   # indigo – Observability
GRAY_BG  = "#F9FAFB"
TEXT      = "#111827"
SUB_TEXT  = "#6B7280"
TOOL_BG  = "#ECFDF5"
MW_BG    = "#FFFBEB"
LLM_BG   = "#F5F3FF"
OBS_BG   = "#EEF2FF"
CLI_BG   = "#F0F9FF"
RUNTIME_BG = "#EFF6FF"

def rect(x, y, w, h, fill=GRAY_BG, stroke=BORDER, rx=RX, opacity=1):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1.5" opacity="{opacity}"/>'

def text(x, y, content, size=14, weight="600", fill=TEXT, anchor="middle"):
    content = escape(content)
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif">{content}</text>'

def sub(x, y, content):
    return text(x, y, content, size=11, weight="400", fill=SUB_TEXT)

def arrow(x1, y1, x2, y2):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{BORDER}" stroke-width="1.5" marker-end="url(#arrowhead)"/>'

def build_svg():
    inner_w = W - 2 * PAD
    parts = []

    # ── Row 1: CLI & Interaction ────────────────────────────────
    y = PAD
    h = 62
    parts.append(rect(PAD, y, inner_w, h, fill=CLI_BG, stroke="#BAE6FD"))
    parts.append(text(W/2, y+26, "CLI & Interaction", size=15, fill=ACCENT))
    parts.append(sub(W/2, y+46, "Interactive Mode · Single-shot Mode · Streaming Output"))

    y += h + ROW_GAP

    # ── Arrow ───────────────────────────────────────────────────
    ay = y + 2
    parts.append(arrow(W/2, ay - 4, W/2, ay + 16))
    y += 24

    # ── Row 2: Agent Runtime ────────────────────────────────────
    h = 62
    parts.append(rect(PAD, y, inner_w, h, fill=RUNTIME_BG, stroke="#93C5FD"))
    parts.append(text(W/2, y+26, "Agent Runtime", size=15, fill=ACCENT))
    parts.append(sub(W/2, y+46, "Thin Loop (~340 lines) · Query → Dispatch → Trajectory · Middleware Hooks"))

    y += h + ROW_GAP

    # ── Arrow ───────────────────────────────────────────────────
    ay = y + 2
    parts.append(arrow(W/2, ay - 4, W/2, ay + 16))
    y += 24

    # ── Row 3: Prompt & Context + Tool System (side by side) ───
    h = 140
    left_w = 230
    right_w = inner_w - left_w - 10

    # Left: Prompt & Context
    parts.append(rect(PAD, y, left_w, h, fill=GRAY_BG, stroke=BORDER))
    parts.append(text(PAD + left_w/2, y+24, "Prompt & Context", size=14, fill=TEXT))
    parts.append(sub(PAD + left_w/2, y+44, "YAML Versioning"))
    parts.append(sub(PAD + left_w/2, y+62, "Platform-aware Rules"))
    parts.append(sub(PAD + left_w/2, y+80, "Token Estimation"))
    parts.append(sub(PAD + left_w/2, y+98, "History Compaction"))
    parts.append(sub(PAD + left_w/2, y+118, "context.py · prompts/*.yaml"))

    # Right: Tool System
    rx = PAD + left_w + 10
    parts.append(rect(rx, y, right_w, h, fill=TOOL_BG, stroke="#A7F3D0"))
    parts.append(text(rx + right_w/2, y+24, "Tool System", size=14, fill="#065F46"))

    # Tool grid (2x3)
    tw = (right_w - 40) / 3
    th = 38
    tools = [
        ("file_edit", "View · Replace · Create"),
        ("bash", "Shell Execution"),
        ("semantic_search", "tree-sitter Symbols"),
        ("task_board", "Persistent Plans"),
        ("delegate", "Sub-agent Roles"),
        ("registry", "Schema Dispatch"),
    ]
    for i, (name, desc) in enumerate(tools):
        col = i % 3
        row = i // 3
        tx = rx + 15 + col * (tw + 5)
        ty = y + 40 + row * (th + 6)
        parts.append(rect(tx, ty, tw, th, fill="#D1FAE5", stroke="#6EE7B7", rx=6))
        parts.append(text(tx + tw/2, ty + 16, name, size=11, weight="600", fill="#065F46"))
        parts.append(text(tx + tw/2, ty + 30, desc, size=9, weight="400", fill="#6B7280"))

    y += h + ROW_GAP

    # ── Arrow ───────────────────────────────────────────────────
    ay = y + 2
    parts.append(arrow(W/2, ay - 4, W/2, ay + 16))
    y += 24

    # ── Row 4: Safety & Middleware ──────────────────────────────
    h = 62
    parts.append(rect(PAD, y, inner_w, h, fill=MW_BG, stroke="#FDE68A"))
    parts.append(text(W/2, y+26, "Safety & Middleware", size=15, fill="#92400E"))
    parts.append(sub(W/2, y+46, "Bash Guard (12 rules) · Sandbox Detection · Context Compaction · Workspace Boundary"))

    y += h + ROW_GAP

    # ── Arrow ───────────────────────────────────────────────────
    ay = y + 2
    parts.append(arrow(W/2, ay - 4, W/2, ay + 16))
    y += 24

    # ── Row 5: LLM Adapter ─────────────────────────────────────
    h = 62
    parts.append(rect(PAD, y, inner_w, h, fill=LLM_BG, stroke="#C4B5FD"))
    parts.append(text(W/2, y+26, "LLM Adapter (litellm)", size=15, fill="#5B21B6"))
    parts.append(sub(W/2, y+46, "Retry & Backoff · Model Fallback Chain · Streaming · Cost Tracking"))

    y += h + ROW_GAP

    # ── Arrow ───────────────────────────────────────────────────
    ay = y + 2
    parts.append(arrow(W/2, ay - 4, W/2, ay + 16))
    y += 24

    # ── Row 6: Observability & Evaluation ──────────────────────
    h = 62
    parts.append(rect(PAD, y, inner_w, h, fill=OBS_BG, stroke="#C7D2FE"))
    parts.append(text(W/2, y+26, "Observability & Evaluation", size=15, fill="#3730A3"))
    parts.append(sub(W/2, y+46, "Trajectory JSONL · Terminal Dashboard · Benchmark Harness · Prompt A/B"))

    y += h + PAD

    # ── Assemble SVG ────────────────────────────────────────────
    H = y
    header = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">\n'
        f'<defs>\n'
        f'  <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">\n'
        f'    <polygon points="0 0, 8 3, 0 6" fill="{BORDER}"/>\n'
        f'  </marker>\n'
        f'</defs>\n'
        f'<rect width="{W}" height="{H}" fill="{BG}" rx="0"/>\n'
    )
    footer = '</svg>\n'
    return header + '\n'.join(parts) + '\n' + footer


def main():
    out_dir = Path(__file__).resolve().parent.parent / "assets"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "architecture.svg"
    out_path.write_text(build_svg(), encoding="utf-8")
    print(f"Generated: {out_path}")


if __name__ == "__main__":
    main()
