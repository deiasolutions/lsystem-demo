# Turtledraw adapter contract

**Adapter:** `simdecisions/browser/src/primitives/drawing-canvas/DrawingCanvasApp.tsx` (a React component rendering p5.js turtle graphics).
**Hosted in:** the simdecisions Shell pane host (`browser/src/shell/components/Shell.tsx`, identified by class `hhp-root`), which loads EGG layouts from `.set.md` files. The turtle-draw EGG layout is `browser/sets/turtle-draw.set.md`.
**Reachable at:** `http://localhost:5173/?set=turtle-draw` in dev (Vite serves the EGG via middleware that maps `/<eggId>.set.md` to `browser/sets/<eggId>.set.md`).

This document fixes the contract between this demo and the adapter. Pieces 2–5 are written against these facts and against nothing else.

## Transport

The adapter subscribes to an in-process React `MessageBus` (`browser/src/infrastructure/relay_bus/messageBus.ts`) by its pane `nodeId` (`turtle-canvas` per the EGG layout). The bus is provided through React context (`ShellCtx`); it is not exposed to `window` and there is no HTTP/WebSocket endpoint that fronts it.

Two practical injection paths exist for an external caller:

1. **Command input field.** The drawing-canvas pane mounts a text input (`input.tdraw-input`) that takes the same command grammar the bus channel does. Filling and submitting it is functionally equivalent to publishing a `TURTLE_COMMAND` message at `target: 'turtle-canvas'`. This is the public UI of the adapter and the path the demo uses.

2. **Direct bus access.** A caller running inside the React app (a sibling pane, a test fixture wrapping `Shell`, or a custom build that exposes the bus to `window`) can publish messages of shape `{type: 'TURTLE_COMMAND', target: 'turtle-canvas', data: {command: '<commands>'}}`. This path requires either upstream change to simdecisions or a custom test harness; the demo does not use it.

The demo bridges to the adapter via Playwright: it loads the EGG URL, fills the command input, and reads the canvas. This is the smallest viable programmatic interface and the path the prompt's Piece 1 explicitly authorizes ("smallest viable thing on the demo's edge; don't refactor upstream").

## Command grammar

Commands are whitespace-separated tokens, case-insensitive, with optional short aliases. Multiple commands are batched with `;` separators in a single submission. The parser is at `DrawingCanvasApp.tsx:66-88`.

| Command | Aliases | Args | Effect |
|---|---|---|---|
| `forward` | `fd` | `N` (px) | Move forward N pixels; draws if pen is down. |
| `back` | `bk` | `N` (px) | Move backward N pixels; draws if pen is down. |
| `right` | `rt` | `θ` (deg) | Turn clockwise θ degrees. |
| `left` | `lt` | `θ` (deg) | Turn counter-clockwise θ degrees. |
| `penup` | `pu` | — | Lift pen; subsequent moves do not draw. |
| `pendown` | `pd` | — | Lower pen; subsequent moves draw. |
| `color` | — | `R G B` | Set pen color (each 0–255). |
| `width` | — | `N` (px) | Set pen stroke width. |
| `goto` | — | `X Y` | Move to absolute canvas coordinates; draws if pen is down. |
| `home` | — | — | Return to canvas center, face up; draws if pen is down. |
| `clear` | — | — | Clear canvas, reset turtle. |
| `circle` | — | `R` (px) | Draw circle of radius R at current position (pen down only). |
| `rect` | — | `W H` (px) | Draw rectangle W×H centered on current position (pen down only). |
| `background` | `bg` | `R G B` | Set background color. |

**Notable absences.** The grammar does **not** include `[` (push state) or `]` (pop state). L-systems that use bracket commands must be flattened before submission — the demo's PRISM-IR program does this expansion in a state-machine step that maintains an explicit `(x, y, heading)` stack and emits absolute `goto`/`left`/`right`/`forward` sequences. The bracket-expansion step is a legitimate piece of workflow content; it is not a workaround for an adapter limitation but a clean separation of concerns (the workflow knows about state stacks; the renderer does not).

## Image capture

The adapter does not provide an export endpoint. The canvas is a standard HTML `<canvas>` element rendered by p5.js inside `<div class="tdraw-canvas-container">`. Three browser-native paths are available; the demo uses the first.

1. **Playwright `locator('canvas').screenshot({path})`.** Direct screenshot of the canvas region. PNG out, no JS injection needed.
2. **`canvas.toDataURL('image/png')` via `page.evaluate`.** Returns a base64 PNG string the harness can decode and write.
3. **p5's `saveCanvas()`** via `page.evaluate` against the p5 instance. Triggers a browser download; less convenient for headless capture than the first two.

## Reachability and runbook

The simdecisions repo carries a Playwright test config at `browser/playwright.config.ts` with `webServer: { command: 'npm run dev', reuseExistingServer: true }`. The demo's harness leverages this: spinning up the Vite dev server is part of the test session, not a manual prerequisite.

```bash
# One-time setup (in simdecisions repo)
cd simdecisions/browser
npm install
npx playwright install chromium

# Demo run (from this repo)
cd lsystem-demo/harness
# (TBD — Piece 4 lands the harness)
```

Production deployment exists (Vercel + Railway, per `vercel.json` and `railway.toml`) but the demo prefers local-dev for reproducibility. A reader following the writeup's runbook should not need network access to deploy infrastructure they do not own.

## Worked example (Playwright skeleton)

```typescript
import { test } from '@playwright/test'

test('renders a small turtle figure', async ({ page }) => {
  await page.goto('http://localhost:5173/?set=turtle-draw')
  await page.waitForSelector('canvas')

  const input = page.locator('input.tdraw-input')
  await input.fill('clear; forward 100; right 90; forward 100; right 90; forward 100; right 90; forward 100')
  await input.press('Enter')

  await page.locator('canvas').screenshot({ path: 'square.png' })
})
```

This skeleton is the entire transport layer. The demo's actual harness substitutes the L-system's flattened command string for the inline literal and adds optional chunking for very long submissions.

## Pinned references

- Adapter component: `simdecisions/browser/src/primitives/drawing-canvas/DrawingCanvasApp.tsx`
- EGG layout: `simdecisions/browser/sets/turtle-draw.set.md` (`nodeId: turtle-canvas`, `appType: drawing-canvas`)
- Pane host: `simdecisions/browser/src/shell/components/Shell.tsx`
- EGG resolver: `simdecisions/browser/src/sets/eggResolver.ts`
- Command parser: `DrawingCanvasApp.tsx:66-88`
- Bus subscription: `DrawingCanvasApp.tsx:406-419`
- Existing Playwright suite (no turtle-draw spec yet): `simdecisions/browser/e2e/`

The simdecisions commit hash this contract was derived against will be pinned in the writeup at demo run time.

## Out-of-scope items

- **Stack-aware grammar (`[`/`]`).** The workflow expands brackets before emission. No upstream change requested.
- **Programmatic transport (HTTP/WebSocket).** The input-field path is sufficient. No upstream change requested.
- **Image export endpoint.** Browser-native capture suffices. No upstream change requested.

If any of these proves insufficient during Pieces 2–5, the resolution is logged in `docs/findings.md` and routed back to the simdecisions project rather than worked around in the adapter.
