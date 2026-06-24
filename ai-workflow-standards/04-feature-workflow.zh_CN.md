# 04 · 功能开发端到端流程

> 从一个想法到合并进 `main`，走完整条链路。
> 配套英文版：`04-feature-workflow.en.md`。
> 上游：`02-development-workflow.zh_CN.md`、`03-rfc-process.zh_CN.md`、`06-pr-workflow.zh_CN.md`。

---

## 0. 决策树

```
新想法 / 新需求
  ↓
是 bug 吗？
  ├─ 是 → 走 05-bug-fix-workflow.zh_CN.md
  └─ 否 ↓
触发 RFC 条件吗？（见 03 第 2 节）
  ├─ 触发 → 写 RFC（档位 A 或 B）
  └─ 不触发 → 直接进入开发循环
  ↓
开发循环：02-development-workflow.zh_CN.md
  ↓
PR：06-pr-workflow.zh_CN.md
  ↓
合并
```

## 1. 想法阶段

**产出**：一段话能说清"做什么、为什么、给谁用"。

模板：

```markdown
**做什么**：一句话功能描述。
**为什么**：当前痛点 / 用户请求 / 业务驱动。
**给谁用**：目标用户或调用方。
**完成的样子**：可观察的成功标准（用户能看到/能做到什么）。
**不在范围**：明确不做什么。
```

判断：
- 这段话写不出来 → 想法还不够清楚，**先想，不要先动手**。
- 写得出来 → 进入下一步。

## 2. RFC 阶段（如触发条件满足）

按 `03-rfc-process.zh_CN.md` 选档位：

| 改动类型 | 推荐档位 |
|---------|---------|
| 单模块新增、API 调整 | 档位 A（轻量 RFC） |
| 跨子系统、新增 middleware、改变默认行为 | 档位 B（完整 Spec + Plan） |
| 紧急 hotfix | 跳过，事后补 |
| 探索原型 | 档位 A，标 `Status: Exploratory` |

**完成标准**：RFC 文件存在、头部 `Status: Approved`、AI 助手已扮演反对者挑过刺、修订留痕。

## 3. 任务拆分阶段

把 RFC 的 Plan 节落到任务清单。每个任务满足：

- **可独立验证**：完成后能跑测试或人工确认。
- **可独立 commit**：粒度对应一个 Conventional Commit。
- **可独立 revert**：不破坏其他任务的结果。
- **预估工时**：1-4 小时为宜；超 1 天的拆细。

工具：
- AI 助手：用 `TaskCreate` 把任务录进会话，逐项 in_progress → completed。
- 项目级：复杂功能在 RFC 的 Plan 里维护勾选式清单（参考 deer-flow 的 `docs/superpowers/plans/` 风格）。

## 4. 实现阶段（每个任务）

按 TDD 循环（见 `02-development-workflow.zh_CN.md` 第 2 节）：

```
1. 切分支（如果是第一个任务）
   git checkout -b feature/<name>

2. 对每个任务：
   a. 写测试 → 红
   b. 写实现 → 绿
   c. 重构 → 保持绿
   d. 跑本地校验门（lint + test + typecheck + build）
   e. git commit（Conventional Commits）
   f. 标记任务 completed

3. 全部任务完成 → 进入 PR 阶段
```

### 实现中的纪律

- **每完成一个任务立刻 commit**，不要攒。
- **RFC 偏差立即记录**：发现设计不对 → 暂停、改 RFC、记 Revision 节、再继续。
- **意外发现新 bug**：开新分支处理，不要顺手在 feature 分支里夹带（混入会让 PR 难审）。
- **重构冲动**：发现可以顺便清理的代码 → 记下来，开单独的 `refactor/` 分支处理，**不要夹带**。

## 5. 文档同步阶段（实现中持续）

边写代码边更新文档（详见 `08-documentation-policy.zh_CN.md`）：

- 新增公开 API → 同步更新 `docs/API.md` 或 `README.md`。
- 新增配置项 → 同步更新 `config.example.yaml` 和配置文档。
- 改变默认行为 → 同步更新 `README.md`。
- 改变架构 → 同步更新 `ARCHITECTURE.md` 和 `CLAUDE.md`。

**纪律**：文档和代码同一个 commit，不要"代码先合、文档后补"。后补的文档永远补不上。

## 6. 自审阶段（push 前）

假装在 review 别人的 PR：

- [ ] 跑完整本地校验门。
- [ ] `git diff main...HEAD` 通读所有改动。
- [ ] 每个文件，问自己："如果这个文件被删了，我能解释为什么需要它吗？"
- [ ] 每段新增代码，问自己："三个月后我还能解释这段在做什么吗？"
- [ ] 测试覆盖：每个公开函数至少一个 happy path + 一个失败路径。
- [ ] 没有未审的 AI 生成代码（见 `00-operating-principles.zh_CN.md` 第 2.1 节）。
- [ ] 文档全部同步。

发现任何问题 → 回到实现阶段修。

## 7. PR 阶段

按 `06-pr-workflow.zh_CN.md` 提交。关键点：

- PR 描述链接到 RFC（如有）。
- PR 描述勾选 Surface area 所有适用项。
- PR 描述填 Validation 节（实际跑过的命令）。
- PR 描述填 AI assistance 节（用了什么工具、怎么用、人类负责声明）。
- 自审通过后再 push。

## 8. 合并后

- [ ] 删除 feature 分支（本地 + 远端）。
- [ ] 如果有跟踪的 Issue，确认 PR 的 `Closes #N` 生效。
- [ ] 如果 RFC 的 `Status` 还是 `Approved`，更新为 `Implemented`。
- [ ] 如果是用户可见变化，更新 `CHANGELOG.md`。
- [ ] 如果是大功能，考虑在 README 加一行介绍。

## 9. 完成后回看

合并一周后回看：

- 这功能在生产中真的被用了吗？（如果没有人用，可能 RFC 阶段没想清楚"给谁用"。）
- 测试有没有发现回归？（如果有，是不是 TDD 阶段红测试写得不够。）
- 文档有没有人问？（如果有，可能文档同步阶段偷懒了。）

把回看结论叠到下一次功能的想法阶段。

---

**一句话总结**：想法 → RFC（如触发）→ 任务拆分 → TDD 实现（边写边同步文档）→ 自审 → PR → 合并 → 回看。每一步都有退出条件，**不满足不进下一步**。
