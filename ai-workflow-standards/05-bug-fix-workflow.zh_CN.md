# 05 · Bug 修复流程

> Bug 修复的核心纪律：**先用一个会失败的测试把 bug 钉住，再修**。否则你永远不知道自己是真修了还是碰巧让症状消失了。
> 配套英文版：`05-bug-fix-workflow.en.md`。
> Bug 上报模板：`templates/bug-report.md`。

---

## 1. Bug 修复的核心原则

1. **先复现**：不能稳定复现的 bug，无法验证修复。
2. **写红测试**：复现路径编成一个测试，在 `main` 上跑 → 必须失败。
3. **改最小**：只动必要的代码，不夹带重构、不顺手清理。
4. **验证绿**：测试转绿，且其他测试不被破坏。
5. **想根因**：症状修了不等于根因修了——问"为什么 bug 一开始能存在？"
6. **防回归**：测试留在主分支，未来同样的 bug 会被它挡住。

## 2. Bug 修复全流程

### Step 1：接收 bug

来源：
- 自己跑出来 → 写一份 bug report（参考 `templates/bug-report.md`）。
- 用户反馈 / 上报 → 让对方填 bug report 模板。
- 监控告警 → 自己复现并填 report。

**最少信息**：复现步骤、实际行为、期望行为、运行环境（OS、版本、配置）、相关日志。

### Step 2：搜重

```bash
gh issue list --state all --search "<keywords>"
```

确认不是已知问题。如果是 → 加评论 / 重新打开已有 issue，不开新分支。

### Step 3：切分支

```bash
git checkout main
git pull --ff-only origin main
git checkout -b fix/<short-bug-name>
```

### Step 4：复现 + 写红测试

**这是最关键的一步**。

```
1. 按 bug report 的步骤，手动复现一次（确认 bug 真的存在）。
2. 把复现步骤编成自动化测试：
   - 后端：tests/test_<bug-area>.py
   - 前端：tests/<area>.test.ts
3. 在 main 上跑这个测试 → 必须失败。
   git stash
   git checkout main
   跑测试 → 红
   git checkout fix/<short-bug-name>
   git stash pop
```

**不能写红测试的场景**：
- UI 视觉 bug → 改用 E2E 截图对比或手动测试步骤。
- 真实外部服务 bug → mock + contract test。
- 并发/时序 bug → 注入式测试（mock time / lock / scheduler）。
- 性能 bug → 基准测试 + 性能阈值。

不能写红测试 → **必须在 PR 中解释为什么**，并提供替代验证（手动测试步骤 + 截图 + 日志）。

### Step 5：定位根因

不要看到症状就改。先用调试手段定位：

- 加 print / console.log（事后必删）→ 跑测试 → 看哪一步状态不对。
- 用 debugger：`pytest --pdb`、`pnpm test --debug`、Chrome DevTools。
- 读 git log / git blame 找引入 bug 的 commit：`git log -S "<suspicious string>"`。
- 二分：`git bisect start` / `git bisect bad HEAD` / `git bisect good <older-commit>`。

定位到根因后再动手。

### Step 6：写最小修复

- **改最小**：只动引起 bug 的那几行。
- **不顺手重构**：发现可清理的代码 → 记下来，开单独分支处理。
- **不引入新依赖**：除非 bug 的根因就是某个依赖问题。
- **保留兼容**：如果 bug 修复改变了行为，考虑是否有用户依赖旧行为（在 PR 中说明）。

### Step 7：验证

```bash
# 跑刚才的红测试 → 现在应该绿
cd backend && PYTHONPATH=. uv run pytest tests/test_<bug-area>.py -v
# 或
cd frontend && pnpm test -- <pattern>

# 跑全量回归
cd backend && make test
cd frontend && pnpm test
```

- 红测试转绿 ✅
- 其他测试不退化 ✅
- lint 干净 ✅
- typecheck 干净（前端） ✅

### Step 8：补回归测试覆盖（可选但推荐）

红测试只覆盖了**这一种**触发路径。想一想：

- 同类输入的边界值有没有覆盖？
- 反向用例（不该触发的场景）有没有测？
- 修复有没有打开新漏洞？

