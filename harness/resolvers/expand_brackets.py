"""lsystem-expand-brackets — bracket-aware state-machine pass.

Translates the bracketed L-system string into the simdecisions turtledraw
adapter's flat command grammar. The adapter has no `[`/`]` push/pop
primitives; the bracket semantics live here.

Algorithm:
- Maintain (x, y, heading_deg) tracking the turtle pose locally,
  in lockstep with what the adapter will display when the emitted
  commands are executed.
- Maintain a stack of saved poses for `[`/`]` semantics.
- Walk the input string character by character:
    F → emit `forward <step>`; advance pose.
    + → emit `right <angle>`; rotate pose clockwise.
    - → emit `left <angle>`; rotate pose counter-clockwise.
    [ → push current pose to stack (no command emitted).
    ] → pop pose; emit `penup; goto x y; <align heading>; pendown`
        to teleport the adapter's turtle to the popped pose without
        drawing.
    Other characters (X, etc.) are L-system rule-only symbols with
    no turtle semantics; skipped.

Output is a single semicolon-separated string the adapter consumes
in one (or more, when chunked) submission(s).
"""

from __future__ import annotations

import json
import math
import time
from typing import Any

from eightos.factory.workload_helpers import (
    load_intention_record,
    read_upstream_resolution_value,
)

# Initial heading the adapter shows after `clear` — empirical convention.
# 0° = facing right (canvas +x). The setup sequence rotates from this to
# the program's declared start_heading_degrees.
_ADAPTER_DEFAULT_HEADING_DEG = 0.0


def resolve(intention_id: str) -> dict[str, Any]:
    start = time.monotonic()
    rec = load_intention_record(intention_id)
    deps = list(rec.frontmatter.get("depends_on") or [])
    if not deps:
        raise ValueError(
            f"lsystem-expand-brackets intention {intention_id!r} has no depends_on"
        )

    upstream_value = read_upstream_resolution_value(intention_id, deps[0])
    lstate = _coerce_lstate(upstream_value, intention_id, deps[0])

    params = lstate["params_snapshot"]
    flat_commands = _expand(lstate["current_string"], params)

    elapsed_ms = (time.monotonic() - start) * 1000.0
    return {
        "flat_commands": flat_commands,
        "command_count": flat_commands.count(";") + 1,
        "command_chars": len(flat_commands),
        "input_length": len(lstate["current_string"]),
        "iteration": lstate.get("iteration"),
        "params_snapshot": params,
        "elapsed_ms": elapsed_ms,
    }


def adapt(structured: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "command_count": structured["command_count"],
        "command_chars": structured["command_chars"],
        "input_length": structured["input_length"],
        "iteration": structured.get("iteration"),
    }
    return {
        "resolution_text": json.dumps({**summary, "flat_commands": structured["flat_commands"], "params_snapshot": structured["params_snapshot"]}),
        "resolution_value": structured,
        "cost_actual": {
            "clock_ms": float(structured.get("elapsed_ms") or 0.0),
            "coin_usd": 0.0,
            "carbon_g": 0.001,
        },
    }


def _expand(string: str, params: dict[str, Any]) -> str:
    forward_step = float(params.get("forward_step_px", 4))
    angle = float(params.get("angle_degrees", 25))
    start_x = float(params.get("start_x", 320))
    start_y = float(params.get("start_y", 700))
    start_heading = float(params.get("start_heading_degrees", -90))
    pen_color = params.get("pen_color") or {"r": 14, "g": 90, "b": 26}
    pen_width = int(params.get("pen_width", 1))
    bg = params.get("background_color") or {"r": 240, "g": 240, "b": 230}

    cmds: list[str] = []

    # Setup sequence — bring the adapter to the program's declared starting state.
    cmds.append("clear")
    cmds.append(f"background {int(bg['r'])} {int(bg['g'])} {int(bg['b'])}")
    cmds.append(f"color {int(pen_color['r'])} {int(pen_color['g'])} {int(pen_color['b'])}")
    cmds.append(f"width {pen_width}")
    cmds.append("penup")
    cmds.append(f"goto {start_x:g} {start_y:g}")
    _emit_turn(cmds, _ADAPTER_DEFAULT_HEADING_DEG, start_heading)
    cmds.append("pendown")

    # Local pose tracking — mirrors what the adapter will show after each cmd.
    x, y, heading = start_x, start_y, start_heading
    stack: list[tuple[float, float, float]] = []

    for ch in string:
        if ch == 'F':
            cmds.append(f"forward {forward_step:g}")
            rad = math.radians(heading)
            x += forward_step * math.cos(rad)
            y += forward_step * math.sin(rad)
        elif ch == '+':
            cmds.append(f"right {angle:g}")
            heading += angle
        elif ch == '-':
            cmds.append(f"left {angle:g}")
            heading -= angle
        elif ch == '[':
            stack.append((x, y, heading))
        elif ch == ']':
            if not stack:
                # Unmatched ] — skip silently; L-system rules should be balanced
                # but tolerating the edge case avoids run aborts on malformed input.
                continue
            x_old, y_old, heading_old = stack.pop()
            cmds.append("penup")
            cmds.append(f"goto {x_old:.2f} {y_old:.2f}")
            _emit_turn(cmds, heading, heading_old)
            cmds.append("pendown")
            x, y, heading = x_old, y_old, heading_old
        # Other characters (X, ...) are rule-only; no turtle semantics.

    return "; ".join(cmds)


def _emit_turn(cmds: list[str], from_deg: float, to_deg: float) -> None:
    """Append a `right`/`left` command rotating from `from_deg` to `to_deg`.

    Normalizes to (-180, +180] for the shortest turn. Emits nothing when
    the delta rounds to zero.
    """
    delta = ((to_deg - from_deg + 180.0) % 360.0) - 180.0
    if abs(delta) < 1e-6:
        return
    if delta > 0:
        cmds.append(f"right {delta:g}")
    else:
        cmds.append(f"left {-delta:g}")


def _coerce_lstate(
    upstream_value: Any,
    intention_id: str,
    upstream_id: str,
) -> dict[str, Any]:
    if isinstance(upstream_value, dict):
        lstate = upstream_value
    elif isinstance(upstream_value, str):
        lstate = json.loads(upstream_value)
    else:
        raise ValueError(
            f"upstream {upstream_id!r} resolution_value unexpected: "
            f"{type(upstream_value).__name__}"
        )
    for required in ("current_string", "params_snapshot"):
        if required not in lstate:
            raise ValueError(
                f"upstream {upstream_id!r} missing required field {required!r}"
            )
    return lstate


__all__ = ["adapt", "resolve"]
