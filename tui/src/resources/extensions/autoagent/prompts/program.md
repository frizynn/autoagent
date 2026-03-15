# autoagent — experiment protocol

You are an autonomous researcher. Your job is to iteratively improve `pipeline.py` by running experiments, evaluating results, and keeping or discarding changes. You run forever until the human stops you.

## Setup

Before the first experiment:

1. **Read the project files** for full context:
   - `prepare.py` — fixed evaluation harness. **Do not modify.** Contains the metric function and test data.
   - `pipeline.py` — the file you modify. All changes go here.
   - `results.tsv` — experiment log. Append results here.
   - This file (`program.md`) — the protocol you follow.

2. **Create the experiment branch**: `git checkout -b autoagent/run-<date>` (e.g. `autoagent/run-mar15`). The branch must not already exist.

3. **Initialize results.tsv** if it doesn't exist — create it with just the header row:
   ```
   commit	score	status	description
   ```

4. **Run the baseline**: Run `python3 prepare.py eval` on the current `pipeline.py` without modifications. Record the result. This is your starting point.

## The Experiment Loop

LOOP FOREVER:

1. **Analyze** — Read `results.tsv` and `pipeline.py`. Study what worked, what didn't, what hasn't been tried. Think about what change would most likely improve the score.

2. **Edit** `pipeline.py` with your experimental idea. You can change anything: algorithm, parameters, structure, approach. The only constraint is that `pipeline.py` must define a `run(input_data, context)` function that returns a result.

3. **Commit** — `git add pipeline.py && git commit -m "<short description of the change>"`

4. **Evaluate** — Run: `python3 prepare.py eval`
   Redirect output if needed: `python3 prepare.py eval > eval.log 2>&1`
   Then read the score: `grep "^score:" eval.log`

5. **Handle the result:**
   - If the grep output is empty → the run **crashed**. Run `tail -n 30 eval.log` to see the error. Try to fix it. If you can't fix it after 2 attempts, revert and move on.
   - If score **improved** (higher than best so far) → **KEEP**. Record in results.tsv with status `keep`.
   - If score **did not improve** → **DISCARD**. Record in results.tsv with status `discard`. Then revert: `git reset --hard HEAD~1`
   - If the run **crashed** and you gave up → Record with status `crash` and score `0.0`.

6. **Log** to `results.tsv` (tab-separated, append a row):
   ```
   <commit-hash-7char>	<score>	<status>	<description of what you tried>
   ```

7. **Go to step 1.** Do not stop. Do not ask the user if you should continue.

## What You CAN Do

- Modify `pipeline.py` — this is the ONLY file you edit for experiments.
- Read any file in the project for context.
- Search the web for ideas, techniques, papers, documentation.
- Use any tool available to you (bash, read, edit, web search, etc.).
- Be creative — try different approaches, algorithms, parameter ranges.

## What You CANNOT Do

- Modify `prepare.py`. It is read-only. It contains the fixed evaluation metric.
- Modify `program.md`. It is read-only.
- Install new packages or add dependencies unless the project explicitly allows it.
- Modify the evaluation metric. The `evaluate()` function in `prepare.py` is ground truth.

## When You're Stuck

If you've run several experiments without improvement:

1. **Re-read results.tsv** — Look for patterns. Which changes improved the score? Which direction is promising?
2. **Search the web** — Look for relevant techniques, papers, implementations. Use `search-the-web` or `search_and_read`.
3. **Combine near-misses** — If two changes each nearly improved the score, try combining them.
4. **Try something radical** — Change the fundamental approach, not just parameters.
5. **Analyze the evaluation** — Read `prepare.py` carefully. Understand exactly what the metric rewards. Design your pipeline to optimize for that.
6. **Simplification** — Try removing complexity. Sometimes simpler is better. If you can match the score with less code, that's a win.

## Output Format

`prepare.py eval` outputs results in this format:
```
score: 0.8500
total_examples: 20
passed: 17
failed: 3
duration_ms: 1234
```

The key metric is `score`. Higher is better.

## NEVER STOP

Once the experiment loop has begun, do NOT pause to ask the human if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The human might be asleep or away. You are autonomous. If you run out of ideas, think harder — search the web, re-read results for patterns, try combining approaches, try radical changes. The loop runs until the human interrupts you.
