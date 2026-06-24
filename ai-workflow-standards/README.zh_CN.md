# AI 协作标准套件 · 中文索引

> 这是给 AI 助手（Claude Code / Cursor / Copilot 等）用的**项目无关协作流程标准**。
> 全栈 Web 项目（Python 后端 + TS 前端），独立开发（你 + AI 助手）。
> 英文版：[`README.en.md`](./README.en.md)

---

## 这套套件是干什么的

把"如何在一个新项目里和 AI 助手协作开发"标准化。把整个 `ai-workflow-standards/` 目录拷到任何新项目根目录，AI 助手读完就能按统一标准工作。

**适用**：全栈 Web（Python 后端 + TS 前端）、独立开发、需要 RFC + PR + CI + TDD 纪律。

**不适用**：纯算法库、嵌入式、移动端原生、企业内部强治理场景（需要补 COC、安全披露等）。

---

## AI 助手首次进入项目时

按这个顺序读：

1. **`00-operating-principles.zh_CN.md`** —— 操作原则和红线（最高优先级）。
2. **`README.md`**（项目自带的）—— 项目定位和快速开始。
3. **`CLAUDE.md`** / **`ARCHITECTURE.md`**（项目自带的）—— 深度上下文。
4. **任务相关的具体流程文件**（按下表选）。

---

## 文件索引

| 文件 | 何时读 | 一句话作用 |
|------|--------|-----------|
| [`00-operating-principles.zh_CN.md`](./00-operating-principles.zh_CN.md) | **总是先读** | AI 协作的红线和默认行为 |
| [`01-project-init.zh_CN.md`](./01-project-init.zh_CN.md) | 新项目第一天 | 项目初始化清单 |
| [`02-development-workflow.zh_CN.md`](./02-development-workflow.zh_CN.md) | 写代码前 | 分支、commit、TDD、本地校验 |
| [`03-rfc-process.zh_CN.md`](./03-rfc-process.zh_CN.md) | 大改动前 | 什么时候写 RFC、怎么写 |
| [`04-feature-workflow.zh_CN.md`](./04-feature-workflow.zh_CN.md) | 开发新功能时 | 从想法到合并的端到端流程 |
| [`05-bug-fix-workflow.zh_CN.md`](./05-bug-fix-workflow.zh_CN.md) | 修 bug 时 | 红测试优先的修复流程 |
| [`06-pr-workflow.zh_CN.md`](./06-pr-workflow.zh_CN.md) | 提 PR 时 | PR 模板、自审、合并策略 |
| [`07-ci-cd-standards.zh_CN.md`](./07-ci-cd-standards.zh_CN.md) | 配 CI 时 | 必查项、GitHub Actions 模板 |
| [`08-documentation-policy.zh_CN.md`](./08-documentation-policy.zh_CN.md) | 改完代码后 | 文档同步纪律 |

模板（`templates/`）：

| 模板 | 用途 |
|------|------|
| [`templates/PULL_REQUEST_TEMPLATE.md`](./templates/PULL_REQUEST_TEMPLATE.md) | 拷到 `.github/pull_request_template.md` |
| [`templates/bug-report.md`](./templates/bug-report.md) | 拷到 `.github/ISSUE_TEMPLATE/bug-report.md` |
| [`templates/rfc-template.md`](./templates/rfc-template.md) | 起草轻量 RFC 的起点 |
| [`templates/design-spec-template.md`](./templates/design-spec-template.md) | 起草完整设计文档的起点 |

---

## 给 AI 助手的最小加载规则

如果你是 AI 助手，且这个目录存在于项目根：

1. **会话开始时**：读 `00-operating-principles.zh_CN.md`（必读）+ 项目自带的 `CLAUDE.md`。
2. **接到任务时**：按下表加载相关文件。

| 用户任务 | 加载文件 |
|---------|---------|
| "帮我初始化项目" | `01` + `templates/*` |
| "我要加 X 功能" | `03`（判断是否触发 RFC）→ `04` → `02` → `06` |
| "有个 bug / 报了个 bug" | `05` → `02` → `06` |
| "我改完代码了" | `02`（本地校验）→ `08`（文档同步）→ `06`（开 PR） |
| "配一下 CI" | `07` |
| "怎么写 commit" | `02` 第 3 节 |

3. **冲突优先级**：`00` > 项目自带 `CLAUDE.md` > 具体流程文件（`02-08`） > 你的默认行为。

---

## 怎么用这套套件

### 用法 A：拷进新项目

```bash
# 假设新项目路径是 ~/code/my-new-app
cp -r ai-workflow-standards/ ~/code/my-new-app/

# 然后在新项目里：
cd ~/code/my-new-app
# 把 templates/PULL_REQUEST_TEMPLATE.md 移到 .github/
# 把 templates/bug-report.md 移到 .github/ISSUE_TEMPLATE/
# 把 templates/rfc-template.md 和 design-spec-template.md 移到 docs/
```

按 `01-project-init.zh_CN.md` 跑初始化清单。

### 用法 B：作为系统提示词喂给 AI

把整个目录加入 AI 助手的"项目文档"或"系统提示词"。Claude Code 会自动读根目录的 `CLAUDE.md`，可以在那里加一行：

```markdown
## Workflow

This project follows the AI workflow standards in `ai-workflow-standards/`.
Start by reading `ai-workflow-standards/00-operating-principles.zh_CN.md`.
```

### 用法 C：作为团队约定

即使是独立开发，也可以把这套作为"未来的我"的约定。每条规则都解释了 why，未来的你回来读不会一头雾水。

---

## 套件的边界

这套标准**不是**：

- ❌ 一个完整的项目模板（不含具体代码示例，只讲流程）。
- ❌ 企业级治理框架（无 COC、无安全披露流程、无多团队协作）。
- ❌ 某个具体框架的最佳实践（不绑定 Django / FastAPI / Next.js 的特定用法）。
- ❌ 一成不变的教条——遇到具体项目不适用的部分，调整它，留 why 痕迹。

这套标准**是**：

- ✅ 一个让"独立开发 + AI 助手"也能维持工程纪律的脚手架。
- ✅ 一份可以拷贝、修改、扩展的起点。
- ✅ 让 AI 助手行为可预测、决策可追溯的统一上下文。

---

## 维护

- 套件本身的改动也走 PR（即使是个人项目）。
- 改了某份文件 → 同步改对应语言版本。
- 累积了新经验 → 加进相应文件，不要新建碎片化文件。

---

**一句话总结**：把这套拷到新项目，AI 助手读完 `00` 再开工，所有"该怎么写代码"的问题都有标准答案。
