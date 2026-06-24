---
name: Bug report
about: 报告一个可复现的问题 / Report something that isn't working
title: "[bug] "
labels: ["bug"]
---

<!-- 感谢花时间填 bug。一份清晰可复现的报告，是修复速度的最大影响因素。
     请填完所有必填字段——尤其 **复现步骤** 和 **日志**。
     Thanks for taking the time to file a bug. A clear, reproducible report is
     the single biggest factor in how fast it gets fixed.
     Please fill in every required field — especially **reproduction steps** and **logs**. -->

## Before you start / 开工前

- [ ] I searched [existing issues](../../issues?q=is%3Aissue) and this is not a duplicate.
- [ ] I can reproduce this on the latest `main`.

## Problem summary / 问题概述

<!-- 一句话描述 bug。One sentence describing the bug. -->
<!-- e.g. make dev fails to start the gateway service -->

## Affected area(s) / 受影响范围

<!-- 全选适用项。Select all that apply. -->

- [ ] Frontend (UI / Next.js)
- [ ] Backend API (endpoints / SSE)
- [ ] Agents / runtime (graph, prompts)
- [ ] Sandbox / Docker
- [ ] Skills / plugins
- [ ] Config / setup (make, config.yaml, env)
- [ ] Docs
- [ ] CI infra
- [ ] Not sure

## What happened / 实际行为

<!-- 实际发生了什么？包含关键错误日志原文。
     The actual behavior. Include the key error lines verbatim. -->
<!-- e.g. When I do X, I expected Y but I got Z. -->

## Expected behavior / 期望行为

<!-- 你期望发生什么？What did you expect to happen instead? -->

## Steps to reproduce / 复现步骤

<!-- 精确的命令序列。能稳定复现 bug 的最小步骤。
     Exact commands and sequence. Minimal steps that reliably reproduce the problem. -->

1.
2.
3.
4. ...

## Relevant logs / 相关日志

<!-- 粘贴关键日志行（如 logs/gateway.log, logs/frontend.log）。注意脱敏。
     Paste key lines from logs. Redact secrets. -->

```shell
# Paste key log lines here
```

## Environment / 运行环境

<!-- 你怎么跑这个项目的？How are you running it? -->

- Run mode: <!-- Local (make dev) / Docker (make docker-start) / CI / Other -->
- Operating system: <!-- macOS / Linux / Windows / Other -->
- Platform details: <!-- e.g. arm64, zsh -->
- Python version: <!-- e.g. Python 3.12.9 -->
- Node.js version: <!-- e.g. v22.11.0 -->
- pnpm version: <!-- e.g. 10.26.2 -->
- uv version: <!-- e.g. 0.7.20 -->

## Git state / Git 状态

<!-- `git branch --show-current` 和最新 commit SHA 的输出。
     Output of `git branch --show-current` and the latest commit SHA. -->

- branch:
- commit:

## Additional context / 其他上下文

<!-- 截图、相关 issue、配置片段（脱敏）、或任何帮助诊断的信息。
     Screenshots, related issues, config snippets (redacted), or anything else that helps triage. -->
