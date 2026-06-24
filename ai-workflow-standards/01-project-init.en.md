# 01 · Project Initialization Checklist

> Day-one bootstrap checklist for a new project. Tick every item — this is what makes the rest of the workflow enforceable.
> Chinese counterpart: `01-project-init.zh_CN.md`.
> Target: full-stack web (Python backend + TS frontend), solo development (you + AI assistant).

---

## 1. Repository and Version Control

- [ ] `git init`, confirm the default branch is `main`.
- [ ] Write `.gitignore`. Cover at minimum: `.env`, `config.yaml`, `extensions_config.json`, `.venv/`, `node_modules/`, `.next/`, `dist/`, `build/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, IDE folders, OS files (`.DS_Store`, `Thumbs.db`).
- [ ] Pick a license (MIT or Apache-2.0 for personal projects). Commit `LICENSE`.
- [ ] Write a minimal `README.md` (project name, one-line pitch, install, run).
- [ ] Add `.gitattributes` (line endings, binary markings) — essential for cross-platform.

## 2. Toolchain

### Backend (Python)

- [ ] Python 3.12+, managed with [`uv`](https://docs.astral.sh/uv/) for deps and venv.
- [ ] `backend/pyproject.toml`: declare `requires-python = ">=3.12"`, runtime deps, dev deps (pytest, ruff).
- [ ] `backend/ruff.toml`: line length, target-version, rule sets.
- [ ] `backend/Makefile`: `install` / `dev` / `lint` / `format` / `test` targets.
- [ ] `backend/.python-version` to pin the version (used by uv).

### Frontend (TypeScript)

- [ ] Node.js 22+, use `pnpm` (performance + strict deps).
- [ ] `frontend/package.json`: declare `engines` and `packageManager` (e.g. `pnpm@10.26.2`).
- [ ] `frontend/tsconfig.json`: `strict: true`, `noUncheckedIndexedAccess: true`.
- [ ] `frontend/eslint.config.js` (flat config) + `frontend/.prettierrc`.
- [ ] `frontend/Makefile` or npm scripts: `lint` / `format` / `typecheck` / `build` / `test` / `test-e2e`.

### Shared

- [ ] Docker (for sandbox, production, reproducible environments).
- [ ] `make check` verifies all tools are installed.
- [ ] `make install` installs every dependency in one shot.

## 3. Directory Layout

Recommended structure (adapt as needed):

```
my-project/
├── Makefile                    # Root orchestration: check / install / dev / stop
├── README.md
├── LICENSE
├── .gitignore
├── .gitattributes
├── config.example.yaml         # Config template (committed)
├── config.yaml                 # Actual config (gitignored)
├── .env.example                # Env var template (committed)
├── .env                        # Actual values (gitignored)
├── docker/
│   ├── Dockerfile
│   ├── docker-compose-dev.yaml
│   └── nginx/
├── backend/
│   ├── Makefile
│   ├── pyproject.toml
│   ├── ruff.toml
│   ├── langgraph.json          # if using LangGraph
│   ├── src/                    # or packages/...
│   ├── tests/
│   └── docs/
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── eslint.config.js
│   ├── src/
│   └── tests/
├── .github/
│   ├── workflows/              # CI
│   ├── ISSUE_TEMPLATE/
│   └── pull_request_template.md
├── docs/
│   ├── ARCHITECTURE.md
│   └── superpowers/
│       ├── specs/
│       └── plans/
└── CLAUDE.md                   # Project-level system prompt for AI assistants
```

## 4. CI Skeleton

`.github/workflows/ci.yml` runs at minimum (see `07-ci-cd-standards.en.md`):

- Backend: `uv sync --group dev` → `make lint` → `make test`
- Frontend: `pnpm install --frozen-lockfile` → `pnpm lint` → `pnpm typecheck` → `pnpm build` → `pnpm test`
- E2E: triggered when `frontend/` changes
- Secret scan: `gitleaks` or equivalent

PRs MUST pass CI before merge (enforced by branch protection).

## 5. Template Files

Copy from `ai-workflow-standards/templates/`:

- `.github/pull_request_template.md`
- `.github/ISSUE_TEMPLATE/bug-report.md`
- `docs/rfc-template.md` (lightweight RFC starting point)
- `docs/design-spec-template.md` (full design doc starting point)

## 6. Pre-commit Hooks

`make install` should also install pre-commit hooks that run at least:

- Backend: `ruff check --fix` + `ruff format`
- Frontend: `prettier --write` + `eslint --fix`
- Shared: reject large files, scan for secret fingerprints

Use the [`pre-commit`](https://pre-commit.com/) framework.

## 7. Config File Strategy

- Commit **templates**: `config.example.yaml`, `.env.example`, `extensions_config.example.json`.
- gitignore **actuals**: `config.yaml`, `.env`, `extensions_config.json`.
- Reference env vars with `$` prefix or `${VAR}` so secrets never get hardcoded.
- Add a `config_version` field; bump it whenever the schema changes.

## 8. Documentation Skeleton

- [ ] `README.md`: project pitch, quick start, doc navigation.
- [ ] `ARCHITECTURE.md`: high-level architecture diagram, module responsibilities, data flow.
- [ ] `CLAUDE.md`: deep context for AI assistants (architecture, commands, conventions, gotchas).
- [ ] `docs/CONTRIBUTING.md`: workflow summary, links to this standards suite.
- [ ] `docs/CHANGELOG.md`: release history (see `08-documentation-policy.en.md`).

## 9. Branch Protection (even on a personal repo)

`main` should at minimum:

- [ ] Forbid direct push (PRs only).
- [ ] Require CI to pass.
- [ ] Require at least 1 approval (self-approval counts — it forces a real self-review).
- [ ] Forbid force push.

GitHub settings: Settings → Branches → Branch protection rules.

## 10. Done Check

Run the full flow once to confirm everything is wired up:

```bash
make check          # tools present
make install        # deps installed
make dev            # services come up
make lint           # clean
make test           # green
git commit --allow-empty -m "chore: verify hooks"   # hook fires
```

All green → project init complete. Start the first feature (`04-feature-workflow.en.md`).

---

**Principle**: every init step exists to make the standard workflow run itself afterward. Skip work on day one, pay it back on every line of code thereafter.
