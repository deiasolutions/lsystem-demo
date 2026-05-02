"""lsystem-prism-decomposer — deterministic PRISM-IR → (I, R) graph translator.

Reads the workload root's body (a PRISM-IR v1.1 Level-1 program in a
fenced YAML block), parses nodes/edges, unrolls back-edges using the
program's declared `params.target_iterations`, and emits a graph spec
the factory's materializer authors as kernel-hosted (I, R) records.

Architectural slot: same as Block 3's `eightos.factory.decomposer`
(LLM-bridged SCAN decomposer) — both produce graph specs the
materializer consumes. This decomposer is in-process and deterministic.
The slot is general; the fill is workload-specific. Two demos
exercising the same slot with different fills (LLM, deterministic)
cash out the architectural claim that the slot isn't LLM-shaped.

Idempotency: on dispatch, computes the expected child id list from the
program; if every expected id already exists in the kernel's
`id-to-path` index, returns an empty graph spec. The materializer then
authors zero records. Combined with the factory walker's filter
(parents with `expanded_into != null` are skipped post-materialization),
the demo is safely re-runnable without producing duplicate records.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import yaml

from eightos._yaml import load_yaml_file
from eightos.factory.workload_helpers import load_intention_record
from eightos.sdk._common import repo_root_or_raise

_YAML_FENCE_RE = re.compile(r"```yaml\s*\n(.*?)\n\s*```", flags=re.DOTALL)


def resolve(intention_id: str) -> dict[str, Any]:
    """Read self, parse PRISM-IR body, emit graph spec."""
    start = time.monotonic()
    rec = load_intention_record(intention_id)
    program = _extract_program_yaml(rec.intention_text)
    graph_spec = _decompose(program)

    repo = repo_root_or_raise()
    idx = load_yaml_file(repo / ".8os" / "index" / "id-to-path.yml") or {}
    expected_ids = [n["node_id"] for n in graph_spec["nodes"]]
    skipped = bool(expected_ids) and all(eid in idx for eid in expected_ids)

    elapsed_ms = (time.monotonic() - start) * 1000.0
    return {
        "nodes": [] if skipped else graph_spec["nodes"],
        "skipped_idempotent": skipped,
        "expected_count": len(expected_ids),
        "elapsed_ms": elapsed_ms,
    }


def adapt(structured: dict[str, Any]) -> dict[str, Any]:
    """Surface the graph spec on `resolution_value` for the materializer."""
    nodes = structured.get("nodes", [])
    summary = {
        "nodes_authored": [n["node_id"] for n in nodes],
        "skipped_idempotent": structured.get("skipped_idempotent", False),
        "expected_count": structured.get("expected_count", 0),
    }
    return {
        "resolution_text": json.dumps(summary),
        "resolution_value": {"nodes": nodes},
        "cost_actual": {
            "clock_ms": float(structured.get("elapsed_ms") or 0.0),
            "coin_usd": 0.0,
            "carbon_g": 0.0001,
        },
    }


def _extract_program_yaml(body: str) -> dict[str, Any]:
    """Pull the fenced YAML block from the PRISM-IR body and parse."""
    match = _YAML_FENCE_RE.search(body)
    if not match:
        raise ValueError("no PRISM-IR YAML fence in record body")
    program = yaml.safe_load(match.group(1))
    if not isinstance(program, dict):
        raise ValueError(
            f"PRISM-IR body did not parse as dict (got {type(program).__name__})"
        )
    return program


def _decompose(program: dict[str, Any]) -> dict[str, Any]:
    """Walk PRISM-IR nodes/edges; unroll back-edges using params.

    Returns the graph spec the materializer expects:
        {nodes: [{node_id, intention_text, depends_on, prism_operator}, ...]}

    Algorithm:
    1. Classify edges into forward/back using source-order topology.
    2. Identify the loop: back-edge `s → t` makes `t` the loop entry,
       `s` the loop decision.
    3. Trace the loop body chain from entry → ... → decision (work
       nodes only).
    4. Classify remaining work nodes into pre-loop (forward-reachable
       to entry) vs post-loop.
    5. Emit pre-loop nodes 1:1; emit `target_iterations` copies of the
       loop body chained sequentially; emit post-loop nodes 1:1 with
       the first post-loop node depending on the final unrolled body
       node.

    Programs without back-edges fall through to a straight-line emit.
    """
    nodes_in_order = list(program.get("nodes") or [])
    nodes_by_id = {n["id"]: n for n in nodes_in_order}
    edges = list(program.get("edges") or [])
    params = program.get("params") or {}
    target_iterations = int(params.get("target_iterations", 1))

    back_edges, forward_edges = _classify_edges(edges, nodes_in_order)
    if len(back_edges) > 1:
        raise ValueError(
            f"multi-loop PRISM-IR programs not yet supported "
            f"(found {len(back_edges)} back-edges)"
        )

    spec_nodes: list[dict[str, Any]] = []

    if not back_edges:
        for node in nodes_in_order:
            if node["t"] in {"start", "end", "decision"}:
                continue
            deps = _deps_for(node["id"], forward_edges, nodes_by_id)
            spec_nodes.append(_make_spec_node(node, deps))
        return {"nodes": spec_nodes}

    back_edge = back_edges[0]
    loop_entry_id = back_edge["t"]
    loop_decision_id = back_edge["s"]
    body_chain_ids = _trace_loop_body(
        loop_entry_id, loop_decision_id, forward_edges, nodes_by_id
    )

    seen_in_loop = set(body_chain_ids) | {loop_decision_id, loop_entry_id}
    pre_loop_nodes: list[dict[str, Any]] = []
    post_loop_nodes: list[dict[str, Any]] = []
    for node in nodes_in_order:
        if node["id"] in seen_in_loop:
            continue
        if node["t"] in {"start", "end", "decision"}:
            continue
        if _reaches(node["id"], loop_entry_id, forward_edges):
            pre_loop_nodes.append(node)
        else:
            post_loop_nodes.append(node)

    for node in pre_loop_nodes:
        deps = _deps_for(node["id"], forward_edges, nodes_by_id)
        spec_nodes.append(_make_spec_node(node, deps))

    last_id_so_far: str | None = (
        pre_loop_nodes[-1]["id"] if pre_loop_nodes else None
    )
    for i in range(target_iterations):
        prev_in_chain = last_id_so_far
        for body_node_id in body_chain_ids:
            body_node = nodes_by_id[body_node_id]
            unrolled_id = f"{body_node_id}-iter-{i}"
            deps = [prev_in_chain] if prev_in_chain is not None else []
            spec_nodes.append(
                {
                    "node_id": unrolled_id,
                    "intention_text": _intention_text_for(body_node, iteration=i),
                    "depends_on": deps,
                    "prism_operator": _prism_op(body_node),
                }
            )
            prev_in_chain = unrolled_id
            last_id_so_far = unrolled_id

    for j, node in enumerate(post_loop_nodes):
        if j == 0 and last_id_so_far is not None:
            deps = [last_id_so_far]
        else:
            deps = _deps_for(node["id"], forward_edges, nodes_by_id)
        spec_nodes.append(_make_spec_node(node, deps))

    # Namespace every node_id with the program's id so multiple programs
    # can coexist in the same 8OS scope without colliding (snowflake's
    # `seed`, `apply_rules-iter-0`, ... vs bushy-tree's same names). The
    # `prism_operator.resolver` field is unchanged — resolvers are global
    # and dispatched per-record by name; only the (I, R) ids are namespaced.
    program_id = program.get("id") or program.get("prism")
    if program_id:
        prefix = f"{program_id}-"
        for spec in spec_nodes:
            spec["node_id"] = prefix + spec["node_id"]
            spec["depends_on"] = [
                prefix + d for d in (spec.get("depends_on") or [])
            ]

    return {"nodes": spec_nodes}


def _classify_edges(
    edges: list[dict[str, Any]],
    nodes_in_order: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split edges into (back, forward) by source-order index of endpoints."""
    order = {n["id"]: i for i, n in enumerate(nodes_in_order)}
    back: list[dict[str, Any]] = []
    fwd: list[dict[str, Any]] = []
    for edge in edges:
        s, t = edge.get("s"), edge.get("t")
        if order.get(t, -1) < order.get(s, -1):
            back.append(edge)
        else:
            fwd.append(edge)
    return back, fwd


