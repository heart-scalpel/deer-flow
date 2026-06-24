# 01 · 项目初始化清单

> 新项目第一天的 bootstrap 清单。逐项过完，后续开发流程才有抓手。
> 配套英文版：`01-project-init.en.md`。
> 适用：全栈 Web（Python 后端 + TS 前端），独立开发（你 + AI 助手）。

---

## 1. 仓库与版本控制

- [ ] `git init`，确认默认分支是 `main`。
- [ ] 写 `.gitignore`，至少覆盖：`.env`、`config.yaml`、`extensions_config.json`、`.venv/`、`node_modules/`、`.next/`、`dist/`、`build/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、IDE 目录、OS 文件（`.DS_Store`、`Thumbs.db`）。
- [ ] 选 License（个人项目通常 MIT 或 Apache-2.0），写 `LICENSE`。
- [ ] 写最小可用的 `README.md`（项目名、一句话定位、安装、运行）。
- [ ] 配 `.gitattributes`（行尾、二进制标记），跨平台协作必备。

## 2. 工具链

### 后端（Python）

- [ ] Python 3.12+，用 [`uv`](https://docs.astral.sh/uv/) 管理依赖和虚拟环境。
- [ ] `backend/pyproject.toml`：声明 `requires-python = ">=3.12"`、依赖、dev 依赖（pytest、ruff）。
- [ ] `backend/ruff.toml`：行宽、target-version、启用规则集。
- [ ] `backend/Makefile`：`install` / `dev` / `lint` / `format` / `test` 目标。
- [ ] `backend/.python-version` 固定版本（uv 用）。

### 前端（TypeScript）

- [ ] Node.js 22+，用 `pnpm`（性能 + 严格依赖）。
- [ ] `frontend/package.json`：声明 `engines`、`packageManager` 字段（如 `pnpm@10.26.2`）。
- [ ] `frontend/tsconfig.json`：`strict: true`、`noUncheckedIndexedAccess: true`。
- [ ] `frontend/eslint.config.js`（flat config）+ `frontend/.prettierrc`。
- [ ] `frontend/Makefile` 或 npm scripts：`lint` / `format` / `typecheck` / `build` / `test` / `test-e2e`。

### 通用

- [ ] Docker（用于沙箱、生产部署、可重现环境）。
- [ ] `make check` 命令验证所有工具就绪。
- [ ] `make install` 一键装全部依赖。

## 3. 目录结构

推荐布局（按需调整）：

```
my-project/
├── Makefile                    # 根级编排：check / install / dev / stop
├── README.md
├── LICENSE
├── .gitignore
├── .gitattributes
├── config.example.yaml         # 配置模板（commit）
├── config.yaml                 # 实际配置（gitignored）
├── .env.example                # 环境变量模板（commit）
├── .env                        # 实际值（gitignored）
├── docker/
│   ├── Dockerfile
│   ├── docker-compose-dev.yaml
│   └── nginx/
├── backend/
│   ├── Makefile
│   ├── pyproject.toml
│   ├── ruff.toml
│   ├── langgraph.json          # 如果用 LangGraph
│   ├── src/                    # 或 packages/...
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
└── CLAUDE.md                   # AI 助手的项目级系统提示
```

## 4. CI 骨架

`.github/workflows/ci.yml` 至少跑（详见 `07-ci-cd-standards.zh_CN.md`）：

- 后端：`uv sync --group dev` → `make lint` → `make test`
- 前端：`pnpm install --frozen-lockfile` → `pnpm lint` → `pnpm typecheck` → `pnpm build` → `pnpm test`
- E2E：`frontend/` 改动时触发
- Secret scan：`gitleaks` 或同类工具

PR 必须 CI 全绿才能合（branch protection 强制）。

## 5. 模板文件

从 `ai-workflow-standards/templates/` 拷贝：

- `.github/pull_request_template.md`
- `.github/ISSUE_TEMPLATE/bug-report.md`
- `docs/rfc-template.md`（轻量 RFC 起点）
- `docs/design-spec-template.md`（完整设计文档起点）

## 6. Pre-commit Hooks

`make install` 应该顺带装好 pre-commit，至少跑：

- 后端：`ruff check --fix` + `ruff format`
- 前端：`prettier --write` + `eslint --fix`
- 通用：禁止提交大文件、密钥指纹扫描

参考 [`pre-commit`](https://pre-commit.com/) 框架。

## 7. 配置文件策略

- 提交**模板**：`config.example.yaml`、`.env.example`、`extensions_config.example.json`。
- gitignore **实际值**：`config.yaml`、`.env`、`extensions_config.json`。
- 配置项以 `$` 前缀或 `${VAR}` 引用环境变量，避免硬编码密钥。
- 加 `config_version` 字段，schema 变更时 bump。

## 8. 文档骨架

- [ ] `README.md`：项目定位、快速开始、文档导航。
- [ ] `ARCHITECTURE.md`：高层架构图、模块职责、数据流。
- [ ] `CLAUDE.md`：给 AI 助手的深度上下文（架构、命令、约定、坑点）。
- [ ] `docs/CONTRIBUTING.md`：开发流程摘要，引用本套标准。
- [ ] `docs/CHANGELOG.md`：版本变更记录（见 `08-documentation-policy.zh_CN.md`）。

## 9. 分支保护（即使是个人仓库）

`main` 分支至少：

- [ ] 禁止直接 push（必须走 PR）。
- [ ] PR 必须过 CI。
- [ ] PR 必须至少 1 个 approval（自己 review 也行——强制 self-review）。
- [ ] 禁止 force push。

GitHub 设置：Settings → Branches → Branch protection rules。

## 10. 完成检查

跑一次完整流程验证一切就绪：

```bash
make check          # 工具齐全
make install        # 依赖装好
make dev            # 服务起来
make lint           # 干净
make test           # 绿
git commit --allow-empty -m "chore: verify hooks"   # hook 工作
```

全过 → 项目初始化完成，可以开始第一次 feature 开发（见 `04-feature-workflow.zh_CN.md`）。

---

**原则**：初始化的每一步都是为了让后续的"标准流程"自动运转。第一天偷懒，后面每一行代码都要补回来。
