# 07 · CI/CD 标准

> CI 不是"锦上添花"，是**让你晚上能睡着的东西**。即使一个人开发，CI 是 AI 生成代码的最后一道自动化质量门。
> 配套英文版：`07-ci-cd-standards.en.md`。

---

## 1. CI 必查项

每个 PR 必须跑过以下检查（任意一项红 → 阻止合并）：

### 后端（Python）

| 检查 | 工具 | 命令 |
|------|------|------|
| 依赖同步 | uv | `uv sync --group dev` |
| Lint | ruff | `ruff check .` |
| Format check | ruff | `ruff format --check .` |
| Type check | mypy / pyright（可选） | `mypy src/` |
| 单元测试 | pytest | `pytest --maxfail=1` |
| 覆盖率（可选） | pytest-cov | `pytest --cov=src --cov-fail-under=70` |

### 前端（TypeScript）

| 检查 | 工具 | 命令 |
|------|------|------|
| 依赖安装 | pnpm | `pnpm install --frozen-lockfile` |
| Lint | ESLint | `pnpm lint` |
| Format check | Prettier | `pnpm format:check` |
| Type check | tsc | `pnpm typecheck` |
| 构建 | Next.js / Vite | `pnpm build`（需要 `BETTER_AUTH_SECRET` 等环境变量） |
| 单元测试 | Vitest / Jest | `pnpm test` |
| E2E（仅 frontend/ 改动时） | Playwright | `pnpm test-e2e` |

### 通用

| 检查 | 工具 |
|------|------|
| Secret scan | [gitleaks](https://github.com/gitleaks/gitleaks) |
| 依赖漏洞 | GitHub Dependabot / `pnpm audit` / `pip-audit` |
| 提交规范 | commitlint / commit-check |
| PR 模板完整性 | GitHub-required sections |

## 2. 推荐的 GitHub Actions 工作流

### `.github/workflows/ci.yml`（主 CI，每个 PR 跑）

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

### `.github/workflows/labeler.yml`（自动打标签，可选）

按改动路径自动打 `area:backend` / `area:frontend` / `area:docs` 等标签。参考 `deer-flow/.github/labels.yml`。

### `.github/workflows/release.yml`（发版时跑）

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
      # ... 推镜像 / 发布 npm / 发布 PyPI
```

## 3. 分支保护

GitHub 设置：**Settings → Branches → Branch protection rules** → 对 `main` 启用：

- [x] **Require a pull request before merging**
  - [x] Require approvals: 1（自审通过后自己 approve）
- [x] **Require status checks to pass before merging**
  - [x] Require branches to be up to date before merging
  - 必选 checks: `backend`, `frontend`, `secret-scan`
- [x] **Require conversation resolution before merging**
- [x] **Do not allow bypassing the above settings**
- [x] **Restrict who can push to matching branches**（不允许任何人直接 push）

个人项目用 GitHub Free 即可启用大部分保护。

## 4. CI 速度优化

慢 CI 是 AI 协作的杀手——每次 push 等 20 分钟，节奏全断。

### 缓存

- 后端：`uv` 自带缓存，加 `astral-sh/setup-uv@v3` 的 `enable-cache: true`。
- 前端：`actions/setup-node@v4` 的 `cache: pnpm`。
- Playwright：缓存 `~/.cache/ms-playwright`。
- Docker：`docker/build-push-action@v5` 的 `cache-from` / `cache-to`。

### 并行

- 后端 / 前端 / secret-scan 并行跑（独立的 job）。
- 测试本身可拆分：`pytest --split`、`vitest --shard`。

### 按需触发

- E2E 只在 `frontend/` 改动时跑（`paths:` 过滤或 `dorny/paths-filter` action）。
- 文档变更跳过测试 job。

### 超时

每个 job 设 `timeout-minutes`（推荐 10-15 分钟），避免挂死占用 runner。

## 5. CI 失败的处理

参见 `06-pr-workflow.zh_CN.md` 第 6 节。**永远不要 disable 检查**。

## 6. 本地复现 CI

CI 的命令应该在本地能 1:1 复现：

```bash
# 后端 CI 等价
cd backend
uv sync --group dev
uv run ruff check .
uv run ruff format --check .
uv run pytest --maxfail=1 -q

# 前端 CI 等价
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
BETTER_AUTH_SECRET=local-dev-secret pnpm build
pnpm test
```

把这套封装到 `make ci-local` 命令里，push 前跑一遍，避免"本地过、CI 红"的尴尬。

## 7. 部署

### Staging

- 每个 PR 合并到 main → 自动部署到 staging。
- staging 永远可访问、可测。

### Production

- 通过 tag 触发：`git tag v1.2.3 && git push origin v1.2.3`。
- Production 部署前必须有 staging 验证记录。
- 紧急回滚：保留前 N 个版本的镜像/构建产物，一键回滚。

### 蓝绿 / 灰度（可选）

- 高风险改动用灰度（10% → 50% → 100%）。
- 配合 feature flag，按用户百分比分批启用。

## 8. 监控（生产）

部署后必须能观测：

- **日志**：结构化 JSON，按 request_id / trace_id 关联。
- **指标**：QPS、延迟分位数、错误率、资源使用。
- **告警**：错误率突增、延迟突增、可用性下降 → 立即通知。
- **链路追踪**：OpenTelemetry / LangSmith / Langfuse（AI 应用）。

## 9. CI 安全

- **不要在 workflow 里硬编码 secret**：用 GitHub Actions secrets。
- **第三方 Action 锁版本**：`uses: actions/checkout@v4`（不要用 `@main` 或 `@master`）。
- **最小权限 token**：`GITHUB_TOKEN` 默认只读，写权限按 job 单独赋。
- **PR 来自 fork 时禁用 secret**：`if: github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository`。

## 10. CI 配置本身的纪律

- CI 配置改动也要走 PR（不能直接 push 到 main）。
- 加新 job → 同步更新 `06-pr-workflow.zh_CN.md` 的 Validation 节示例。
- 删 job → 必须在 PR 描述中说明为什么不需要这个检查了。

---

**一句话总结**：CI 是**自动化的 self-review**——把它当成不睡觉、不偷懒、不带情绪的资深工程师。配置它、信任它、永远不要绕过它。
