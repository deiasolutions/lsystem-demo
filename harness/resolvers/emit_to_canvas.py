"""lsystem-emit-to-canvas — Playwright bridge to the simdecisions turtledraw adapter.

Terminal node of the L-system workflow. Reads the upstream
`flat_commands` string, opens a headless Chromium browser at
`http://localhost:5173/?set=turtle-draw` (the simdecisions Vite dev
server must be running), fills the adapter's command-input field with
the commands, waits for the canvas to render, and screenshots the
canvas region as a PNG.

Single-shot fill if the command string fits comfortably in one paste;
chunked sends with brief inter-chunk waits otherwise. The chunking path
taken is logged in the resolution metadata so the writeup can reference
the actual run.

Configuration is via env vars with sane defaults:
    SIMDECISIONS_URL   — adapter URL (default: http://localhost:5173/?set=turtle-draw)
    LSYSTEM_OUTPUT_DIR — where to write the PNG (default: <demo-repo>/output/)
    LSYSTEM_HEADLESS   — "true" (default) or "false"; set to false when debugging.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from eightos.factory.workload_helpers import (
    load_intention_record,
    read_upstream_resolution_value,
)

_DEFAULT_URL = "http://localhost:5173/?set=turtle-draw"
_DEFAULT_OUTPUT_NAME = "fractal-plant.png"

# Threshold above which we chunk the command stream. Chosen empirically: most
# browsers handle a ~50k-char paste into a controlled <input> cleanly; beyond
# that the React state update can lag enough to drop characters. Conservative.
_SINGLE_SHOT_MAX_CHARS = 30000

# When chunking, target this many chars per chunk, breaking only on `;`
# boundaries to keep individual commands intact.
_CHUNK_TARGET_CHARS = 20000

# Inter-chunk wait, milliseconds. Gives the canvas time to draw the chunk's
# commands before the next fill replaces the input.
_INTER_CHUNK_WAIT_MS = 250

# After the final submission, wait this long before screenshotting.
_FINAL_RENDER_WAIT_MS = 2000


def resolve(intention_id: str) -> dict[str, Any]:
    start = time.monotonic()
    rec = load_intention_record(intention_id)
    deps = list(rec.frontmatter.get("depends_on") or [])
    if not deps:
        raise ValueError(
            f"lsystem-emit-to-canvas {intention_id!r} has no depends_on"
        )

    upstream_value = read_upstream_resolution_value(intention_id, deps[0])
    lstate = _coerce_upstream(upstream_value, deps[0])
    flat_commands = lstate["flat_commands"]

    output_dir = Path(os.environ.get("LSYSTEM_OUTPUT_DIR") or _default_output_dir())
    output_dir.mkdir(parents=True, exist_ok=True)
    output_png = output_dir / _DEFAULT_OUTPUT_NAME

    url = os.environ.get("SIMDECISIONS_URL") or _DEFAULT_URL
    headless = (os.environ.get("LSYSTEM_HEADLESS") or "true").lower() != "false"

    chunking, browser_metrics = _render(
        flat_commands=flat_commands,
        url=url,
        headless=headless,
        output_png=output_png,
    )

    elapsed_ms = (time.monotonic() - start) * 1000.0
    return {
        "image_path": str(output_png),
        "image_bytes": output_png.stat().st_size if output_png.exists() else 0,
        "command_count": flat_commands.count(";") + 1,
        "command_chars": len(flat_commands),
        "chunking": chunking,
        "url": url,
        "browser_metrics": browser_metrics,
        "elapsed_ms": elapsed_ms,
    }


def adapt(structured: dict[str, Any]) -> dict[str, Any]:
    summary_text = (
        f"Rendered {structured['command_count']} turtle commands "
        f"({structured['command_chars']} chars, {structured['chunking']}). "
        f"Image: {structured['image_path']} ({structured['image_bytes']} bytes)."
    )
    return {
        "resolution_text": json.dumps({"summary": summary_text, **structured}),
        "resolution_value": structured,
        "cost_actual": {
            "clock_ms": float(structured.get("elapsed_ms") or 0.0),
            "coin_usd": 0.0,
            "carbon_g": 0.5,
        },
    }


def _render(
    *,
    flat_commands: str,
    url: str,
    headless: bool,
    output_png: Path,
) -> tuple[str, dict[str, Any]]:
    """Drive Playwright; return (chunking_label, browser_metrics)."""
    from playwright.sync_api import sync_playwright

    metrics: dict[str, Any] = {}
    chunking_label: str

    with sync_playwright() as p:
        page_load_start = time.monotonic()
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_selector("canvas", timeout=15000)
        page.wait_for_selector("input.tdraw-input", timeout=10000)
        metrics["page_load_ms"] = (time.monotonic() - page_load_start) * 1000.0

        input_loc = page.locator("input.tdraw-input")
        send_start = time.monotonic()

        if len(flat_commands) <= _SINGLE_SHOT_MAX_CHARS:
            input_loc.fill(flat_commands)
            input_loc.press("Enter")
            chunking_label = "single-shot"
            chunk_count = 1
        else:
            chunks = _split_on_semicolons(flat_commands, _CHUNK_TARGET_CHARS)
            for i, chunk in enumerate(chunks):
                input_loc.fill(chunk)
                input_loc.press("Enter")
                if i < len(chunks) - 1:
                    page.wait_for_timeout(_INTER_CHUNK_WAIT_MS)
            chunking_label = f"chunked ({len(chunks)} chunks)"
            chunk_count = len(chunks)

        metrics["send_ms"] = (time.monotonic() - send_start) * 1000.0
        metrics["chunk_count"] = chunk_count

        page.wait_for_timeout(_FINAL_RENDER_WAIT_MS)

        screenshot_start = time.monotonic()
        canvas = page.locator("canvas").first
        canvas.screenshot(path=str(output_png))
        metrics["screenshot_ms"] = (time.monotonic() - screenshot_start) * 1000.0

        browser.close()

    return chunking_label, metrics


def _split_on_semicolons(s: str, target_chars: int) -> list[str]:
    """Split `s` into chunks no larger than `target_chars`, breaking on `;`.

    Never splits a single command across chunks. If a single command exceeds
    target_chars on its own (unlikely), it lands in its own chunk over-target.
    """
    if not s:
        return [""]
    pieces = s.split(";")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for piece in pieces:
        piece_len = len(piece) + 1  # +1 for the `;` separator
        if current and current_len + piece_len > target_chars:
            chunks.append(";".join(current))
            current = [piece]
            current_len = piece_len
        else:
            current.append(piece)
            current_len += piece_len
    if current:
        chunks.append(";".join(current))
    return chunks


def _coerce_upstream(upstream_value: Any, upstream_id: str) -> dict[str, Any]:
    if isinstance(upstream_value, dict):
        d = upstream_value
    elif isinstance(upstream_value, str):
        d = json.loads(upstream_value)
    else:
        raise ValueError(
            f"upstream {upstream_id!r} unexpected shape: {type(upstream_value).__name__}"
        )
    if "flat_commands" not in d:
        raise ValueError(
            f"upstream {upstream_id!r} missing 'flat_commands' field; "
            f"got keys {sorted(d.keys())!r}"
        )
    return d


def _default_output_dir() -> str:
    """Default output directory: <repo-root>/output/."""
    here = Path(__file__).resolve()
    # harness/resolvers/emit_to_canvas.py → repo root is two up.
    return str(here.parent.parent.parent / "output")


__all__ = ["adapt", "resolve"]
