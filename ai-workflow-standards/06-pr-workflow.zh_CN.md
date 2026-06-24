# 06 · PR 工作流

> **一个人开发也要走 PR。** PR 不是"等别人审"的关卡，而是**强迫自己用第三方视角审一遍自己改动**的工具。
> 配套英文版：`06-pr-workflow.en.md`。
> PR 模板：`templates/PULL_REQUEST_TEMPLATE.md`。

---

## 1. 为什么独立开发也要走 PR

不走 PR 的代价：
- 直接 push 到 main → 没人（包括你自己）系统审过 → bug 进了主干才发现。
- 改动散落多个 commit → 三个月后想搞清楚"为什么这么改" 时翻不到。
- 没有验证记录 → CI 哪天挂了不知道是哪次改动引入的。
- AI 生成的代码没经过自审 → "AI 写啥我合啥"。

走 PR 的收益：
- **强制 self-review**：写 PR 描述 + 通读 diff = 用陌生人视角审一次。
- **可追溯**：PR 链接 Issue、RFC、验证命令、AI 工具——一条完整的决策链。
- **CI 门禁**：合并前 CI 必须绿，挡住本地漏掉的回归。
- **回滚锚点**：每个 PR 是一个 revert 单位，比逐 commit 回滚干净。

## 2. PR 必填节

PR 描述（按 `templates/PULL_REQUEST_TEMPLATE.md`）必须有：

| 节 | 必填条件 | 作用 |
|----|---------|------|
| **Issue 链接** | 有 Issue 时必填 | `Fixes #N` / `Closes #N` / `Ref #N` |
| **Why** | 总是必填 | 触发点 + 解决的痛点 |
| **What changed** | 总是必填 | 用户视角的变化描述，不是 diff 罗列 |
| **Surface area** | 总是必填 | 勾选所有涉及的表面，决定 review 范围 |
| **Bug fix verification** | bug fix 必填，其他删掉 | 测试路径 + main 红分支绿 |
| **Validation** | 总是必填 | 实际跑过的命令 |
| **AI assistance** | **总是必填** | 工具、用法、人类负责声明 |
| **Screenshots / Recording** | 涉及前端 UI 时必填 | 改动入口截图，最好前后对比 |
| **RFC / Spec 链接** | 有设计文档时必填 | 让 reviewer 顺藤摸瓜 |

## 3. 用 `gh` 开 PR

```bash
gh pr create --title "<type>(<scope>): <subject ≤70 字符>" --body "$(cat <<'EOF'
Fixes #123

## Why
<!-- 为什么开这个 PR？触发点 + 解决的痛点。非平凡功能先有 RFC。 -->

## What changed
<!-- 从用户/调用方视角描述变化。 -->

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
<!-- bug fix 才填，否则删掉。测试路径 + main 红 + 分支绿。 -->

## Validation
<!-- 实际跑过的命令。 -->
cd backend && make lint && make test
cd frontend && pnpm lint && pnpm typecheck && pnpm build && pnpm test

## AI assistance
**Tool(s) used:** <!-- Claude Code / Cursor / Copilot / none -->
**How you used it:** <!-- 怎么用 -->
- [ ] 我已读完并理解每一行变更，并对它负责——这不是未审阅的 AI 输出。
EOF
)"
```

## 4. Self-review checklist（合并前自审）

**所有项必须通过**才能合并：

### Diff 审阅
- [ ] `git diff main...HEAD` 通读全部改动。
- [ ] 每个 commit 都是原子的、message 符合 Conventional Commits。
- [ ] 没有 `console.log` / `print` / 调试代码残留。
- [ ] 没有注释掉的死代码。
- [ ] 没有 TODO 不带 issue 链接。

### 测试
- [ ] 新功能/bug 修复有对应测试。
- [ ] 测试覆盖 happy path + 失败路径 + 边界。
- [ ] CI 在 PR 上是绿的。
- [ ] 本地跑过完整 lint + test。

