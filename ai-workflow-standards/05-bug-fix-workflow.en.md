# 05 · Bug Fix Workflow

> The core discipline of bug fixing: **pin the bug with a failing test before you fix it**. Otherwise you never know whether you actually fixed it or just made the symptom go away.
> Chinese counterpart: `05-bug-fix-workflow.zh_CN.md`.
> Bug report template: `templates/bug-report.md`.

---

## 1. Core Principles

1. **Reproduce first**: a bug you can't reproduce reliably is a bug you can't verify.
2. **Write a red test**: encode the repro path as a test; on `main` it MUST fail.
3. **Minimal change**: touch only what's necessary. No piggybacked refactors, no opportunistic cleanup.
4. **Verify green**: the test turns green and nothing else regresses.
5. **Find the root cause**: fixing the symptom isn't fixing the bug — ask "why was this bug possible in the first place?"
6. **Prevent regression**: the test stays on main; the same bug can't come back.

## 2. End-to-End Flow

### Step 1: Receive the bug

Source:
- You hit it yourself → fill out a bug report (see `templates/bug-report.md`).
- User / external report → ask them to fill the template.
- Monitoring alert → reproduce it and fill the report yourself.

**Minimum info**: repro steps, actual behavior, expected behavior, environment (OS, versions, config), relevant logs.

### Step 2: Dedupe

```bash
gh issue list --state all --search "<keywords>"
```

Confirm it's not a known issue. If it is → comment on / reopen the existing issue. Don't open a duplicate branch.

### Step 3: Branch off

```bash
git checkout main
git pull --ff-only origin main
git checkout -b fix/<short-bug-name>
```

### Step 4: Reproduce and write the red test

**This is the most important step.**

```
1. Walk through the bug report's repro steps manually to confirm the bug exists.
2. Encode the repro as an automated test:
   - Backend: tests/test_<bug-area>.py
   - Frontend: tests/<area>.test.ts
3. Run the test on main → it MUST fail.
   git stash
   git checkout main
   run test → red
   git checkout fix/<short-bug-name>
   git stash pop
```

**When a red test is genuinely impossible**:
- UI visual bug → use E2E screenshot diff or detailed manual test steps.
- Real external service bug → mock + contract test.
- Concurrency / timing bug → injection test (mock time / lock / scheduler).
- Performance bug → benchmark with a threshold.

If you can't write a red test → you **MUST** explain why in the PR and provide an alternative validation (manual steps + screenshots + logs).

### Step 5: Locate the root cause

Don't patch on the symptom. Locate first:

- Add temporary `print` / `console.log` (delete afterward) → run the test → see where state diverges.
- Use a debugger: `pytest --pdb`, `pnpm test --debug`, Chrome DevTools.
- Read git history: `git log -S "<suspicious string>"` to find the commit that introduced the bug.
- Bisect: `git bisect start` / `git bisect bad HEAD` / `git bisect good <older-commit>`.

Only start fixing once you've located the root cause.

### Step 6: Write the minimal fix

- **Minimal**: change only the lines that caused the bug.
- **No piggybacked refactors**: noticed cleanup opportunities → record them, do them on a separate branch.
- **No new dependencies**: unless the bug's root cause is a dependency issue.
- **Backward compatibility**: if the fix changes behavior, consider whether users depend on the old behavior (and document it in the PR).

### Step 7: Verify

```bash
# Run the red test from step 4 → should now be green
cd backend && PYTHONPATH=. uv run pytest tests/test_<bug-area>.py -v
# or
cd frontend && pnpm test -- <pattern>

# Full regression
cd backend && make test
cd frontend && pnpm test
```

- Red test is green ✅
- No other tests regressed ✅
- Lint clean ✅
- Typecheck clean (frontend) ✅

### Step 8: Add regression coverage (optional but recommended)

The red test covers **one** trigger path. Ask:

- Are boundary values of the same input class covered?
- Are negative cases (scenarios that should NOT trigger) tested?
- Does the fix open any new hole?

