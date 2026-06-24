# 03 · RFC Process

> **Think before you code.** An RFC (Request for Comments) forces the design out of your head and onto paper, so design mistakes surface in 5 minutes of writing instead of 5 hours of coding.
> Chinese counterpart: `03-rfc-process.zh_CN.md`.
> Templates: `templates/rfc-template.md` and `templates/design-spec-template.md`.

---

## 1. Why Write an RFC (Even When Working Alone)

Cost of skipping an RFC:
- Halfway through, you realize the direction is wrong — roll back half a day of work.
- After merging, you discover you broke a contract you didn't know existed.
- Three months later, you can't remember why you designed it this way.
- Your AI assistant has no anchor, so it generates code that meanders.

Benefits of writing one:
- **Forces clarity**: writing "why this design" exposes logical holes.
- **Anchor for AI collaboration**: an RFC is the strongest context you can hand an AI assistant. It dramatically lowers the chance of drift.
- **Future traceability**: `git blame` tells you *what* changed; an RFC tells you *why*.
- **Rubber-duck review**: even solo, writing the design out and reading it once beats turning it over in your head.

## 2. When an RFC Is Required

**Trigger conditions** (any one is enough):

- New module, new subsystem, new public API.
- Changing existing public API behavior or defaults.
- New cross-cutting logic in the middleware / interceptor / plugin class.
- Introducing a new dependency, framework, or toolchain.
- Non-trivial change spanning multiple files (≥5) or multiple modules.
- Data schema change, migration, or rollback strategy.
- Anything touching security, auth, authorization, or crypto.
- Performance optimization on a hot path — you must quantify the expected gain first.
- Any decision that will be "hard to reverse later."

**No RFC needed for**:
- Bug fixes (use `05-bug-fix-workflow.en.md`).
- Documentation-only updates.
- Adding tests.
- Fixing lint warnings.
- Localized refactors within a single file (no cross-module impact).
- Tuning config values.

## 3. Two Tiers of RFC

### Tier A: Lightweight RFC

For: single module, single concern, contained scope.

File location: `docs/rfc-<short-name>.md`

Contents (see `templates/rfc-template.md`):
1. **Problem**: what hurts today.
2. **Design principles**: 3-5 non-negotiable constraints.
3. **Approach**: API design + usage examples.
4. **Alternatives**: what else you considered and why you rejected it.
5. **Migration path**: impact on existing code/users.
6. **Design decisions table**: one-line rationale for each key choice.

Length: 100-300 lines.

### Tier B: Full Spec + Plan

For: cross-subsystem, far-reaching, requires phased rollout.

**Two files**:
- **Spec**: `docs/specs/YYYY-MM-DD-<name>-design.md` — answers "**why design it this way**".
- **Plan**: `docs/plans/YYYY-MM-DD-<name>.md` — answers "**in what order, which files**".

#### Spec contents

See `templates/design-spec-template.md`:

1. **Goal**: what to solve.
2. **Investigation findings**: the actual state of current code/data/logs (with evidence).
3. **Approach options**: at least three (A/B/C), trade-offs compared.
4. **Recommended approach**: which one and why.
5. **Risk assessment**: where it could fail.
6. **Verification**: how to prove the design is viable (minimal repro script, prototype code, data probe).
7. **Out of scope**: what is explicitly not in this design.

Length: 200-500 lines.

#### Plan contents

See the "Plan" section of `templates/rfc-template.md`:

1. **File structure table**: each file's operation type (Modify / Create / Delete) + responsibility.
2. **Task breakdown**: each Task is one group of changes, independently verifiable.
3. **Steps per Task**: checkbox list.
4. **Constraints per Task**: what cannot be touched, what must be preserved.

Length: 30-100 lines per Task.

## 4. RFC Workflow

```
Idea surfaces
  ↓
Draft RFC (Tier A or B)
  ↓
Self-review: pretend someone else wrote it, find holes
  ↓
(For teams) send to peers; for solo, ask the AI to play devil's advocate
  ↓
Freeze: write Status: Approved in the file header
  ↓
Enter implementation (04-feature-workflow.en.md)
  ↓
If implementation surfaces design issues → come back, update RFC, record why
  ↓
Implementation done → link the RFC from the PR
```

## 5. Letting the AI Review the RFC

Solo developer's "peer review" is the AI assistant. Have it play two roles:

### Role 1: Devil's Advocate

```
Read this RFC and answer as a hard-nosed senior engineer:
1. What assumptions are left unstated?
2. What edge cases are missing?
3. How does this design break at 10x traffic / 10x data volume?
4. I rejected alternative X — can you argue me into choosing it instead?
5. Summarize this RFC in one paragraph so we can confirm understanding.
```

### Role 2: Implementation Oracle

```
Assume we implement this RFC as written. List:
1. The 3 places most likely to have bugs.
2. The 3 places hardest to test.
3. The 3 decisions most likely to be reworked.
```

Fold the AI's feedback back into the RFC. **Leave a trace** (append a "Revision" section noting significant changes).

## 6. RFC-to-Code Consistency

- The RFC is *design intent*; the code is *implementation reality*.
- If you drift from the RFC during implementation → you **MUST** update the RFC. Don't let it become a lie.
- The `Status` field lifecycle: `Draft` → `Approved` → `Implemented` (or `Superseded by <new-rfc>`).
- Do not delete superseded RFCs — mark `Status: Superseded`, link to the new one, keep the history.

## 7. RFC Index

Maintain a table in `docs/README.md` or `docs/rfc-index.md`:

```markdown
| RFC | Status | Date | One-line purpose |
|-----|--------|------|------------------|
| rfc-create-agent-factory | Implemented | 2026-05-20 | Extract a pure-parameter SDK factory API |
| rfc-extract-shared-modules | Approved | 2026-06-01 | Split core into a publishable package |
| rfc-grep-glob-tools | Draft | 2026-06-15 | Add grep/glob tools to the sandbox |
```

Update the index the moment a new RFC is added. Don't batch.

## 8. When to Skip the RFC (With a Clear Conscience)

Urgent hotfix → fix first, backfill the RFC if architecture changed.
Exploratory prototype → mark `Status: Exploratory`, keep it out of the index, no harm in dropping it.

If you skip, write the reason in the PR description: "I didn't write an RFC because X. If we later discover Y, we'll add one."

---

**One-line summary**: an RFC is not paperwork; it is **the cheapest way to find design errors**. Thirty minutes writing an RFC before three hours of coding is the most leveraged time you'll spend.