如果红测试不够覆盖根因，**再加几个测试**，确保未来其他变体也会被挡住。

### Step 9：写 PR

按 `06-pr-workflow.zh_CN.md`，特别填好 **Bug fix verification** 节：

```markdown
## Bug fix verification
- Test path: tests/test_sandbox.py::test_acquire_timeout_on_cold_start
- Red on main: yes (run on commit abc1234)
- Green on branch: yes
```

PR 标题：`fix(<scope>): <one-line-description>`。
PR 描述链接 Issue：`Fixes #123`。

### Step 10：合并后

- 删除 fix 分支。
- 确认 Issue 自动关闭（`Fixes` 生效）。
- 如果 bug 暴露了某个流程漏洞（如某类测试缺失），开一个 `chore` 分支加强。

## 3. 特殊类型的 bug

### Production hotfix

```
1. 在 main 上 tag 当前状态（应急回滚锚点）
2. 切 hotfix 分支：git checkout -b hotfix/<name>
3. 最小修复 + 红测试
4. 加速 review（自审 + 一人 review）
5. 合并 + 立即部署
6. 事后：补回归测试、写事故复盘（docs/postmortems/YYYY-MM-DD-<name>.md）
```

### Flaky test（间歇失败的测试）

- 不要忽略，不要 `@pytest.mark.flaky` 重试掩盖。
- 用 `pytest --count=100 -x` 反复跑定位。
- 根因通常是：时序竞争、隐式状态依赖、外部资源未清理。
- 修复后用 `--count` 反复验证稳定。

### 性能 regression

- 不要凭感觉改。
- 先跑基准（before vs after commit）→ 量化退化。
- 用 profiler（py-spy、Chrome DevTools）找热点。
- 修复后再跑基准 → 量化改善。
- 把基准写进 CI 的 performance job（可选）。

### 安全相关 bug

- 按严重程度分类（参考 CVSS）。
- 严重 → 私下修复，不公开 Issue 直到补丁可用。
- 修复后写 `docs/security/advisories/YYYY-MM-DD-<name>.md`，说明影响范围、修复版本、升级建议。

## 4. Bug 修复的反模式

- ❌ **改了症状没改根因**：加个 try/except 吞掉异常，bug 还在。
- ❌ **顺手重构**：修 bug 顺手清理一堆代码 → PR 难审，难回滚。
- ❌ **删测试**：测试 fail 了就删测试，bug 假装修好了。
- ❌ **mock 掉真实路径**：让测试过，但 bug 没被验证。
- ❌ **不写 PR 链接**：未来没人能追溯这个 bug 的来龙去脉。
- ❌ **复现步骤丢失**：bug report 没记录复现路径，未来无法验证。

## 5. 一个完整的 Bug 修复 PR 长什么样

标题：`fix(sandbox): resolve timeout on cold container start`

```markdown
Fixes #421

## Why
用户报告：冷启动后首次沙箱调用总是 30 秒超时。
日志显示 readiness probe 在 2s 后才翻绿，但 acquire 路径在 1s 间隔轮询，刚好错过。

## What changed
Sandbox acquire 路径的 poll interval 现在可配置，默认 500ms（之前 1s 硬编码）。

## Surface area
- [x] Backend API
- [ ] Frontend UI
- [ ] Agents / LangGraph
- [ ] Sandbox
- [ ] Skills
- [ ] Dependencies
- [ ] Default behavior change   ← poll interval 默认值变了
- [ ] Docs / tests / CI only

## Bug fix verification
- Test path: backend/tests/test_sandbox.py::test_acquire_timeout_on_cold_start
- Red on main: yes (verified on commit abc1234)
- Green on branch: yes

## Validation
cd backend && make lint && make test
冷启动场景手动验证：rm -rf .sandbox-cache && make dev && 调用 /api/runs/stream 3 次均成功

## AI assistance
**Tool(s) used:** Claude Code
**How you used it:** 定位 poll interval 硬编码位置 + 起草红测试
- [x] 我已读完并理解每一行变更，并对它负责。
```

---

**一句话总结**：写红测试钉住 bug → 定位根因 → 最小修复 → 验证绿 → PR。**没有红测试的 bug 修复 = 假装修好了**。
