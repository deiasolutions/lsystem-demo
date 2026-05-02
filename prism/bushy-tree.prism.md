---
authored_by: q88n
authored_on: '2026-04-29T00:00:00.000Z'
authored_via: outside
authority_level: convention
collapsed_summary: Lindenmayer bushy tree — a bracketed L-system whose recursive substitution yields a tree-shaped fractal with branching foliage. Sibling demo to the Koch snowflake; same PRISM-IR pipeline, different params.
depends_on: []
domain: lsystem-prism-decomposer
expanded_into: null
id: bushy-tree
kind: ir-node
parent: null
projection_types:
- prism-ir
resolution_event: null
resolved_at: null
resolver: null
revalidate_trigger: null
scope: lsystem
status: open
superseded_by: null
supersedes: null
surrogate_of: null
tier: 1
valid_through: null
visible_to:
- lsystem
---

# Intention

A bushy fractal tree, expressed as a PRISM-IR v1.1 Level-1 program for hosting
in 8OS and rendering via the simdecisions turtledraw adapter. Sibling demo to
`lsystem-fractal-plant` (Koch snowflake) — same workflow shape, same resolver
pipeline; only the L-system rules and tuning params differ.

The substitution `F → FF+[+F-F-F]-[-F+F+F]` doubles the trunk on each
iteration and emits two branched sub-trees per F. With brackets the workflow's
`expand_brackets` resolver does real work (push/pop the turtle pose around
each `[ ... ]` to draw branches without disconnecting the pen path), in
contrast to the bracket-less Koch snowflake.

The composition under test is unchanged: PRISM-IR + 8OS + simdecisions. This
file just supplies different L-system params to the same five-resolver
pipeline so the demo can render two distinct fractals from one substrate.

```yaml
v: 1.1.0
prism: bushy-tree
version: 1.1.0
conformance: level-1

id: bushy-tree
name: Lindenmayer bushy tree
domain: lsystem/bushy-tree
intention: |
  Render a bushy Lindenmayer fractal tree by iteratively rewriting an axiom
  with one bracketed production rule, expanding the resulting bracketed
  string into a flat absolute-coordinate turtle command stream, and emitting
  that stream to the turtledraw rendering surface.

failure_tolerance:
  apply_rules: retry
  expand_brackets: retry
  emit_to_canvas: escalate

constraints:
  - sla: total flow under 60s
    fail: drop
    priority: low

params:
  axiom: "F"
  rules:
    F: "FF+[+F-F-F]-[-F+F+F]"
  target_iterations: 4
  angle_degrees: 22.5
  forward_step_px: 4
  start_x: 640
  start_y: 760
  start_heading_degrees: -90
  pen_color: { r: 120, g: 220, b: 140 }
  pen_width: 1
  background_color: { r: 14, g: 10, b: 26 }

entities:
  - id: lstate
    fields: [current_string, iteration, flat_commands]

nodes:
  - id: start
    t: start
  - id: seed
    t: task
    o: { op: script, resolver: lsystem-seed }
    out: [current_string, iteration]
  - id: apply_rules
    t: task
    o: { op: script, resolver: lsystem-apply-rules }
    out: [current_string, iteration]
  - id: iter_check
    t: decision
    cond: lstate.iteration < params.target_iterations
  - id: expand_brackets
    t: task
    o: { op: script, resolver: lsystem-expand-brackets }
    out: [flat_commands]
  - id: emit_to_canvas
    t: task
    o: { op: script, resolver: lsystem-emit-to-canvas }
  - id: end
    t: end

edges:
  - { s: start, t: seed }
  - { s: seed, t: apply_rules }
  - { s: apply_rules, t: iter_check }
  - { s: iter_check, t: apply_rules, c: 'lstate.iteration < params.target_iterations' }
  - { s: iter_check, t: expand_brackets, c: 'lstate.iteration >= params.target_iterations' }
  - { s: expand_brackets, t: emit_to_canvas }
  - { s: emit_to_canvas, t: end }

metrics:
  - id: iterations_completed
    expr: lstate.iteration at end
  - id: command_count
    expr: length(lstate.flat_commands) at emit_to_canvas
  - id: cycle_time_p95
    expr: rate(start -> end, p95)
```

## Resolver semantics (informational)

Identical to the snowflake demo — the resolver pipeline is shared. See
`lsystem-fractal-plant.prism.md` for the resolver descriptions. The only
difference between this program and the snowflake program is the `params:`
block: different axiom, different rule, different angle, different geometry.
The same resolvers (`lsystem-seed`, `lsystem-apply-rules`,
`lsystem-expand-brackets`, `lsystem-emit-to-canvas`) execute against this
program's params and produce a tree-shaped fractal instead of a snowflake.

## Hosting note

The 8OS frontmatter at the top of this file presumes the file is mirrored
into the host 8OS repo at `8os/ir/lsystem/bushy-tree.prism.md` when the demo
runs. Set `LSYSTEM_PROGRAM=bushy-tree` to direct the harness at this program
instead of the default `lsystem-fractal-plant`. The output PNG is named
`bushy-tree.png` so the snowflake render is preserved alongside.
