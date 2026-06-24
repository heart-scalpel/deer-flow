# 04 · Feature Workflow End-to-End

> From an idea to landing on `main` — the full chain.
> Chinese counterpart: `04-feature-workflow.zh_CN.md`.
> Upstream: `02-development-workflow.en.md`, `03-rfc-process.en.md`, `06-pr-workflow.en.md`.

---

## 0. Decision Tree

```
New idea / new requirement
  ↓
Is it a bug?
  ├─ yes → use 05-bug-fix-workflow.en.md
  └─ no  ↓
Does it trigger an RFC condition? (section 2 of doc 03)
  ├─ yes → write RFC (Tier A or B)
  └─ no  → enter the dev loop directly
  ↓
Dev loop: 02-development-workflow.en.md
  ↓
PR: 06-pr-workflow.en.md
  ↓
Merge
```

## 1. Idea Phase

**Output**: a single paragraph that clearly states "what, why, for whom."

Template:

```markdown
**What**: one-line feature description.
**Why**: current pain / user request / business driver.
**For whom**: target user or caller.
**Done looks like**: observable success criteria (what the user can see / do).
**Out of scope**: what is explicitly not in this feature.
```

Decide:
- Can't fill this in → the idea isn't ready. **Think more, don't start coding.**
- Filled in cleanly → proceed.

## 2. RFC Phase (if a trigger condition fires)

Pick a tier per `03-rfc-process.en.md`:

| Change type | Recommended tier |
|-------------|------------------|
| New module within an existing subsystem, API tweak | Tier A (lightweight RFC) |
| Cross-subsystem, new middleware, behavior default change | Tier B (full Spec + Plan) |
| Urgent hotfix | Skip, backfill later |
| Exploratory prototype | Tier A, `Status: Exploratory` |

**Done means**: the RFC file exists, the header says `Status: Approved`, the AI has played devil's advocate, revisions are recorded.

## 3. Task Breakdown Phase

Translate the RFC's Plan section into a task list. Each task must be:

- **Independently verifiable**: completion shows up as a green test or an observable outcome.
- **Independently committable**: granularity matches one Conventional Commit.
- **Independently revertable**: doesn't break other tasks' results.
- **Estimated**: 1-4 hours is ideal; anything over a day gets split.

Tools:
- AI assistant: record tasks via `TaskCreate`, walk them through `in_progress` → `completed`.
- Project level: maintain a checkbox list in the RFC's Plan section for complex features (mirror the `docs/superpowers/plans/` style).

## 4. Implementation Phase (per task)

Follow the TDD loop (section 2 of `02-development-workflow.en.md`):

```
1. Branch off (if this is the first task)
   git checkout -b feature/<name>

2. For each task:
   a. Write test → red
   b. Write implementation → green
   c. Refactor → stay green
   d. Run local validation gates (lint + test + typecheck + build)
   e. git commit (Conventional Commits)
   f. Mark task completed

3. All tasks done → enter PR phase
```

### Discipline during implementation

- **Commit the moment a task completes.** Don't stockpile.
- **Record RFC drift immediately**: if you find the design is wrong → pause, update the RFC, add a Revision note, then continue.
- **Newly discovered bug**: open a separate `fix/` branch. Don't piggyback it into the feature branch (mixing makes the PR unreviewable).
- **Refactor temptation**: notice cleanup opportunities → record them, do them on a separate `refactor/` branch later. **Don't piggyback.**

## 5. Doc Sync Phase (continuous during implementation)

Update docs as you write code (see `08-documentation-policy.en.md`):

- New public API → update `docs/API.md` or `README.md` in the same change.
- New config field → update `config.example.yaml` and the config doc.
- Default behavior change → update `README.md`.
- Architecture change → update `ARCHITECTURE.md` and `CLAUDE.md`.

**Rule**: docs and code land in the same commit. "Code first, docs later" → the docs never get written.

## 6. Self-Review Phase (before push)

Pretend you're reviewing someone else's PR:

- [ ] Full local validation gate run.
- [ ] `git diff main...HEAD` read in full.
- [ ] For every file: "If this file were deleted, could I explain why we needed it?"
- [ ] For every new code block: "Will I be able to explain what this does in three months?"
- [ ] Test coverage: at least one happy path + one failure path per public function.
- [ ] No unreviewed AI-generated code (section 2.1 of `00-operating-principles.en.md`).
- [ ] All docs synced.

Anything fails → back to the implementation phase.

## 7. PR Phase

Open per `06-pr-workflow.en.md`. Key points:

- Link the RFC (if any) in the PR description.
- Check every applicable Surface area box.
- Fill the Validation section with the commands you actually ran.
- Fill the AI assistance section: which tool, how used, human-responsibility confirmation.
- Push only after self-review passes.

## 8. After Merge

- [ ] Delete the feature branch (local and remote).
- [ ] If a tracking Issue exists, confirm the PR's `Closes #N` closed it.
- [ ] If the RFC `Status` is still `Approved`, flip it to `Implemented`.
- [ ] If user-visible, update `CHANGELOG.md`.
- [ ] If it's a major feature, add a line in the README.

## 9. Post-Mortem After a Week

One week after merge, look back:

- Is the feature actually being used in practice? (If not, the "for whom" question in the Idea phase probably wasn't answered clearly.)
- Did tests catch regressions? (If not, the red tests in TDD probably weren't strong enough.)
- Did anyone ask questions the docs should have answered? (If yes, the doc-sync phase cut corners.)

Fold the conclusions into the next feature's Idea phase.

---

**One-line summary**: Idea → RFC (if triggered) → Task breakdown → TDD implementation (with continuous doc sync) → Self-review → PR → Merge → Look back. Every phase has an exit criterion; **do not advance until it's met**.
