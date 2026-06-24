# 02 · Daily Development Loop

> The default rhythm for everyday coding. Every PR runs through this loop.
> Chinese counterpart: `02-development-workflow.zh_CN.md`.
> Upstream principles: `00-operating-principles.en.md`.

---

## 1. Sync and Branch

```bash
git checkout main
git pull --ff-only origin main
git checkout -b <type>/<short-name>
```

### Branch naming

| Type | Prefix | Example |
|------|--------|---------|
| New feature | `feature/` | `feature/add-minimax-provider` |
| Bug fix | `fix/` | `fix/sandbox-timeout` |
| Docs | `docs/` | `docs/update-readme` |
| Refactor | `refactor/` | `refactor/config-system` |
| Tests | `test/` | `test/cover-memory-queue` |
| Build/config | `chore/` | `chore/bump-deps` |
| Performance | `perf/` | `perf/index-message-store` |

**Rules**: kebab-case, ≤50 chars, semantically clear, no dates or author names (git already records those).

## 2. TDD Loop: Red → Green → Refactor

For every unit of functionality:

1. **Red**: write a test, run it, watch it fail (and confirm it fails on `main` too).
2. **Green**: write the minimal implementation that makes the test pass.
3. **Refactor**: clean up the code, keep the test green.

```bash
# Backend
cd backend && PYTHONPATH=. uv run pytest tests/test_<feature>.py -v

# Frontend
cd frontend && pnpm test -- <pattern>
```

**Do not** write the implementation first and backfill tests later — those tests only verify what you already wrote; they never catch design mistakes.

## 3. Commit Convention (Conventional Commits)

### Format

```
<type>(<scope>): <one-line subject>

<!-- optional body -->
- Bullet 1
- Bullet 2

<!-- optional footer -->
Closes #123
```

### Allowed types

| type | Use for |
|------|---------|
| `feat` | New user-visible feature |
| `fix` | Bug fix |
| `docs` | Documentation |
| `refactor` | Refactor (no external behavior change) |
| `test` | Tests |
| `chore` | Build, deps, CI, config |
| `perf` | Performance optimization |
| `style` | Formatting (usually auto-generated; do not commit separately) |
| `ci` | CI configuration |
| `build` | Build system / dependencies |

### Subject line

- **Imperative mood**: "add support for X", not "added support for X".
- ≤70 characters (GitHub's truncation threshold).
- No trailing period.
- No emoji (unless the project convention requires it).

### Examples

```
feat(models): add MiniMax generation provider

- Register MiniMax provider in ModelFactory
- Declare thinking and vision capabilities
- Add unit tests covering reflection-based loading

Closes #421
```

```
fix(sandbox): resolve timeout on cold container start

The acquire path was polling at 1s intervals but the readiness
probe only flips after 2s on cold boots. Poll interval is now
configurable, default 500ms.
```

### Anti-examples

- ❌ `update code`
- ❌ `fix bug`
- ❌ `wip`
- ❌ `asdf`
- ❌ Subject longer than 70 chars that GitHub will truncate

## 4. Commit Granularity

**One commit, one concern.**

- Adding a feature + tweaking lint config → two commits.
- Fixing a bug + opportunistic refactor → two commits.
- Multiple related changes for the same feature across files → may be one commit.

Rule of thumb: **can this commit be reverted in isolation without breaking others?** If not, split it.

## 5. Local Validation Gates (run before push)

### Backend

```bash
cd backend
make format   # ruff format (auto)
make lint     # ruff check .
make test     # uv run pytest
```

### Frontend

```bash
cd frontend
pnpm format:write          # Prettier
pnpm lint                  # ESLint
pnpm typecheck             # tsc --noEmit
BETTER_AUTH_SECRET=local-dev-secret pnpm build   # production build
pnpm test                  # unit tests
```

For UI changes also:

```bash
cd frontend && make test-e2e   # requires Chromium
```

### Universal

- [ ] No leftover `console.log` / `print` (unless intentional, with a comment).
- [ ] No large blocks of commented-out dead code.
- [ ] No TODOs without a linked issue.
- [ ] No undeclared new dependencies.
- [ ] No `.env` / `config.yaml` staged.

## 6. Never Commit

- ❌ `.env`, `config.yaml`, `extensions_config.json`, credentials.
- ❌ `.venv/`, `node_modules/`, `__pycache__/`, `.next/`, `dist/`.
- ❌ Large binaries (images, video, datasets) — use LFS or external storage.
- ❌ Personal IDE configs (`.idea/workspace.xml`, etc.).
- ❌ OS files (`.DS_Store`, `Thumbs.db`).

`git status` should show a clean working tree before you stage.

## 7. Staging Strategy

- **Prefer `git add <specific file>`** over `git add .` / `git add -A` — avoids accidentally including unreviewed files.
- Use `git add -p` to stage in chunks and split one set of edits into multiple semantic commits.
- Run `git diff --cached` to review what's staged before committing.

## 8. Push Cadence

- **Push early, push often** — if you lose local work, no one can recover it.
- Push after every semantic unit (one commit) is fine.
- Do not stockpile a week of commits before pushing.

```bash
git push -u origin <branch-name>
```

## 9. Keeping Up with `main`

When `main` advances:

```bash
git fetch origin
git rebase origin/main   # prefer rebase for a linear history
```

After resolving conflicts:

```bash
git add <resolved-files>
git rebase --continue
# Do NOT git rebase --skip unless you understand exactly why
# NEVER --no-verify
```

If the feature branch has already been pushed and has collaborators (even you on another machine), use merge instead of rebase to avoid rewriting history.

## 10. Done → Enter the PR Workflow

Local validation green, branch pushed → proceed to `06-pr-workflow.en.md`.

---

**One-line summary**: keep branch names standard, write clear commits, never skip TDD, run local validation before every push — do those four and the PR phase becomes pure self-review.
