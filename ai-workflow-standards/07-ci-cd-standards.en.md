# 07 · CI/CD Standards

> CI is not "icing on the cake" — it's **the thing that lets you sleep at night**. Even solo, CI is the last automated quality gate standing between AI-generated code and main.
> Chinese counterpart: `07-ci-cd-standards.zh_CN.md`.

---

## 1. Mandatory CI Checks

Every PR must pass the following (any red → blocks merge):

### Backend (Python)

| Check | Tool | Command |
|-------|------|---------|
| Deps sync | uv | `uv sync --group dev` |
| Lint | ruff | `ruff check .` |
| Format check | ruff | `ruff format --check .` |
| Type check | mypy / pyright (optional) | `mypy src/` |
| Unit tests | pytest | `pytest --maxfail=1` |
| Coverage (optional) | pytest-cov | `pytest --cov=src --cov-fail-under=70` |

### Frontend (TypeScript)

| Check | Tool | Command |
|-------|------|---------|
| Deps install | pnpm | `pnpm install --frozen-lockfile` |
| Lint | ESLint | `pnpm lint` |
| Format check | Prettier | `pnpm format:check` |
| Type check | tsc | `pnpm typecheck` |
| Build | Next.js / Vite | `pnpm build` (needs env vars like `BETTER_AUTH_SECRET`) |
| Unit tests | Vitest / Jest | `pnpm test` |
| E2E (only when `frontend/` changes) | Playwright | `pnpm test-e2e` |

### Shared

| Check | Tool |
|-------|------|
| Secret scan | [gitleaks](https://github.com/gitleaks/gitleaks) |
| Dependency vulnerabilities | GitHub Dependabot / `pnpm audit` / `pip-audit` |
| Commit format | commitlint / commit-check |
| PR template completeness | GitHub-required sections |

## 2. Recommended GitHub Actions Workflows

### `.github/workflows/ci.yml` (main CI, runs on every PR)

```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv sync --group dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pytest --maxfail=1 -q

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v3
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
          cache-dependency-path: frontend/pnpm-lock.yaml
      - run: pnpm install --frozen-lockfile
      - run: pnpm lint
      - run: pnpm typecheck
      - run: pnpm build
        env:
          BETTER_AUTH_SECRET: ci-placeholder-secret
      - run: pnpm test

  e2e:
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    needs: [backend, frontend]
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v3
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
          cache-dependency-path: frontend/pnpm-lock.yaml
      - run: pnpm install --frozen-lockfile
      - run: pnpm exec playwright install --with-deps chromium
      - run: pnpm test-e2e

  secret-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### `.github/workflows/labeler.yml` (auto-labeling, optional)

Auto-apply `area:backend` / `area:frontend` / `area:docs` labels based on changed paths. Reference: `deer-flow/.github/labels.yml`.

### `.github/workflows/release.yml` (runs on release)

```yaml
name: Release
on:
  push:
    tags: ['v*']

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t myapp:${{ github.ref_name }} .
      - run: docker push myapp:${{ github.ref_name }}
      # ... push image / publish to npm / publish to PyPI
```

## 3. Branch Protection

GitHub settings: **Settings → Branches → Branch protection rules** → enable on `main`:

- [x] **Require a pull request before merging**
  - [x] Required approvals: 1 (you approve after self-review)
- [x] **Require status checks to pass before merging**
  - [x] Require branches to be up to date before merging
  - Required checks: `backend`, `frontend`, `secret-scan`
- [x] **Require conversation resolution before merging**
- [x] **Do not allow bypassing the above settings**
- [x] **Restrict who can push to matching branches** (no one pushes directly)

GitHub Free covers most of this for personal projects.

## 4. CI Speed Optimization

Slow CI kills AI-collaboration rhythm — pushing then waiting 20 minutes breaks flow.

### Caching

- Backend: `uv` caches natively; add `enable-cache: true` on `astral-sh/setup-uv@v3`.
- Frontend: `actions/setup-node@v4` with `cache: pnpm`.
- Playwright: cache `~/.cache/ms-playwright`.
- Docker: `docker/build-push-action@v5` with `cache-from` / `cache-to`.

### Parallelism

- Backend / frontend / secret-scan run as independent jobs in parallel.
- Tests can be sharded: `pytest --split`, `vitest --shard`.

### Conditional triggers

- E2E runs only when `frontend/` changes (`paths:` filter or `dorny/paths-filter`).
- Docs-only changes skip the test jobs.

### Timeouts

Set `timeout-minutes` on every job (10-15 recommended) so a hang doesn't burn runner minutes.

## 5. Handling CI Failures

See section 6 of `06-pr-workflow.en.md`. **Never disable a check.**

## 6. Reproduce CI Locally

CI commands should be 1:1 reproducible locally:

```bash
# Backend CI equivalent
cd backend
uv sync --group dev
uv run ruff check .
uv run ruff format --check .
uv run pytest --maxfail=1 -q

# Frontend CI equivalent
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
BETTER_AUTH_SECRET=local-dev-secret pnpm build
pnpm test
```

Wrap this in a `make ci-local` target and run it before pushing. Avoids "passes locally, fails in CI" embarrassment.

## 7. Deployment

### Staging

- Every merge to main → auto-deploy to staging.
- Staging is always reachable and testable.

### Production

- Trigger via tag: `git tag v1.2.3 && git push origin v1.2.3`.
- Production deploy requires a staging validation record.
- Rollback: keep the last N image/build artifacts; one-click revert.

### Blue-green / canary (optional)

- High-risk changes use canary (10% → 50% → 100%).
- Pair with feature flags for percentage-based rollout.

## 8. Observability (production)

After deploy you must be able to see:

- **Logs**: structured JSON, correlated by request_id / trace_id.
- **Metrics**: QPS, latency percentiles, error rate, resource usage.
- **Alerts**: error-rate spike, latency spike, availability drop → immediate notification.
- **Tracing**: OpenTelemetry / LangSmith / Langfuse (for AI apps).

## 9. CI Security

- **Never hardcode secrets in workflows**: use GitHub Actions secrets.
- **Pin third-party Action versions**: `uses: actions/checkout@v4` (never `@main` or `@master`).
- **Least-privilege tokens**: `GITHUB_TOKEN` defaults to read-only; grant write per job as needed.
- **Disable secrets on fork PRs**: `if: github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository`.

## 10. Discipline Around CI Config Itself

- CI config changes go through PRs (never push directly to main).
- Adding a job → sync the Validation section example in `06-pr-workflow.en.md`.
- Removing a job → the PR description must explain why the check is no longer needed.

---

**One-line summary**: CI is **automated self-review** — treat it as a senior engineer who never sleeps, never cuts corners, never gets emotional. Configure it, trust it, never bypass it.
