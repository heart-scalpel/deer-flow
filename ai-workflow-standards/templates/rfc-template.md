# RFC: <short-name> — <one-line description>

<!--
 RFC 模板（轻量版） / RFC template (lightweight tier)
 使用方法：拷到 docs/rfc-<short-name>.md
 Usage: copy this file to docs/rfc-<short-name>.md

 完整版（跨子系统、影响深远）用 design-spec-template.md，再加一份 plan。
 For larger cross-subsystem changes, use design-spec-template.md plus a separate plan file.
-->

**Status:** Draft  <!-- Draft → Approved → Implemented | Superseded by <new-rfc> | Rejected -->
**Date:** YYYY-MM-DD
**Author:** <you>
**PR / Issue:** #N  <!-- if applicable -->

---

## 1. 问题 / Problem

<!-- 当前痛点是什么？为什么这件事很重要？
     What hurts today? Why does this matter? -->

## 2. 设计原则 / Design Principles

<!-- 3-5 条不可妥协的约束，决策时遇到冲突按这些排序。
     3-5 non-negotiable constraints; use these to break ties when deciding. -->

1.
2.
3.

## 3. 方案 / Approach

### 3.1 API / 接口

<!-- 公开 API、配置项、命令、行为定义。给出代码示例。
     Public API, config fields, commands, behavior. Show code examples. -->

```python
# Python example (or whatever language applies)
```

```typescript
// TypeScript example (or whatever language applies)
```

### 3.2 行为 / Behavior

<!-- 用户/调用方能观察到的行为。新增、改变、废弃。
     What the user / caller can observe. Added, changed, deprecated. -->

## 4. 备选方案 / Alternatives Considered

<!-- 至少考虑过 1 个其他方案，对比后说明为什么没选。
     At least one alternative; explain why you didn't pick it. -->

| 方案 / Approach | 优点 / Pros | 缺点 / Cons | 决议 / Verdict |
|----------------|------------|------------|----------------|
| A（推荐 / recommended） | | | |
| B | | | |
| C | | | |

## 5. 迁移路径 / Migration Path

<!-- 对现有代码、配置、用户的影响。需要逐步迁移还是一次性切换？
     Impact on existing code, configs, users. Phased rollout or one-shot? -->

## 6. 风险 / Risks

<!-- 这个设计可能怎么失败？分别怎么缓解？
     How can this design fail? How is each risk mitigated? -->

1.
2.

## 7. 设计决议表 / Design Decisions

<!-- 每个关键决策的一行理由。和正文一一对应。
     One-line rationale for each key choice. Cross-references the body. -->

| 决策 / Decision | 选择 / Choice | 理由 / Reason |
|----------------|--------------|---------------|
| 公开 API 形态 / Public API shape | | |
| 配置覆盖方式 / Config override mechanism | | |
| 默认值 / Defaults | | |
| 向后兼容策略 / Backward-compat strategy | | |

## 8. 实现计划 / Implementation Plan

<!-- 把方案拆成可独立验证的 Task。每个 Task 一组改动 + 验证标准。
     Break the approach into independently verifiable tasks. Each task = a group of changes + a verification criterion. -->

### Task 1: <name>

**Files:**
- Modify: `path/to/file`
- Create: `path/to/new-file`

**Steps:**
- [ ] Step 1
- [ ] Step 2

**Constraints:**
- 不要改 X / Do not change X
- 必须保留 Y / Must preserve Y

**Verification:** 测试路径或可观察的成功标准 / test path or observable success criterion

### Task 2: <name>

**Files:**
- ...

**Steps:**
- ...

**Constraints:**
- ...

**Verification:** ...

## 9. 不做的事 / Out of Scope

<!-- 明确写什么不在本 RFC 范围内，避免 scope creep。
     Explicitly state what is NOT in this RFC's scope; prevents scope creep. -->

-

## 10. 修订记录 / Revisions

<!-- 实现过程中如果偏离了原始设计，在这里记录。
     If the design drifts during implementation, record it here. -->

- YYYY-MM-DD: <change>

---

## 反对方 / Devil's Advocate Review

<!-- 让 AI 助手扮演严苛的资深工程师读过这份 RFC 后填写。
     Have an AI assistant play a hard-nosed senior engineer and fill this in.

     Q1: 哪些假设没说清楚？/ What assumptions are left unstated?
     Q2: 哪些边界条件没考虑？/ What edge cases are missing?
     Q3: 这个设计在 10x 流量 / 10x 数据量下会怎么崩？/ How does this break at 10x?
     Q4: 备选方案 X 没选，能不能反过来选？/ Argue for picking alternative X. -->

-
