# 06 · PR Workflow

> **Even when working alone, use PRs.** A PR is not a "waiting for someone to review" checkpoint — it is a tool that **forces you to review your own change from a third-person perspective**.
> Chinese counterpart: `06-pr-workflow.zh_CN.md`.
> PR template: `templates/PULL_REQUEST_TEMPLATE.md`.

---

## 1. Why PRs Even When Solo

Cost of skipping PRs:
- Direct push to main → no one (including you) systematically reviewed it → bugs land on main before anyone notices.
- Changes scattered across commits → three months later you can't reconstruct "why this change."
- No validation record → when CI breaks one day, you can't trace which change caused it.
- AI-generated code with no self-review → "AI wrote it, I merged it."

Benefits of PRs:
- **Forces self-review**: writing the PR description + reading the diff in full = one pass of stranger-perspective review.
- **Traceable**: the PR links the issue, RFC, validation commands, and AI tools — a complete decision chain.
- **CI gate**: CI must be green before merge; catches regressions your local run missed.
- **Rollback anchor**: each PR is a revert unit, cleaner than reverting commit-by-commit.

## 2. Required PR Sections

The PR description (per `templates/PULL_REQUEST_TEMPLATE.md`) must contain:

| Section | Required when | Purpose |
|---------|---------------|---------|
| **Issue link** | When an issue exists | `Fixes #N` / `Closes #N` / `Ref #N` |
| **Why** | Always | The trigger + the pain addressed |
| **What changed** | Always | User-perspective change description, not a diff list |
| **Surface area** | Always | Check every touched area; scopes the review |
| **Bug fix verification** | Bug fixes only (delete otherwise) | Test path + main-red/branch-green |
| **Validation** | Always | Commands you actually ran |
| **AI assistance** | **Always** | Tools used, how used, human-responsibility confirmation |
| **Screenshots / Recording** | When Frontend UI is touched | Entry-point screenshots, before/after ideally |
| **RFC / Spec link** | When a design doc exists | Lets the reviewer follow the thread |

## 3. Open the PR with `gh`

```bash
gh pr create --title "<type>(<scope>): <subject ≤70 chars>" --body "$(cat <<'EOF'
Fixes #123

## Why
<!-- Why open this PR? Trigger + pain addressed. For non-trivial features, have an RFC first. -->

## What changed
<!-- Describe the change from the user / caller perspective. -->

## Surface area
- [ ] Frontend UI
- [ ] Backend API
- [ ] Agents / LangGraph
- [ ] Sandbox
- [ ] Skills
- [ ] Dependencies
- [ ] Default behavior change
- [ ] Docs / tests / CI only

## Bug fix verification
<!-- Bug fixes only; otherwise delete. Test path + red on main + green on branch. -->

## Validation
<!-- Commands you actually ran. -->
cd backend && make lint && make test
cd frontend && pnpm lint && pnpm typecheck && pnpm build && pnpm test

## AI assistance
**Tool(s) used:** <!-- Claude Code / Cursor / Copilot / none -->
**How you used it:** <!-- How you used it -->
- [ ] I have read and understand every line of this change and take responsibility for it — it is not unreviewed AI output.
EOF
)"
```

## 4. Self-Review Checklist (before merge)

**All items must pass** before you merge:

### Diff review
- [ ] Read `git diff main...HEAD` in full.
- [ ] Every commit is atomic and follows Conventional Commits.
- [ ] No leftover `console.log` / `print` / debug code.
- [ ] No commented-out dead code.
- [ ] No TODOs without a linked issue.

### Tests
- [ ] New features / bug fixes have corresponding tests.
- [ ] Tests cover happy path + failure path + boundary.
- [ ] CI is green on the PR.
- [ ] Full local lint + test run.

### Security
- [ ] No committed `.env` / secrets / credentials.
- [ ] No known-vulnerable dependencies introduced (CI dependency scan passes).
- [ ] No hardcoded keys, tokens, passwords.
- [ ] SQL / command injection, XSS, CSRF reviewed (if the change touches them).

### Docs
- [ ] User-visible change → README updated.
- [ ] Architecture change → ARCHITECTURE.md / CLAUDE.md updated.
- [ ] API change → API docs updated.
- [ ] Config field change → config.example.yaml updated.

### PR description
- [ ] Why section answers "why this PR exists."
- [ ] What changed section uses user perspective.
- [ ] Surface area fully checked.
- [ ] Validation section lists actual commands.
- [ ] AI assistance section filled honestly.
- [ ] Linked Issue / RFC (if any).

### Size
- [ ] PR diff < 300 lines (ideal).
- [ ] PR diff > 700 lines → strong justification written in Why.

## 5. Review Criteria

When you self-review, ask:

1. **Readable**: will I be able to understand why each file changed in three months?
2. **Reversible**: if something goes wrong, can it be cleanly reverted?
3. **Breaking**: what default behavior changed? Who is affected?
4. **Tests**: do the tests actually cover the root cause, or only the symptom?
5. **AI traces**: is there AI-generated code I haven't fully read?
6. **Scope**: does the PR do exactly one thing? Is anything piggybacked?

Any uncertain answer → go back and fix.

## 6. Handling CI Failures

CI red → **don't retry hoping it goes away**:

1. Read the CI log; locate the failure.
2. Classify:
   - **Lint / format failure** → run `make format` / `pnpm format:write` locally, commit the fix.
   - **Test failure** → real bug or test itself broken? Fix the root cause.
   - **Build failure** → type error, missing dep, config issue? Fix it.
   - **Flaky test** → don't retry-mask it; flag it, fix it separately.
3. Push the fix → wait for CI to rerun.
4. **Never `--no-verify` to skip hooks or disable CI checks.**

## 7. Merge Strategy

For a personal project, **squash merge** is recommended:

- Multiple WIP commits collapse into one clean Conventional Commit.
- Linear main history, easy to read.
- GitHub settings: Settings → General → Pull Requests → Allow squash merging (check) / Allow merge commits (uncheck) / Allow rebase merging (optional).

After merge:
- Auto-delete the head branch (toggle in GitHub settings).
- `git checkout main && git pull --ff-only origin main && git branch -d <local-branch>`.

## 8. PR Cadence

- **One PR, one concern**: mixed-purpose PRs are unreviewable and un-revertable.
- **Open early**: even WIP — mark `[WIP]` or set as draft, get CI running.
- **Small increments**: reviewers skim large PRs; they scrutinize small ones.
- **Respond to feedback**: even self-review feedback — fix issues immediately, don't defer.

## 9. Handling Conflicts

```bash
git fetch origin
git rebase origin/main   # prefer rebase
# resolve conflicts
git add <resolved>
git rebase --continue
git push --force-with-lease   # IMPORTANT: --force-with-lease, not --force
```

`--force-with-lease` is safer than `--force`: it refuses if the remote has new commits from someone else, preventing accidental overwrites.

## 10. After Merge

- [ ] Confirm CI is green on main too.
- [ ] Delete the feature branch (local and remote).
- [ ] If linked Issue, confirm `Fixes` closed it.
- [ ] If user-visible, update `CHANGELOG.md`.
- [ ] If major feature, consider cutting a release tag.
- [ ] If an RFC exists, flip `Status: Approved` to `Status: Implemented`.

---

**One-line summary**: a PR is not a gate for others — it's a **tool that forces you to review yourself**. Self-review checklist fully passed + CI fully green + description fully filled — all three are mandatory.
