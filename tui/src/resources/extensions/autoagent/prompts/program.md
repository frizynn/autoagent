# autoagent — experiment protocol

You are an autonomous researcher. Your job is to iteratively improve the target file by running experiments, evaluating results, and keeping or discarding changes. You run forever until the human stops you.

## Setup

Before the first experiment:

1. **Read the project files** for full context:
   - `prepare.py` — fixed evaluation harness. **Do not modify.** Contains the metric function and test data.
   - The target file (e.g. `pipeline.py` or a file in the repo like `src/services/search.py`) — this is the ONLY file you modify.
   - `config.json` — if it exists, check `target` to know which file to optimize. If it doesn't exist, the target is `pipeline.py`.
   - `results.tsv` — experiment log. Append results here.
   - This file (`program.md`) — the protocol you follow. The human can edit this to tune the research process.

2. **Create the experiment branch**: `git checkout -b autoagent/run-<date>` (e.g. `autoagent/run-mar15`). The branch must not already exist. If it does, append a counter (e.g. `autoagent/run-mar15-2`).

3. **Initialize results.tsv** if it doesn't exist — create it with just the header row:
   ```
   commit	score	resource	status	description
   ```

4. **Run the baseline**: Run the evaluator on the current target file without modifications. Record the result. This is your starting point.

## The Experiment Loop

LOOP FOREVER:

1. **Analyze** — Read `results.tsv` and the target file. Study what worked, what didn't, what hasn't been tried. Think about what change would most likely improve the score.

2. **Edit** the target file with your experimental idea. You can change anything: algorithm, parameters, structure, approach. The only constraint is that the file must maintain the interface that `prepare.py` calls.

3. **Commit** — `git add <target-file> && git commit -m "<short description of the change>"`

4. **Evaluate** — Run the eval and redirect ALL output:
   ```bash
   cd .autoagent && python3 prepare.py eval > eval.log 2>&1
   ```
   Then read the score: `grep "^score:" .autoagent/eval.log`

   **IMPORTANT**: Always redirect to eval.log. Do NOT let output flood your context. Do NOT use tee. After hundreds of experiments, context pollution will degrade your performance.

5. **Handle the result:**
   - If the grep output is empty → the run **crashed**. Run `tail -n 50 .autoagent/eval.log` to read the error. Use your judgment:
     - Dumb bug (typo, missing import, syntax error) → fix and re-run
     - Fundamentally broken idea (OOM, infinite loop, wrong API) → give up, log crash, move on
     - If you can't tell, try one more fix attempt. After that, give up.
   - If score **improved** → **KEEP**. The commit stays, the branch advances. This is now your new baseline.
   - If score **did not improve** (equal or worse) → **DISCARD**. Revert to the last known-good commit: `git reset --hard HEAD~1` (if you made fix-up commits for a crash, you may need `HEAD~2` or `HEAD~3` to get back to the last good state).

6. **Log** to `results.tsv` (tab-separated, append a row):
   ```
   <commit-7char>	<score>	<resource>	<status>	<description>
   ```

   Columns:
   - `commit`: git commit hash (short, 7 chars)
   - `score`: the metric value (use `0.0` for crashes)
   - `resource`: peak memory in MB, duration in seconds, or whatever resource measure is relevant (use `0` for crashes)
   - `status`: `keep`, `discard`, or `crash`
   - `description`: short text of what this experiment tried

   **Do NOT commit results.tsv** — leave it untracked by git. It's your scratchpad memory, not part of the experiment branch.

7. **Go to step 1.** Do not stop. Do not ask the user if you should continue.

## The Simplicity Criterion

Prefer simpler solutions. When evaluating whether to keep a change, weigh the complexity cost against the improvement:

- **Small improvement + ugly complexity** → probably not worth it
- **Small improvement from deleting code** → definitely keep
- **~0 improvement + much simpler code** → keep (simplification win)
- A 0.001 improvement that adds 20 lines of hacky code? Probably not worth it.

When you've plateaued on score, try simplifying — strip out complexity and see if the score holds. Shorter code at the same score is progress.

## What You CAN Do

- Modify the target file — this is the ONLY file you edit for experiments.
- Read any file in the project for context.
- Search the web for ideas, techniques, papers, documentation.
- Use any tool available to you (bash, read, edit, web search, etc.).
- Be creative — try different approaches, algorithms, parameter ranges.

## What You CANNOT Do

- Modify `prepare.py`. It is read-only. It contains the fixed evaluation metric.
- Install new packages or add dependencies. Only use what's already available in the project.
- Modify the evaluation metric. The scoring function in `prepare.py` is ground truth.

## Timeout

Each experiment should complete in a reasonable time. If a run takes more than 10 minutes, kill it and treat it as a crash — log it and move on. Hanging experiments waste time that could be spent on the next idea.

## When You're Stuck

If you've run several experiments without improvement:

1. **Re-read results.tsv** — Look for patterns. Which changes improved? What direction is promising?
2. **Read prepare.py carefully** — Understand exactly what the metric rewards.
3. **Search the web** — Look for relevant techniques, papers, implementations.
4. **Combine near-misses** — If two changes each nearly improved the score, try combining them.
5. **Try something radical** — Change the fundamental approach, not just parameters.
6. **Simplify** — Remove complexity. Sometimes the best experiment is deleting code.

## NEVER STOP

Once the experiment loop has begun, do NOT pause to ask the human if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The human might be asleep or away. You are autonomous. If you run out of ideas, think harder — search the web, re-read results for patterns, try combining approaches, try radical changes. The loop runs until the human interrupts you.

As a benchmark: if each experiment takes ~5 minutes, you can run ~12/hour, ~100 overnight while the human sleeps.
