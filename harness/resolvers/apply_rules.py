"""lsystem-apply-rules — one rule-rewrite pass over the L-system string.

Reads the upstream `lstate` (from the predecessor resolver, which is
either `lsystem-seed` for iter 0 or `lsystem-apply-rules-iter-{n-1}`
for iter `n`). For each character of `current_string`, looks it up in
`params_snapshot.rules` and replaces with the rule's RHS if a rule
matches; characters with no rule pass through unchanged. Increments
`iteration` and forwards `params_snapshot` so downstream resolvers can
see the original axiom/rules without walking back to the root.
"""

from __future__ import annotations

import json
import time
from typing import Any

from eightos.factory.workload_helpers import (
    load_intention_record,
    read_upstream_resolution_value,
)


def resolve(intention_id: str) -> dict[str, Any]:
    start = time.monotonic()
    rec = load_intention_record(intention_id)
    deps = list(rec.frontmatter.get("depends_on") or [])
    if not deps:
        raise ValueError(
            f"lsystem-apply-rules intention {intention_id!r} has no depends_on; "
            f"expected one upstream lstate-producing node"
        )

    upstream_value = read_upstream_resolution_value(intention_id, deps[0])
    lstate = _coerce_lstate(upstream_value, intention_id, deps[0])

    rules = lstate["params_snapshot"].get("rules") or {}
    if not isinstance(rules, dict):
        raise ValueError(
            f"params.rules must be a dict (got {type(rules).__name__})"
        )

    new_string = "".join(rules.get(ch, ch) for ch in lstate["current_string"])
    elapsed_ms = (time.monotonic() - start) * 1000.0

    return {
        "current_string": new_string,
        "iteration": int(lstate.get("iteration", 0)) + 1,
        "params_snapshot": lstate["params_snapshot"],
        "elapsed_ms": elapsed_ms,
    }


def adapt(structured: dict[str, Any]) -> dict[str, Any]:
    return {
        "resolution_text": json.dumps(structured),
        "resolution_value": structured,
        "cost_actual": {
            "clock_ms": float(structured.get("elapsed_ms") or 0.0),
            "coin_usd": 0.0,
            "carbon_g": 0.0001,
        },
    }


def _coerce_lstate(
    upstream_value: Any,
    intention_id: str,
    upstream_id: str,
) -> dict[str, Any]:
    """Tolerate either a parsed dict or a JSON-string upstream value."""
    if isinstance(upstream_value, dict):
        lstate = upstream_value
    elif isinstance(upstream_value, str):
        try:
            lstate = json.loads(upstream_value)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"upstream {upstream_id!r} resolution is a string but not valid JSON: {e}"
            ) from e
    else:
        raise ValueError(
            f"upstream {upstream_id!r} resolution_value has unexpected shape "
            f"(got {type(upstream_value).__name__}); expected dict or JSON string"
        )

    for required in ("current_string", "iteration", "params_snapshot"):
        if required not in lstate:
            raise ValueError(
                f"upstream {upstream_id!r} lstate missing required field {required!r}; "
                f"got keys {sorted(lstate.keys())!r}"
            )
    return lstate


__all__ = ["adapt", "resolve"]
