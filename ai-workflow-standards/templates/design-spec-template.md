# Design Spec: <name>

<!--
 完整设计文档模板 / Full design spec template
 使用方法：拷到 docs/specs/YYYY-MM-DD-<name>-design.md
 Usage: copy this file to docs/specs/YYYY-MM-DD-<name>-design.md

 配套 plan 文件路径 / Path of companion plan file:
   docs/plans/YYYY-MM-DD-<name>.md
-->

**Date:** YYYY-MM-DD
**Branch:** `<branch-name>`
**Status:** Draft  <!-- Draft → Design Approved → Implementation In Progress → Shipped | Deferred -->
**Depends on:** <!-- 链接前置 spec / link prerequisite specs -->
**Companion plan:** [`docs/plans/YYYY-MM-DD-<name>.md`](../plans/YYYY-MM-DD-<name>.md)

---

## 1. 目标 / Goal

<!-- 一段话说清要解决什么。包含可观察的成功标准。
     One paragraph: what does this solve? Include observable success criteria. -->

## 2. 调研发现 / Investigation Findings

<!-- 现有代码 / 数据 / 日志的实际状态。带证据（行号、文件路径、SQL、数据样本）。
     The actual state of current code / data / logs. With evidence (line numbers, file paths, SQL, data samples).

     不要假设，去验证。"我以为 X" → 去 grep X，引用具体行号。
     Do not assume. Verify. "I thought X" → grep for X, cite line numbers. -->

### 2.1 当前状态 / Today's state

### 2.2 为什么是这样 / Why it is this way

<!-- 现状是怎么形成的？历史 commit / 设计取舍 / 外部约束。
     How did the current state come to be? Past commits / design tradeoffs / external constraints. -->

### 2.3 具体证据 / Concrete evidence

<!-- 复现脚本输出、日志行、数据库查询结果。
     Repro script output, log lines, DB query results. -->

## 3. 方案候选 / Approaches Considered

<!-- 至少三个方案。对每个：
       - 思路 / idea
       - 实现成本 / implementation cost
       - 运行时成本 / runtime cost
       - 优点 / pros
       - 缺点 / cons
       - 风险 / risks
     At least three approaches. For each:
       implementation cost, runtime cost, pros, cons, risks. -->

### Approach A: <name>

### Approach B: <name>

### Approach C: <name>

### 对比 / Comparison

| 维度 / Dimension | A | B | C |
|------------------|---|---|---|
| 实现成本 / Implementation cost | | | |
| 运行时成本 / Runtime cost | | | |
| 向后兼容 / Backward compat | | | |
| 测试覆盖难度 / Testability | | | |
| 风险等级 / Risk level | | | |

## 4. 推荐方案 / Recommended Approach

<!-- 选哪个？为什么？特别要说清为什么不选其他方案。
     Which one? Why? Especially: why not the others? -->

## 5. 验证 / Verification

<!-- 怎么证明这个方案可行？
     最小可复现脚本？原型代码？数据测试？
     How do we prove this works?
     Minimal repro script? Prototype code? Data probe? -->

### 5.1 最小复现 / Minimal reproduction

```python
# Standalone script that proves the approach works (or surfaces the bug being fixed)
```

### 5.2 测试结果 / Test results

```
# Output of the verification script
```

### 5.3 假设的检验 / Hypothesis check

<!-- 列出方案依赖的每个假设，逐条验证。
     List every assumption the approach relies on; verify each. -->

| 假设 / Hypothesis | 验证方式 / How verified | 结论 / Result |
|------------------|------------------------|---------------|
| | | |

## 6. 风险 / Risks

<!-- 识别所有可能失败的地方，每个给缓解方案。
     Identify every place this could fail; give mitigation for each. -->

1. **风险 / Risk**: 
   **缓解 / Mitigation**:

2. **风险 / Risk**: 
   **缓解 / Mitigation**:

## 7. 反方意见及反驳 / Counterarguments and Rebuttals

<!-- 让 AI 助手或同事挑战这个设计，把挑战和你的反驳都记下来。
     Have an AI or peer challenge this design; record both the challenge and your rebuttal. -->

### 反方意见 1 / Counterargument 1

> [挑战内容 / the challenge]

**反驳 / Rebuttal**: 

## 8. 实现切片 / Implementation Slices

<!-- 推荐方案的实现拆成几个可独立 ship 的 PR。每个 PR 的范围、依赖、退出标准。
     Slice the recommended approach into independently shippable PRs. Each PR's scope, dependencies, exit criteria.

     详细 step-by-step 放在配套的 plan 文件里。
     Detailed step-by-step goes in the companion plan file. -->

| PR | 范围 / Scope | 依赖 / Depends on | 退出标准 / Exit criteria |
|----|--------------|-------------------|-------------------------|
| #1 | | | |
| #2 | | | |

## 9. 不做的事 / Out of Scope

<!-- 明确写什么不在本 spec 范围内。
     Explicitly state what is NOT covered by this spec. -->

-

## 10. 后续工作 / Future Work

<!-- 本 spec 完成后值得继续做的事（不阻塞当前 ship）。
     Worth doing after this spec ships; not blocking. -->

-

## 11. 参考资料 / References

<!-- 相关 issue、PR、外部文档、论文、源码链接。
     Related issues, PRs, external docs, papers, source links. -->

-

---

## 修订记录 / Revisions

- YYYY-MM-DD: <change>
