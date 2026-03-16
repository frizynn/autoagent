# GSD State

**Active Milestone:** M006 — Autoresearch Pivot
**Active Slice:** S02 — Conversational Setup + Minimal UX (next)
**Active Task:** none (S02 not yet planned)
**Phase:** Between slices

## Milestone Registry
- ✅ **M001:** Core Loop & Infrastructure
- ✅ **M002:** Search Intelligence
- ✅ **M003:** Safety & Verification
- ✅ **M004:** Interview & Polish
- ✅ **M005:** Pi TUI Extension
- 🔄 **M006:** Autoresearch Pivot (S01 done, S02+S03 remaining)

## Recent Decisions
- D079: system.md MODE A/B keyed on .autoagent/ existence
- D080: go command prefers local .autoagent/program.md over bundled
- D081: stop is a no-op placeholder until S03
- D082: Extension reads prompts via readFileSync at command time

## Blockers
- None

## Next Action
Plan and execute S02: Conversational Setup + Minimal UX — launch with no project triggers conversational setup, LLM writes prepare.py + baseline pipeline.py through conversation.
