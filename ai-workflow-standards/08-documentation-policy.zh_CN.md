# 08 · 文档策略

> **文档不是事后补的，是和代码一起写的。** 代码改了文档没改 = 工作未完成。
> 配套英文版：`08-documentation-policy.en.md`。

---

## 1. 文档分层

| 文档 | 受众 | 何时更新 | 内容定位 |
|------|------|---------|---------|
| `README.md` | 第一次访问项目的人 | 任何用户可见行为变化 | 项目定位、快速开始、文档导航 |
| `ARCHITECTURE.md` | 想理解整体设计的人 | 架构层面变化 | 高层架构图、模块职责、数据流 |
| `CLAUDE.md` | AI 助手（以及读它的你） | 命令 / 工作流 / 内部系统变化 | 深度上下文：架构、命令、约定、坑点 |
| `docs/CONFIGURATION.md` | 配置项目的用户 | 配置项变化 | 每个 config.yaml 字段的含义和默认值 |
| `docs/API.md` | 调用 API 的人 | API 端点变化 | 每个 endpoint 的方法、参数、响应 |
| `docs/CONTRIBUTING.md` | 贡献者 | 开发流程变化 | 引用本套标准，本地启动、提交规范 |
| `docs/CHANGELOG.md` | 升级版本的用户 | 每次发版 | 版本变化列表 |
| `docs/RFC-INDEX.md` | 想理解决策历史的人 | 每次新增 RFC | RFC 列表（见 `03-rfc-process.zh_CN.md` 第 7 节） |
| `docs/postmortems/` | 复盘故障的人 | 重大事故后 | 时间线、影响、根因、行动项 |

## 2. README.md 的角色

README 是项目的**前门**。要求：

- **3 行内说清项目是什么**：定位、解决什么问题、给谁用。
- **5 分钟内能跑起来**：安装、配置、启动的命令完整。
- **文档导航清晰**：链接到 ARCHITECTURE / API / CONFIGURATION / CONTRIBUTING。

反模式：
- ❌ README 写架构细节（应放 ARCHITECTURE）。
- ❌ README 写开发流程（应放 CONTRIBUTING）。
- ❌ README 写配置项细节（应放 CONFIGURATION）。
- ❌ README 没有快速开始。
- ❌ README 几个月没更新。

## 3. CLAUDE.md 的角色

CLAUDE.md（或 AGENTS.md、.cursor/rules）是给 AI 助手的**项目级系统提示**。要求：

- **架构总览**：模块划分、依赖方向、数据流。
- **常用命令**：lint / test / build / dev 的精确命令。
- **代码约定**：风格、命名、文件组织。
- **不可越过的边界**：架构分层约束、依赖方向、安全约束。
- **坑点提示**：易踩的雷、非显然的行为。
- **测试策略**：怎么写测试、跑哪些测试、blocking-IO 之类的运行时 gate。

每次代码改动后，**先问自己**：这次改动需要更新 CLAUDE.md 吗？

- 改了模块结构 → 更新。
- 加了新命令 → 更新。
- 改了内部约定 → 更新。
- 加了新坑点 → 更新。
- 单纯改实现细节 → 通常不需要。

## 4. 文档同步纪律

### 同步原则

**文档和代码同一个 commit / PR。** 不要"代码先合、文档后补"——后补的文档永远补不上。

### 决策树

```
代码改动 →
  改了用户可见行为？
    → 是：更新 README
  改了架构 / 模块结构 / 命令 / 工作流？
    → 是：更新 ARCHITECTURE 和/或 CLAUDE.md
  改了配置项？
    → 是：更新 config.example.yaml + CONFIGURATION.md
  改了 API？
    → 是：更新 API.md（OpenAPI 自动生成的话确认生成结果）
  改了开发流程？
    → 是：更新 CONTRIBUTING.md
  改了依赖？
    → 是：更新 README 的 prerequisites + (CI 配置)
  没有任何上述变化？
    → 通常是纯实现细节，不需要更新文档
```

## 5. CHANGELOG 纪律

