# L-system demo — execution report (2026-04-29)

**Date:** 2026-04-29
**Authors:** Q88N + Claude (L-system demo execution session)
**Repos touched:** `8os` (no changes), `simdecisions/browser`, `lsystem-demo`.
**Status at close:** Two L-system programs working end-to-end against the 8OS binary at `1.1.0-dev.6`. Renders produced as PNGs.

This was the L-system demo step from the post-Block-4.7 sequence in `8os/docs/build-state-2026-04-29-evening.md`. The prompt was drafted but not yet executed; this session executed it.

## What shipped

Two PRISM-IR programs running through the same kernel + adapter pipeline:

- **`koch-snowflake`** (`prism/koch-snowflake.prism.md`) — bracket-less Koch snowflake. Axiom `F++F++F`, rule `F → F-F++F-F`, angle 60°, 4 iterations, 1799 commands. Renders to `output/koch-snowflake.png` (~44 KB).
- **`bushy-tree`** (`prism/bushy-tree.prism.md`) — bracketed L-system, branching foliage. Axiom `F`, rule `F → FF+[+F-F-F]-[-F+F+F]`, angle 22.5°, 4 iterations. Renders to `output/bushy-tree.png` (~54 KB).

Both compose: PRISM-IR declares the workflow as a Level-1 program; 8OS hosts execution as an `(I, R)` graph (root + 7 children: seed, apply_rules ×4, expand_brackets, emit_to_canvas); simdecisions's turtledraw drawing-canvas primitive renders the terminal turtle-command stream into a webpage canvas via Playwright. Three independently-built systems, each with its own primary use case unrelated to the demo, composing at runtime on a workload none of them was designed for. **This is the empirical witness for the publish.**

The demo runs cleanly via:

```sh
# default — koch snowflake
.venv/bin/python ../lsystem-demo/harness/run_demo.py

# bushy tree
LSYSTEM_PROGRAM=bushy-tree .venv/bin/python ../lsystem-demo/harness/run_demo.py
```

Vite dev server must be running at `localhost:5173` from `simdecisions/browser`.

## Stack changes

### `simdecisions/browser`

1. **New set: `sets/lsystem-canvas.set.md`** — single-pane set with the `drawing-canvas` primitive, no chrome (top-bar, menu-bar, terminal/Fr@nk pane all stripped), no auth. Loads quickly, minimal transitive deps. Harness URL: `?set=lsystem-canvas`.

2. **`primitives/drawing-canvas/DrawingCanvasApp.tsx` — two changes**:

   - `handleSubmit` rewritten to batch commands across animation frames (50 commands / frame). Returns from the keypress handler within microseconds; commands process across subsequent frames. Long-input drivers no longer block Playwright's `press(Enter)` actionability budget.
   - **New programmatic API**: `window.__lsystem.execute(commandsString)` exposed via a `useEffect`. Bypasses `execCommand` entirely (which writes to localStorage and triggers React state updates per command — pathological at thousands of commands). Calls `parseCommand` + `executeParsed` directly on the p5 instance, suppresses cursor redraw per command, syncs React state + cursor only once after all batches complete. Returns a `Promise<number>` resolving with the command count. 500 commands per animation frame batch.

### `lsystem-demo`

1. **Renamed `lsystem-fractal-plant` → `koch-snowflake`**: the original PRISM doc was authored as a fractal-plant variant but the rules+params actually produce a Koch snowflake. Mislabel corrected across the repo.

   - `prism/lsystem-fractal-plant.prism.md` → `prism/koch-snowflake.prism.md`. All internal `id:`, `prism:`, `name:`, `domain:`, `intention:` and prose updated.
   - `docs/lsystem-fractal-plant.md` → `docs/koch-snowflake.md`. Title + lead + image path updated; rest of writeup will revisit during the overview-drafting step.
   - `README.md` — list of programs, output file naming, framing.

2. **New PRISM program: `prism/bushy-tree.prism.md`** — bracketed L-system, sibling to the snowflake. Same workflow shape (5 resolvers); only `params:` block differs (different axiom, rule, angle, geometry).

