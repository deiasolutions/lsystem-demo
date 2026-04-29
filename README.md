# lsystem-demo

A working composition of three independently-built systems rendering
Lindenmayer's fractal plant. The composition is the demonstration.

## The three composing systems

- **[PRISM-IR](https://github.com/deiasolutions/prism-ir)** — the workflow
  language. Declares the L-system rule-rewriting program: axiom, production
  rules, iteration count, bracket-expansion state machine, terminal turtle-
  command emission.
- **[8OS](https://github.com/deiasolutions/8os)** — the kernel runtime. Hosts
  the workflow's execution as an (I, R) graph; resolvers dispatch each
  iteration; the kernel records lineage and resolution events.
- **[simdecisions](https://github.com/deiasolutions/simdecisions)** turtledraw
  adapter — the rendering surface. A React/p5.js drawing-canvas EGG inside
  the shiftcenter pane host receives turtle commands and renders to a webpage
  canvas.

None of the three systems were built knowing about the others as their
primary use case. PRISM-IR is a general workflow language; 8OS is a general
kernel; the turtledraw adapter is general drawing infrastructure for
SimDecisions. The composition working at runtime is empirical evidence that
the (I, R) primitive supports composition across systems built independently,
on different timelines, for different primary purposes.

## What this demo witnesses (and what it does not)

This demo witnesses **composability under multi-system runtime composition** —
that the (I, R) primitive carries enough architectural weight to bridge three
independently-built systems at runtime.

It does not witness PRISM-IR's coverage of the 43 Workflow Patterns (a
separate formal claim made by the PRISM-IR project) or 8OS's eight-axiom
kernel ABI (a structural claim of the 8OS project). Those are separate
witnesses; this is the empirical one.

## Pinned versions

- 8OS binary: `v1.1.0-dev.6`
- PRISM-IR spec: `v1.1`
- simdecisions: locked to commit at demo run time (recorded in writeup)

## Layout

```
docs/adapter-contract.md       Piece 1 — how the demo talks to the turtledraw adapter.
docs/lsystem-fractal-plant.md  Piece 5 — the writeup (publishable artifact).
docs/findings.md               frictions surfaced in PRISM-IR / 8OS / the adapter.
prism/                         PRISM-IR program(s) for the fractal plant.
ir/lsystem/                    8OS kernel records (the program authored as (I, R)s).
harness/                       Python + Playwright runner bridging 8OS to the adapter.
output/                        rendered images and turtle-command captures.
```

## Reproduce

Runbook lands here when the demo is buildable end-to-end. Status: in
construction; Piece 1 (adapter contract) ships first.