If the red test alone doesn't cover the root cause, **add more tests** so future variants get caught.

### Step 9: Open the PR

Per `06-pr-workflow.en.md`, especially fill the **Bug fix verification** section:

```markdown
## Bug fix verification
- Test path: tests/test_sandbox.py::test_acquire_timeout_on_cold_start
- Red on main: yes (run on commit abc1234)
- Green on branch: yes
```

PR title: `fix(<scope>): <one-line-description>`.
Link the issue: `Fixes #123`.

### Step 10: After merge

- Delete the fix branch.
- Confirm the issue auto-closed (the `Fixes` keyword did its job).
- If the bug exposed a process gap (e.g., a missing class of tests), open a `chore` branch to tighten the gates.

## 3. Special Bug Types

### Production hotfix

```
1. Tag the current main state (rollback anchor)
2. Branch: git checkout -b hotfix/<name>
3. Minimal fix + red test
4. Accelerated review (self-review + one reviewer)
5. Merge + deploy immediately
6. Afterward: add regression tests, write a postmortem (docs/postmortems/YYYY-MM-DD-<name>.md)
```

### Flaky test

- Don't ignore it. Don't slap on `@pytest.mark.flaky` to retry-mask it.
- Loop it: `pytest --count=100 -x` to surface the failure mode.
- Root cause is usually: race condition, implicit state dependency, uncleaned external resource.
- After fixing, verify stability with `--count` looping.

### Performance regression

- Don't fix by feel.
- Run benchmarks (before vs after the offending commit) → quantify the regression.
- Profile to find the hot spot (py-spy, Chrome DevTools).
- Fix → re-benchmark → quantify the improvement.
- Optionally wire the benchmark into a CI performance job.

### Security-related bug

- Classify by severity (CVSS reference).
- Critical → fix privately; don't open a public issue until a patch is available.
- After the fix, write `docs/security/advisories/YYYY-MM-DD-<name>.md` covering scope, fixed versions, upgrade guidance.

## 4. Anti-patterns

- ❌ **Symptom fixed, root cause untouched**: wrap the exception in a try/except and swallow it; the bug is still there.
- ❌ **Piggybacked refactors**: fix the bug and clean up unrelated code → the PR is unreviewable and un-revertable.
- ❌ **Deleting tests**: the test fails, so delete it; the bug is "fixed."
- ❌ **Mocking out the real path**: tests pass, but the bug was never actually exercised.
- ❌ **No PR linkage**: future maintainers can't trace what happened.
- ❌ **Lost repro steps**: the bug report didn't capture the repro path; no one can verify later.

## 5. What a Complete Bug Fix PR Looks Like

Title: `fix(sandbox): resolve timeout on cold container start`

```markdown
Fixes #421

## Why
Reported: the first sandbox call after a cold start always times out at 30s.
Logs show the readiness probe flips green after 2s, but the acquire path polls at 1s intervals and keeps missing it.

## What changed
Sandbox acquire poll interval is now configurable, default 500ms (previously hardcoded at 1s).

## Surface area
- [x] Backend API
- [ ] Frontend UI
- [ ] Agents / LangGraph
- [ ] Sandbox
- [ ] Skills
- [ ] Dependencies
- [x] Default behavior change   ← poll interval default changed
- [ ] Docs / tests / CI only

## Bug fix verification
- Test path: backend/tests/test_sandbox.py::test_acquire_timeout_on_cold_start
- Red on main: yes (verified on commit abc1234)
- Green on branch: yes

## Validation
cd backend && make lint && make test
Manual cold-start repro: rm -rf .sandbox-cache && make dev && called /api/runs/stream 3 times, all succeeded

## AI assistance
**Tool(s) used:** Claude Code
**How you used it:** located the hardcoded poll interval + drafted the red test
- [x] I have read and understand every line of this change and take responsibility for it.
```

---

**One-line summary**: pin with a red test → find root cause → minimal fix → verify green → PR. **A bug fix without a red test is a fake fix.**
