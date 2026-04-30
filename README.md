# lsystem-demo

A working composition of three independently-built systems rendering Lindenmayer fractals. The composition is the demonstration. Two example programs ship: a Koch snowflake (`koch-snowflake`, default) and a bracketed bushy tree (`bushy-tree`); both run through the same PRISM-IR + 8OS + simdecisions pipeline.

This is **Demo #1 in the publish-track demo trio.** See the [8OS overview](https://github.com/deiasolutions/8os/blob/main/docs/8OS-OVERVIEW-v3.md) for context on the trio. The full writeup with rendered output, traces, and per-tick numbers is at [`docs/koch-snowflake.md`](docs/koch-snowflake.md).

## The three composing systems

- **[PRISM-IR](https://github.com/deiasolutions/prism-ir)** — the source language. Declares the L-system rule-rewriting program: axiom, production rules, iteration count, bracket-expansion state machine, terminal turtle-command emission.
- **[8OS](https://github.com/deiasolutions/8os)** — the kernel runtime. Hosts the program's execution as an (I, R) graph; resolvers dispatch each iteration; the kernel records lineage and resolution events.
- **[simdecisions](https://github.com/deiasolutions/simdecisions)** turtledraw adapter — the rendering surface. A React/p5.js drawing canvas inside the simdecisions test harness receives turtle commands and renders to a webpage canvas.

None of the three systems were built knowing about the others as their primary use case. PRISM-IR is a general workflow language; 8OS is a general kernel; the turtledraw adapter is general drawing infrastructure for SimDecisions. The composition working at runtime is empirical evidence that the (I, R) primitive supports composition across systems built independently, on different timelines, for different primary purposes.

## What this demo witnesses (and what it does not)

This demo witnesses **composability under multi-system runtime composition** — that the (I, R) primitive carries enough architectural weight to bridge three independently-built systems at runtime.

It does not witness LLM mediation (Demo #2 / SCAN does that) or self-composition (Demo #3 / decomposition-strategy does that). It witnesses the bare composability claim — three independently-built systems meeting at the (I, R) joint.

## Pinned versions

- 8OS binary: `v1.1.0-dev.6`
- PRISM-IR spec: `v1.1`
- simdecisions: locked to commit at demo run time (recorded in writeup)

## Layout

```
docs/adapter-contract.md       Piece 1 — how the demo talks to the turtledraw adapter.
docs/koch-snowflake.md         Piece 5 — the writeup (publishable artifact).
docs/findings.md               frictions surfaced in PRISM-IR / 8OS / the adapter.
prism/koch-snowflake.prism.md  Koch snowflake L-system (default program).
prism/bushy-tree.prism.md      Bracketed bushy-tree L-system (sibling program).
ir/lsystem/                    8OS kernel records (the program(s) authored as (I, R)s).
harness/                       Python + Playwright runner bridging 8OS to the adapter.
output/                        rendered images, one per program.
```

## Reproduce

```bash
# 1. Clone all three repos
mkdir -p ~/lsystem-demo-run && cd ~/lsystem-demo-run
git clone https://github.com/deiasolutions/8os.git
git clone https://github.com/deiasolutions/lsystem-demo.git
git clone https://github.com/deiasolutions/simdecisions.git

# 2. Pin 8OS to the published version
( cd 8os && git checkout v1.1.0-dev.6 )

# 3. Install the kernel + harness as editable Python packages
( cd 8os && uv venv && uv pip install -e . )
( cd 8os && uv pip install -e ../lsystem-demo )
( cd 8os && .venv/bin/playwright install chromium )

# 4. Start the simdecisions dev server (separate terminal)
( cd simdecisions/browser && npm install && npm run dev )

# 5. Run the demo
( cd 8os && .venv/bin/python ../lsystem-demo/harness/run_demo.py )
```

The harness writes the rendered PNG to `output/` and prints the per-tick trace to stdout. Total wall-clock: a few seconds. API spend: $0 (deterministic decomposer; no LLM bridge crossings).

## License

Apache 2.0. See [`LICENSE`](LICENSE).