### 安全
- [ ] 没有 commit `.env` / 密钥 / credentials。
- [ ] 没有引入已知漏洞依赖（CI 的依赖扫描通过）。
- [ ] 没有写死密钥、token、密码。
- [ ] SQL / 命令注入、XSS、CSRF 检查过（如果改动涉及）。

### 文档
- [ ] 用户可见变化 → 更新 README。
- [ ] 架构变化 → 更新 ARCHITECTURE.md / CLAUDE.md。
- [ ] API 变化 → 更新 API 文档。
- [ ] 配置项变化 → 更新 config.example.yaml。

### PR 描述
- [ ] Why 节回答了"为什么开这个 PR"。
- [ ] What changed 节从用户视角描述。
- [ ] Surface area 全部勾选。
- [ ] Validation 节填了实际命令。
- [ ] AI assistance 节诚实填写。
- [ ] 关联 Issue / RFC（如有）。

### 文件大小
- [ ] PR diff < 300 行（理想）。
- [ ] PR diff > 700 行 → 有充分理由写在 Why 节。

## 5. PR 评审标准

自己作为 reviewer 给自己 review 时，问：

1. **能读懂吗**：三个月后我还能看懂每个文件为什么改吗？
2. **可逆吗**：如果出问题，能干净 revert 吗？
3. **破坏性**：改变了什么默认行为？谁会受影响？
4. **测试**：测试真的覆盖了根因，还是只覆盖了症状？
5. **AI 痕迹**：有没有 AI 生成的代码我没读完？
6. **范围**：这个 PR 是不是只做了一件事？有没有夹带？

任何一项答 "不确定" → 回去修。

## 6. 处理 CI 失败

CI 红了 → **不要重试 hoping it goes away**：

1. 读 CI 日志，定位失败原因。
2. 分类：
   - **Lint / format 失败** → 本地跑 `make format` / `pnpm format:write`，commit 修复。
   - **测试失败** → 是真 bug 还是测试本身有问题？修根因。
   - **构建失败** → 类型错误、缺依赖、配置问题？修。
   - **Flaky test** → 不要重试掩盖，标记 + 单独修。
3. 修复后 push → 等 CI 重跑。
4. **永远不要 `--no-verify` 跳过 hook 或 disable CI 检查**。

## 7. 合并策略

个人项目推荐 **Squash merge**：

- 多个 WIP commit 压成一个干净的 Conventional Commit。
- main 历史线性，易读。
- GitHub 设置：Settings → General → Pull Requests → Allow squash merging（勾选） / Allow merge commits（取消） / Allow rebase merging（可选）。

合并后：
- 自动删除 head 分支（GitHub 设置可开启）。
- `git checkout main && git pull --ff-only origin main && git branch -d <local-branch>`。

## 8. PR 节奏

- **一个 PR 一件事**：混合多个功能的 PR 难审、难回滚。
- **早开 PR**：哪怕 WIP，标 `[WIP]` 或 `draft`，让 CI 先跑起来。
- **小步推进**：reviewer 看大 PR 会偷懒；小 PR 反而被认真审。
- **回应反馈**：自己 review 自己也要诚实——发现的问题立刻修，不要"以后再说"。

## 9. 处理冲突

```bash
git fetch origin
git rebase origin/main   # 优先 rebase
# 解决冲突
git add <resolved>
git rebase --continue
git push --force-with-lease   # 注意：用 --force-with-lease 而非 --force
```

`--force-with-lease` 比 `--force` 安全：如果远端有别人 push 过的新提交会拒绝，避免覆盖。

## 10. 合并后

- [ ] 确认 CI 在 main 上也绿。
- [ ] 删除本地 + 远端 feature 分支。
- [ ] 如果有关联 Issue，确认 `Fixes` 生效。
- [ ] 如果是用户可见变化，更新 `CHANGELOG.md`。
- [ ] 如果是大功能，考虑发个 release tag。
- [ ] 如果有 RFC，把 `Status: Approved` 改成 `Status: Implemented`。

---

**一句话总结**：PR 不是等别人审的关卡，是**强迫自己审自己**的工具。Self-review checklist 全过、CI 全绿、描述填齐——三者缺一不可。