`docs/CHANGELOG.md` 遵循 [Keep a Changelog](https://keepachangelog.com/) 格式：

```markdown
# Changelog

## [Unreleased]

### Added
- 新功能 X

### Changed
- 默认 Y 从 A 改为 B

### Deprecated
- Z 即将废弃，用 W 替代

### Removed
- 删除了 V

### Fixed
- 修复 bug U

### Security
- 修复 CVE-XXXX-XXXXX

## [1.2.0] - 2026-06-15
...
```

### 何时写 CHANGELOG

- 每次 PR 合并到 main → 在 `[Unreleased]` 节加一条。
- 每次发版 → 把 `[Unreleased]` 改成 `[version] - date`，新建空的 `[Unreleased]`。

### 什么要记

- 用户可见的功能/行为变化（added / changed / deprecated / removed / fixed / security）。
- **不记**内部重构、测试补充、CI 配置（除非影响发布产物）。

## 6. API 文档

### 自动生成优先

- 后端：FastAPI → `GET /openapi.json` → Swagger UI / Redoc。
- 前端：tRPC / Zod → 自动推导 schema。
- gRPC：protobuf → buf generator。

### 手写补充

自动生成只能告诉调用者"参数和返回值"，**不能**告诉：

- 这个 endpoint 什么时候该用、什么时候不该用。
- 边界 case 的行为（限流、重试、幂等性）。
- 错误码的业务含义。

这些手写在 `docs/API.md` 或 OpenAPI 的 `description` 字段里。

## 7. 代码注释

### 默认不写注释

代码默认**不写注释**。命名清晰 + 类型完整 + 测试覆盖 = 自解释。

### 何时必须写

注释写**为什么**（why），不写**是什么**（what）：

```python
# Bad
i += 1  # i 加 1

# Good
# Deadline is +7 days because the legal review window requires a week minimum.
deadline = today + timedelta(days=7)
```

**必须写注释的场景**：
- 非显然的业务规则、合规约束、外部契约。
- Workaround（链接到相关 issue / RFC）。
- 性能优化的理由（"这里用 dict 而非 list 是因为 O(1) 查询"）。
- Magic number 的来源。
- 反直觉的行为（"这段代码看起来奇怪是因为 X 历史原因"）。

### 不要写

- 重复代码已经说清楚的（`# set name to empty` above `name = ""`）。
- 引用已废弃的 issue / PR（链接会失效）。
- 临时性的"修改了 X"（属于 commit message，不属于注释）。

## 8. README 文档导航段示例

```markdown
## Documentation

- [Architecture](docs/ARCHITECTURE.md) — high-level design and module layout
- [Configuration](docs/CONFIGURATION.md) — every config field explained
- [API reference](docs/API.md) — endpoint catalog
- [Contributing](docs/CONTRIBUTING.md) — dev setup and workflow
- [Changelog](docs/CHANGELOG.md) — release history
- [RFCs](docs/rfc-index.md) — design decision history
```

## 9. 文档自身的 review

PR 自审时多带一项：

- [ ] 这次改动需要更新文档吗？需要的话更新了吗？

如果 reviewer（包括你自己）问"为什么文档没提 X" → 文档同步漏了。

## 10. 文档过期清理

- 每季度过一遍 `docs/` 删过期内容。
- 删的内容如果有价值 → 移到 `docs/archive/`。
- 引用过期文档的代码 → 一并更新。

## 11. 多语言文档

如果项目要中英双语（参考本套标准的 CN/EN 配对）：

- **每对文件结构对齐**：CN 和 EN 同节同序，方便对照。
- **代码示例统一用英文**：避免代码内字符串/注释的中英漂移。
- **同步更新**：改了一份必须立即改另一份，不要"先改 CN，EN 之后再翻译"。
- **顶部互链**：每份文件头部链接到对应语言版本。

---

**一句话总结**：文档是代码的**影子**——代码动，影子必须动。代码改了文档没改，等于把项目变成一座只你自己能读懂的迷宫，未来的你（和 AI 助手）都会迷路。
