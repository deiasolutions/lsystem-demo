"""lsystem-seed — initialize lsystem state from PRISM-IR root params.

Walks up to the .prism.md root and reads `params.axiom` plus the full
params block. Emits the initial `lstate` payload for downstream
resolvers: `current_string = axiom`, `iteration = 0`,
`params_snapshot = <params>`.

Downstream resolvers read this resolution and propagate `params_snapshot`
forward through the chain so no resolver below seed has to walk back to
the root for parameters.
"""

from __future__ import annotations

import json
from typing import Any

from eightos.factory.workload_helpers import read_parent_prism_params


def resolve(intention_id: str) -> dict[str, Any]:
    """Read root params; emit initial lstate."""
    params = read_parent_prism_params(intention_id)
    if not params:
        raise ValueError(
            f"no PRISM-IR params reachable from {intention_id!r} via parent chain"
        )
    if "axiom" not in params:
        raise ValueError("PRISM-IR params missing required field 'axiom'")
    return {
        "current_string": params["axiom"],
        "iteration": 0,
        "params_snapshot": params,
    }


def adapt(structured: dict[str, Any]) -> dict[str, Any]:
    return {
        "resolution_text": json.dumps(structured),
        "resolution_value": structured,
        "cost_actual": {
            "clock_ms": 1.0,
            "coin_usd": 0.0,
            "carbon_g": 0.0001,
        },
    }


__all__ = ["adapt", "resolve"]
