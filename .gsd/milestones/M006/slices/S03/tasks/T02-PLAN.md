---
estimated_steps: 5
estimated_files: 1
---

# T02: Wire dashboard, stop, and branch info into index.ts

**Slice:** S03 — Multi-Experiment + Dashboard
**Milestone:** M006

## Description

Connect the DashboardOverlay component to the Ctrl+Alt+A shortcut, wire the real stop command to `ctx.abort()`, and enhance session_start with git branch awareness. This is pure integration wiring — all the component logic is in T01's `dashboard.ts`.

## Steps

1. Add imports to `index.ts`:
   - Add `import { DashboardOverlay } from "./dashboard.js"` (note: .js extension for ESM)
   - Add `import { execSync } from "node:child_process"`
   - Ensure `ExtensionContext` is imported from `@gsd/pi-coding-agent` (needed for stop handler's `ctx.isIdle()` and `ctx.abort()` types)
2. Add a `getCurrentBranch()` helper function in `index.ts`:
   ```typescript
   function getCurrentBranch(): string | null {
     try {
       return execSync("git branch --show-current", { encoding: "utf-8", cwd: process.cwd() }).trim() || null;
     } catch { return null; }
   }
   ```
3. Replace the Ctrl+Alt+A shortcut handler. Change from the placeholder notification to:
   ```typescript
   pi.registerShortcut(Key.ctrlAlt("a"), {
     description: "AutoAgent dashboard",
     handler: async (ctx) => {
       await ctx.ui.custom<void>(
         (tui, theme, _kb, done) => {
           return new DashboardOverlay(tui, theme, () => done());
         },
         {
           overlay: true,
           overlayOptions: {
             width: "80%",
             minWidth: 60,
             maxHeight: "80%",
             anchor: "center",
           },
         },
       );
     },
   });
   ```
4. Replace the stop case in the command handler. Change from the placeholder "Nothing running" notification to:
   ```typescript
   case "stop": {
     if (ctx.isIdle()) {
       ctx.ui.notify("Nothing running to stop.", "info");
     } else {
       ctx.abort();
       ctx.ui.notify("⚡ Experiment loop stopped.", "info");
     }
     return;
   }
   ```
5. Enhance session_start to show git branch info. After computing `statusLine`, check if the current branch is an `autoagent/*` branch. If so, append the branch name to the status. Add branch context to the notification:
   ```typescript
   const branch = getCurrentBranch();
   const branchInfo = branch?.startsWith("autoagent/") ? ` · branch: ${branch}` : "";
   // Include branchInfo in the statusLine or notification
   ```
   Update the notification to include `branchInfo` and add a Ctrl+Alt+A hint:
   ```
   `⚡ AutoAgent${branchInfo}\n${statusLine}\n\nCommands: /autoagent go | stop · Ctrl+Alt+A dashboard`
   ```

## Must-Haves

- [ ] DashboardOverlay imported from ./dashboard.js
- [ ] Ctrl+Alt+A opens dashboard via ctx.ui.custom() with overlay: true and overlayOptions
- [ ] Stop case calls ctx.isIdle() to check, ctx.abort() to stop
- [ ] session_start shows current branch name when on an autoagent/* branch
- [ ] execSync imported from node:child_process for branch detection

## Verification

```bash
FILE="tui/src/resources/extensions/autoagent/index.ts"

# Dashboard import
grep -q 'import.*DashboardOverlay.*from.*dashboard' "$FILE" || (echo "FAIL: no dashboard import" && exit 1)

# Overlay wiring
grep -q "overlay.*true" "$FILE" || (echo "FAIL: no overlay: true" && exit 1)
grep -q "overlayOptions" "$FILE" || (echo "FAIL: no overlayOptions" && exit 1)

# Stop wired to abort
grep -q "ctx.abort()" "$FILE" || (echo "FAIL: no ctx.abort()" && exit 1)
grep -q "isIdle" "$FILE" || (echo "FAIL: no isIdle check" && exit 1)

# Branch detection
grep -q "git branch" "$FILE" || (echo "FAIL: no git branch detection" && exit 1)
grep -q "execSync" "$FILE" || (echo "FAIL: no execSync import" && exit 1)

# No more placeholder text
! grep -q "coming in S03\|coming soon" "$FILE" || (echo "FAIL: placeholder text still present" && exit 1)

# Ctrl+Alt+A hint in notification
grep -q "Ctrl+Alt+A\|dashboard" "$FILE" || (echo "FAIL: no dashboard hint in notification" && exit 1)

echo "ALL PASS"
```

## Inputs

- `tui/src/resources/extensions/autoagent/dashboard.ts` — T01's output. Exports `DashboardOverlay` class with constructor `(tui: { requestRender: () => void }, theme: Theme, onClose: () => void)`.
- `tui/src/resources/extensions/autoagent/index.ts` — current extension entry point with placeholder Ctrl+Alt+A handler, no-op stop command, and session_start without branch info.
- GSD Dashboard wiring pattern from `gsd-2/src/resources/extensions/gsd/commands.ts` lines 193-205: `ctx.ui.custom<void>((tui, theme, _kb, done) => new Overlay(tui, theme, () => done()), { overlay: true, overlayOptions: { ... } })`.
- `ctx.isIdle(): boolean` and `ctx.abort(): void` are confirmed on `ExtensionContext` (from types.d.ts lines 193-195).

## Expected Output

- `tui/src/resources/extensions/autoagent/index.ts` — modified to import DashboardOverlay, wire Ctrl+Alt+A to overlay, wire stop to ctx.abort(), and show branch info in session_start.