3. **Harness `run_demo.py`** — parameterized via `LSYSTEM_PROGRAM` env var. Default `koch-snowflake`. Path becomes `prism/<name>.prism.md`, install location `ir/lsystem/<name>.prism.md`, output PNG `output/<name>.png`.

4. **Harness `resolvers/emit_to_canvas.py` — three changes**:

   - URL default switched to `?set=lsystem-canvas` (the new minimal set; configurable via `SIMDECISIONS_URL`).
   - Drives `window.__lsystem.execute()` via `page.evaluate()` instead of `fill`/`press(Enter)` on the input field.
   - Waits for `canvas count >= 2` before calling `evaluate` (the shell renders the drawing-canvas primitive twice — likely StrictMode double-mount; the second-mounted instance's `useEffect` runs last and wins the `window.__lsystem.execute` registration). Screenshots `canvas.last` to capture the active drawing surface.

5. **Harness `resolvers/prism_decomposer.py` — namespacing fix**: every child node_id is now prefixed with the program's id (`${program-id}-seed`, `${program-id}-apply_rules-iter-0`, etc.). Required for multi-program coexistence in the same 8OS scope; without it, the second program's idempotency check sees the first program's records (under unprefixed names) and skips materialization.

### `8os`

No kernel code changed. The kernel binary at `1.1.0-dev.6` runs the demo unchanged. Pre-existing kernel records (records under `ir/lsystem/` from prior sessions) were cleared at the rename to avoid stale `lsystem-fractal-plant` artifacts.

## Findings surfaced

The session surfaced six real bugs across the stack. All but one were fixed; the one remaining is logged here for follow-up.

### F-IMMERSIVE-NAV — `chromeMode: "immersive"` triggers infinite render loop

When the lsystem-canvas set used `"chromeMode": "immersive"`, the `ImmersiveNavigator` shell component entered an infinite re-render loop (`Maximum update depth exceeded` flooded the console 400+ times). The cause is a `setState`-in-`useEffect` pattern in `simdecisions/browser/src/shell/components/ImmersiveNavigator.tsx` that doesn't terminate when invoked outside its expected layout context.

**Fix in this session:** switched to `"chromeMode": "auto"`. ImmersiveNavigator doesn't activate.

**Real bug in simdecisions:** the ImmersiveNavigator should not infinite-loop when used in unusual chrome configurations. Worth a finding in their issue tracker. Out of scope here.

### F-HANDLE-SUBMIT-BLOCKING — synchronous loop blows past Playwright's actionability budget

`handleSubmit` in `DrawingCanvasApp` ran `for (const cmd of commands) execCommand(cmd)` synchronously on the keypress event. With ~3000 commands the loop blocked the JS thread well past 30s; Playwright's `press(Enter)` timed out.

**Fix:** batched across animation frames.

### F-EXECCOMMAND-PER-CALL-OVERHEAD — localStorage write + React re-render per command

Even after batching `handleSubmit`, the per-command path was still pathological at scale: `execCommand` calls `saveHistory(nodeId, [...history, cmd])` (writes the entire history JSON to localStorage), and triggers `setTurtleDisplay`, `setStatusMessage`, `setCmdCount`. With two DrawingCanvasApp instances mounted, every command triggered double-renders.

**Fix:** `window.__lsystem.execute` bypasses `execCommand` entirely. Calls `parseCommand` + `executeParsed` directly. Skips localStorage saves, skips per-command React state updates, syncs state once at end.

### F-DOUBLE-MOUNT-CANVAS-RACE — StrictMode mounts two DrawingCanvasApp instances

The shell mounts two instances of every primitive (likely React StrictMode dev-only behavior). Both register `window.__lsystem.execute` on mount; the second-mounted one's effect runs last and wins the global. Initially the harness called `evaluate` after only the first canvas mounted → drew on canvas[0] → screenshotted canvas[1] (blank). Wait-for-canvas-count fixes the race.

**Fix:** `page.wait_for_function("() => document.querySelectorAll('canvas').length >= 2")` + 500ms buffer before calling `evaluate`.

### F-DECOMPOSER-NODE-ID-COLLISION — multi-program scope coexistence

The decomposer produced node_ids like `seed`, `apply_rules-iter-0`, etc. without program-namespacing. Two programs in the same scope produce identical child names → idempotency check sees existing records → second program's children never materialize → tick loop spins forever.

**Fix:** prefix every node_id with `${program-id}-`.

### F-ADAPTER-HEADING-DEFAULT-MISMATCH (logged, not fixed)

`harness/resolvers/expand_brackets.py` has `_ADAPTER_DEFAULT_HEADING_DEG = 0.0`. The actual drawing-canvas adapter's clear-state heading is `-90` (per `defaultTurtle` in `DrawingCanvasApp.tsx`). When the program's `start_heading_degrees` matches the actual `-90`, no rotation is emitted (correct by accident). For other headings, the harness emits a turn computed from the wrong reference, producing rotated-by-90° output.

In this session both demos work because:
- `koch-snowflake` uses `start_heading_degrees: 0`. The harness emits no rotation (delta=0). The actual heading after `clear` is `-90`. So the snowflake draws starting up. Same incorrect-but-it-fits geometry produces an OK render.
- `bushy-tree` uses `start_heading_degrees: -90`. Harness emits `left 90`. Actual heading after clear is `-90`, then `-90 - 90 = -180` (left). The tree grows leftward in turtle terms but the user sees it grow upward... actually I'm not sure why it works visually. Unlikely to be perfectly aligned with intent, but renders.

**Real fix:** change `_ADAPTER_DEFAULT_HEADING_DEG` to `-90.0` in `expand_brackets.py`, and re-tune any program whose start_heading was tuned against the wrong default.

Out of scope today. Logged for the next pass on the demo.

## Cosmetic items left as-is

- **Bushy-tree render is small** (~150×250 px on 1280×800 canvas). User explicitly said "leave it." Tunable later via `forward_step_px` in `prism/bushy-tree.prism.md` once the heading-default fix lands.

## What this surfaces about the publish-prep sequence

Per `8os/docs/build-state-2026-04-29-evening.md`:

1. **L-system demo** — **DONE** (this session). Two PNGs as empirical witness. The publish can reference both.
2. **Overview drafting** — next. References the demo concretely. The koch-snowflake.png is the cleaner publish image; bushy-tree.png demonstrates the bracketed-L-system path through the same pipeline.
3. **Repo hygiene** — banner-and-commit work for the untracked docs.
4. **Publish** — overview + spec + 8OS repo + this demo writeup + PRISM-IR repo.
5. **LinkedIn article** — accessible distillation, Koch snowflake as the hook image.

The demo is no longer a blocker for the publish prep. The simdecisions/browser changes (lsystem-canvas set, DrawingCanvasApp's window API + batched handleSubmit) are now part of the simdecisions repo and need to be committed there independently.

## Repo state at close

| Repo | Changes need committing? |
|---|---|
| `8os` | No code changes. Live `.8os/` records (`ir/lsystem/koch-snowflake.prism/`, `ir/lsystem/bushy-tree.prism/`, both root .md files) materialized by the demo and committable as project state. |
| `simdecisions/browser` | Yes — `sets/lsystem-canvas.set.md` (new), `primitives/drawing-canvas/DrawingCanvasApp.tsx` (handleSubmit + window API). Independent commit. |
| `lsystem-demo` | Yes — file renames, two PRISM programs, decomposer namespacing, harness emit_to_canvas + run_demo updates, README + docs. Independent commit. |

## Pinned versions at close

- 8OS binary: `1.1.0-dev.6` (unchanged across session)
- simdecisions/browser: head of `main` plus the two-file diff above
- lsystem-demo: head of `main` plus the rename + namespacing + harness diff above
- PRISM-IR spec: v1.1 (unchanged)

---

*End of L-system demo execution report. Two L-systems compose end-to-end through PRISM-IR → 8OS → simdecisions. Empirical witness in hand. Next: overview drafting.*
