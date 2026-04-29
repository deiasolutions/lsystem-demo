---
authored_by: q88n
authored_on: '2026-04-29T00:00:00.000Z'
authored_via: outside
authority_level: convention
collapsed_summary: Lindenmayer fractal plant — iteratively rewrite an axiom with two production rules, expand brackets to a flat absolute-coordinate command stream, render via the simdecisions turtledraw adapter.
depends_on: []
domain: lsystem-prism-decomposer
expanded_into: null
id: lsystem-fractal-plant
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

Lindenmayer's fractal plant, expressed as a PRISM-IR v1.1 Level-1 program for
hosting in 8OS and rendering via the simdecisions turtledraw adapter. The
8OS-hosted frontmatter `id` (above) and the PRISM-IR body `id` (below) match
exactly per v1.1 identity discipline.

The workflow is six structural phases: **seed** the system with the axiom;
**apply rules** for one rewrite round; **iter check** routes back for the next
round or forward when the iteration count is reached; **expand brackets**
walks the bracketed string with an explicit (x, y, heading) stack and emits
a flat absolute-coordinate command stream the adapter can consume directly
(the adapter's grammar has no `[`/`]` — bracket semantics live in the
workflow); **emit to canvas** transmits the flat command stream to the
turtledraw adapter via Playwright; **end** terminates.

The composition under test is PRISM-IR + 8OS + simdecisions: the program here
declares the workflow; 8OS hosts it as an (I, R) graph; simdecisions's
turtledraw adapter is the rendering surface. None of the three was built
knowing about the others as a primary use case; the demo is empirical
evidence that the (I, R) primitive supports composition across systems built
independently.

```yaml
v: 1.1.0
prism: lsystem-fractal-plant
version: 1.1.0
conformance: level-1

id: lsystem-fractal-plant
name: Lindenmayer fractal plant
domain: lsystem/fractal-plant
intention: |
  Render Lindenmayer's fractal plant by iteratively rewriting an axiom with
  two production rules, expanding the resulting bracketed string into a flat
  absolute-coordinate turtle command stream, and emitting that stream to a
  turtledraw rendering surface.

failure_tolerance:
  apply_rules: retry
  expand_brackets: retry
  emit_to_canvas: escalate

constraints:
  - sla: total flow under 60s
    fail: drop
    priority: low

params:
  axiom: "X"
  rules:
    X: "F+[[X]-X]-F[-FX]+X"
    F: "FF"
  target_iterations: 6
  angle_degrees: 25
  forward_step_px: 4
  start_x: 320
  start_y: 700
  start_heading_degrees: -90
  pen_color: { r: 14, g: 90, b: 26 }
  pen_width: 1
  background_color: { r: 240, g: 240, b: 230 }

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

The `op: script, resolver: <id>` declarations above bind to deterministic
Python implementations registered as `_kernel.resolver` records in the host
8OS instance. The implementations live in this repo at
`harness/resolvers/`; the registration records live in
`8os/ir/_kernel/resolver/`. Each resolver is small (tens of lines) because
the workflow's structure is carried by the PRISM-IR graph, not by ad-hoc
resolver internals.

- **`lsystem-seed`** — initialize `lstate` from `params`: `current_string =
  params.axiom`, `iteration = 0`, `flat_commands = null`.
- **`lsystem-apply-rules`** — one rewrite pass: replace each character of
  `lstate.current_string` with `params.rules[char]` if a rule matches, else
  leave unchanged; increment `lstate.iteration`.
- **`lsystem-expand-brackets`** — walk `lstate.current_string` with an
  explicit `(x, y, heading)` stack. `[` pushes; `]` pops and emits a `goto
  x y; left/right θ` pair to restore turtle pose without drawing (penup
  around the move; pendown after). `F` emits `forward step`; `+` and `-`
  emit `right θ` and `left θ`. The result is a semicolon-separated string
  of flat commands the adapter can execute.
- **`lsystem-emit-to-canvas`** — invoke the Playwright harness:
  fill `input.tdraw-input` at `localhost:5173/?set=turtle-draw` with
  `lstate.flat_commands`, capture the canvas, write the PNG to
  `output/fractal-plant.png`. Chunked sends if the command string exceeds
  the input field's tolerated paste length.

## Hosting note

The 8OS frontmatter at the top of this file presumes the file is mirrored
into the host 8OS repo at `8os/ir/lsystem/lsystem-fractal-plant.prism.md`
when the demo runs. The lsystem-demo repo is the canonical authoring
location; the deterministic translator (`harness/prism_to_ir.py`) imports
this file into 8OS and materializes the seven nodes above as (I, R) records
under `8os/ir/lsystem/`, with `depends_on` edges derived from this body's
`edges:` list.

The `_kernel.scope` record for scope `lsystem` is authored once at translator
initialization if it does not already exist.