def _trace_loop_body(
    entry_id: str,
    decision_id: str,
    forward_edges: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    """Trace entry → ... → decision via forward edges; return work-node ids."""
    chain: list[str] = []
    cur = entry_id
    visited: set[str] = set()
    while cur not in visited:
        visited.add(cur)
        if cur == decision_id:
            break
        node = nodes_by_id.get(cur)
        if node is not None and node["t"] not in {"start", "end", "decision"}:
            chain.append(cur)
        next_edges = [e for e in forward_edges if e["s"] == cur]
        if not next_edges:
            break
        cur = next_edges[0]["t"]
    return chain


def _reaches(
    src: str,
    target: str,
    forward_edges: list[dict[str, Any]],
) -> bool:
    """Forward-only reachability check from `src` to `target`."""
    if src == target:
        return True
    seen: set[str] = {src}
    stack: list[str] = [src]
    while stack:
        cur = stack.pop()
        for e in forward_edges:
            if e["s"] != cur:
                continue
            t = e["t"]
            if t == target:
                return True
            if t not in seen:
                seen.add(t)
                stack.append(t)
    return False


def _deps_for(
    node_id: str,
    forward_edges: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    """Predecessor work-node ids for `node_id` (skips start/decision)."""
    deps: list[str] = []
    for e in forward_edges:
        if e.get("t") != node_id:
            continue
        s = e.get("s")
        s_node = nodes_by_id.get(s)
        if s_node is None:
            continue
        if s_node["t"] in {"start", "decision"}:
            continue
        deps.append(s)
    return deps


def _intention_text_for(node: dict[str, Any], *, iteration: int | None = None) -> str:
    op = node.get("o") or {}
    resolver = op.get("resolver") or "(unspecified)"
    if iteration is not None:
        return (
            f"L-system rule rewrite, iteration {iteration}. Reads upstream "
            f"lstate, applies params.rules to current_string, increments "
            f"iteration. Resolver: {resolver}."
        )
    return f"L-system workflow node {node['id']!r}. Resolver: {resolver}."


def _prism_op(node: dict[str, Any]) -> dict[str, Any] | None:
    op = node.get("o")
    if not isinstance(op, dict):
        return None
    return {
        "op": op.get("op"),
        "resolver": op.get("resolver"),
        "model": op.get("model"),
    }


def _make_spec_node(node: dict[str, Any], deps: list[str]) -> dict[str, Any]:
    return {
        "node_id": node["id"],
        "intention_text": _intention_text_for(node),
        "depends_on": deps,
        "prism_operator": _prism_op(node),
    }


__all__ = ["adapt", "resolve"]
