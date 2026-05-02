"""run_demo — single-command entry point for the L-system composition demo.

Steps:
1. Resolve the 8OS repo location (env override or default peer-dir).
2. Bootstrap: idempotently install the PRISM-IR root record into
   8os/ir/lsystem/ (copy from this repo's prism/ dir; reindex if changed).
3. Loop factory.tick on scope=lsystem until the graph stops advancing.
4. Verify the rendered PNG exists and report the result.

Configuration via env (all optional):
    EIGHTOS_REPO       — path to the 8OS repo (default: peer dir 8os/)
    SIMDECISIONS_URL   — turtle-draw EGG URL (default: localhost:5173/?set=turtle-draw)
    LSYSTEM_OUTPUT_DIR — where to write the rendered PNG
    LSYSTEM_HEADLESS   — "true" (default) or "false"
    LSYSTEM_PROGRAM    — name of the PRISM-IR program (without .prism.md
                         suffix). Default `koch-snowflake`. The harness
                         reads `prism/<name>.prism.md`, installs it at
                         `ir/lsystem/<name>.prism.md` in the 8OS repo,
                         and writes the render to `output/<name>.png`.
                         Available programs: `koch-snowflake` (default,
                         pristine geometric fractal), `bushy-tree`
                         (bracketed L-system, branching foliage).

Prerequisite: the simdecisions Vite dev server must be running. From
that repo: `cd browser && npm install && npm run dev`. The dev server
needs to be up before this script's emit-to-canvas step fires.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any


def main() -> int:
    eightos_repo, prism_source, prism_dest = _resolve_paths()

    if not eightos_repo.exists():
        print(f"ERROR: 8OS repo not found at {eightos_repo}", file=sys.stderr)
        print("Set EIGHTOS_REPO to the path of your 8OS checkout.", file=sys.stderr)
        return 1
    if not prism_source.exists():
        print(f"ERROR: PRISM-IR program not at {prism_source}", file=sys.stderr)
        return 1

    original_cwd = Path.cwd()
    os.chdir(eightos_repo)
    try:
        _bootstrap_root_record(prism_source, prism_dest, eightos_repo)
        success = _run_factory_loop(eightos_repo)
    finally:
        os.chdir(original_cwd)

    output_png = _output_path()
    if output_png.exists():
        print(
            f"\n✔ Render: {output_png}  "
            f"({output_png.stat().st_size} bytes)"
        )
        return 0 if success else 2
    else:
        print(f"\n✗ Demo finished but no image produced at {output_png}", file=sys.stderr)
        return 3


def _program_name() -> str:
    return os.environ.get("LSYSTEM_PROGRAM") or "koch-snowflake"


def _resolve_paths() -> tuple[Path, Path, Path]:
    here = Path(__file__).resolve()
    demo_dir = here.parent.parent  # lsystem-demo/
    default_8os = demo_dir.parent / "8os"
    eightos_repo = Path(
        os.environ.get("EIGHTOS_REPO") or default_8os
    ).resolve()
    program = _program_name()
    prism_source = demo_dir / "prism" / f"{program}.prism.md"
    prism_dest = eightos_repo / "ir" / "lsystem" / f"{program}.prism.md"
    return eightos_repo, prism_source, prism_dest


def _output_path() -> Path:
    here = Path(__file__).resolve()
    demo_dir = here.parent.parent
    return Path(
        os.environ.get("LSYSTEM_OUTPUT_DIR") or (demo_dir / "output")
    ).resolve() / f"{_program_name()}.png"


def _bootstrap_root_record(
    prism_source: Path,
    prism_dest: Path,
    eightos_repo: Path,
) -> None:
    prism_dest.parent.mkdir(parents=True, exist_ok=True)
    needs_copy = (
        not prism_dest.exists()
        or prism_source.read_bytes() != prism_dest.read_bytes()
    )
    if needs_copy:
        shutil.copy2(prism_source, prism_dest)
        rel = prism_dest.relative_to(eightos_repo)
        print(f"[bootstrap] Installed root record: {rel}")
        # Refresh kernel indexes so factory.tick can find the new root.
        from eightos.sdk._runner import run as run_op

        try:
            run_op("kernel.reindex", {"mode": "full"})
            print("[bootstrap] kernel.reindex ok")
        except Exception as e:  # noqa: BLE001
            print(f"[bootstrap] kernel.reindex warning: {e}")
    else:
        rel = prism_dest.relative_to(eightos_repo)
        print(f"[bootstrap] Root record already in place: {rel}")


def _run_factory_loop(eightos_repo: Path) -> bool:
    from eightos.factory.tick import tick

    max_ticks = 30
    last_leaves = -1
    stalled_count = 0
    any_failure = False

    for tick_n in range(max_ticks):
        result = _safe_tick(tick, eightos_repo)
        n_leaves = result.get("leaves_found", 0)
        dispatched = result.get("dispatched") or []
        n_ok = sum(1 for d in dispatched if d.get("ok"))
        n_fail = sum(1 for d in dispatched if not d.get("ok"))

        print(
            f"[tick {tick_n}] leaves={n_leaves}, ok={n_ok}, fail={n_fail}"
        )
        for d in dispatched:
            iid = d.get("intention_id") or "?"
            if not d.get("ok"):
                any_failure = True
                print(f"  ✗ {iid}: {d.get('error')}")
            elif d.get("materialized_children"):
                print(
                    f"  ↳ {iid} → {d['materialized_children']} children materialized"
                )
            elif d.get("ok"):
                print(f"  ✓ {iid}")

        if n_leaves == 0:
            print("[tick] graph fully resolved.")
            return not any_failure
        if n_leaves == last_leaves and n_ok == 0:
            stalled_count += 1
            if stalled_count >= 2:
                print("[tick] stalled; aborting.")
                return False
        else:
            stalled_count = 0
        last_leaves = n_leaves

    print("[tick] hit max_ticks without full resolution.")
    return not any_failure


def _safe_tick(tick_fn: Any, eightos_repo: Path) -> dict[str, Any]:
    """Wrap tick to convert hard errors into a synthetic empty result."""
    try:
        return tick_fn(eightos_repo, "lsystem")
    except Exception as e:  # noqa: BLE001
        print(f"[tick] error: {type(e).__name__}: {e}")
        return {"leaves_found": 0, "dispatched": [{"ok": False, "error": str(e), "intention_id": None}]}


if __name__ == "__main__":
    sys.exit(main())
