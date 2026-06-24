# 02 · 日常开发循环

> 每天写代码的默认节奏。所有 PR 都要跑通这套流程。
> 配套英文版：`02-development-workflow.en.md`。
> 上游原则：`00-operating-principles.zh_CN.md`。

---

## 1. 同步与切分支

```bash
git checkout main
git pull --ff-only origin main
git checkout -b <type>/<short-name>
```

### 分支命名

| 类型 | 前缀 | 示例 |
|------|------|------|
| 新功能 | `feature/` | `feature/add-minimax-provider` |
| Bug 修复 | `fix/` | `fix/sandbox-timeout` |
| 文档 | `docs/` | `docs/update-readme` |
| 重构 | `refactor/` | `refactor/config-system` |
| 测试 | `test/` | `test/cover-memory-queue` |
| 构建/配置 | `chore/` | `chore/bump-deps` |
| 性能 | `perf/` | `perf/index-message-store` |

**规则**：kebab-case，≤50 字符，语义清晰，不带日期/作者名（git 自带）。

## 2. TDD 循环：红 → 绿 → 重构

每写一段功能：

1. **红**：写一个测试，跑 → 失败（在 `main` 上也失败）。
2. **绿**：写最小实现，让测试刚好通过。
3. **重构**：清理代码，测试保持绿。

```bash
# 后端
cd backend && PYTHONPATH=. uv run pytest tests/test_<feature>.py -v

# 前端
cd frontend && pnpm test -- <pattern>
```

**不要**先写实现再补测试——那样测试只会验证你已经写的东西，不会发现设计错误。

## 3. Commit 规范（Conventional Commits）

### 格式

```
<type>(<scope>): <一句话描述>

<!-- 可选 body -->
- 要点 1
- 要点 2

<!-- 可选 footer -->
Closes #123
```

### type 取值

| type | 用途 |
|------|------|
| `feat` | 新功能（用户可见） |
| `fix` | Bug 修复 |
| `docs` | 文档 |
| `refactor` | 重构（不改外部行为） |
| `test` | 测试 |
| `chore` | 构建、依赖、CI、配置 |
| `perf` | 性能优化 |
| `style` | 格式（一般由工具自动产生，不要单独 commit） |
| `ci` | CI 配置 |
| `build` | 构建系统/依赖 |

### 描述句

- **祈使句**："add support for X"，不是 "added support for X"。
- ≤70 字符（GitHub 截断阈值）。
- 不要句号结尾。
- 不要 emoji（除非项目约定）。

### 示例

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

### 反例

- ❌ `update code`
- ❌ `fix bug`
- ❌ `wip`
- ❌ `asdf`
- ❌ `fix: 修复了` （中文动词在 type 后但缺乏主语）
- ❌ `feat: 一大段话超过了七十字符上限所以会被截断不好看不好搜`

## 4. Commit 粒度

**一个 commit 一件事**。

- 加新功能 + 改 lint 配置 → 两个 commit。
- 修 bug + 顺手重构 → 两个 commit。
- 多个相关改动（同一功能的不同文件）→ 可以一个 commit。

判断标准：**这个 commit 能不能独立 revert 而不破坏其他东西？** 不能就拆。

## 5. 本地校验门（push 前必跑）

### 后端

```bash
cd backend
make format   # ruff format（自动）
make lint     # ruff check .
make test     # uv run pytest
```

### 前端

```bash
cd frontend
pnpm format:write          # Prettier
pnpm lint                  # ESLint
pnpm typecheck             # tsc --noEmit
BETTER_AUTH_SECRET=local-dev-secret pnpm build   # 生产构建
pnpm test                  # 单元测试
```

UI 改动还要：

```bash
cd frontend && make test-e2e   # 需要 Chromium
```

### 通用

- [ ] 没有 `console.log` / `print` 残留（除非有意保留并注释）。
- [ ] 没有注释掉的大段死代码。
- [ ] 没有 TODO 没有对应的 issue 链接。
- [ ] 没有引入未声明的新依赖。
- [ ] 没有把 `.env` / `config.yaml` 暂存。

## 6. 不要 commit 的东西

- ❌ `.env`、`config.yaml`、`extensions_config.json`、credentials。
- ❌ `.venv/`、`node_modules/`、`__pycache__/`、`.next/`、`dist/`。
- ❌ 大二进制文件（图片、视频、数据集）—— 用 LFS 或外部存储。
- ❌ IDE 个人配置（`.idea/workspace.xml` 等）。
- ❌ OS 文件（`.DS_Store`、`Thumbs.db`）。

`git status` 检查暂存内容是干净的工作树。

## 7. 暂存策略

- **优先 `git add <具体文件>`**，不要 `git add .` / `git add -A`——容易夹带未审文件。
- 用 `git add -p` 分块暂存，把同一改动拆成多个语义 commit。
- 暂存前 `git diff --cached` 复核一遍要 commit 的内容。

## 8. Push 频率

- **早 push、勤 push**——本地丢了没人救。
- 每完成一个语义单元（一个 commit）就可以 push。
- 不要攒一周的 commit 一起 push。

```bash
git push -u origin <branch-name>
```

## 9. 跟 `main` 同步

`main` 有新提交时：

```bash
git fetch origin
git rebase origin/main   # 优先 rebase，保持线性历史
```

冲突解决后：

```bash
git add <已解决的文件>
git rebase --continue
# 不要 git rebase --skip 除非明确知道为什么
# 永远不要 --no-verify
```

如果 feature 分支已 push 且有协作（即使是自己另一台机），用 merge 而非 rebase，避免改写历史。

## 10. 完成 → 进入 PR 流程

跑完本地校验、push 完分支 → 进入 `06-pr-workflow.zh_CN.md`。

---

**一句话总结**：分支名守规范，commit 写清楚，TDD 不跳步，push 前本地校验全过——这四件事做到，PR 阶段就只剩自我审阅了。
