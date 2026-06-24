<!-- PR 模板 / Pull Request template
     使用方法：拷到 .github/pull_request_template.md
     Usage: copy this file to .github/pull_request_template.md
     不要删除任何节，无内容的留空或写 N/A。
     Do not delete any section; leave blank or write N/A if not applicable. -->

<!-- 关联 issue。用 Fixes / Closes / Resolves 在合并时自动关闭；用 Refs 仅引用。
     Link the issue. Fixes / Closes / Resolves auto-close on merge; Refs just links. -->
Fixes #

## Why

<!-- 为什么开这个 PR？说清两件事：
       - 触发点：什么让你写这个改动？bug、新需求、技术债、生产事故？
       - 解决的痛点：用户感受到的问题，或它解锁了什么。
     非平凡功能请先有 RFC / 设计文档对齐 scope。
     Why open this PR? Cover:
       - The trigger: what made you write this? A bug, a feature need, tech debt, a prod incident?
       - The pain being addressed: user-facing problem, or what it unblocks.
     For non-trivial features, have an RFC / design doc first. -->


## What changed

<!-- 从用户/调用方视角描述变化，不是 code diff 罗列。例如：
       - "Settings 现在有 'Custom endpoint' 字段，默认关闭"
       - "Backend /api/chat 新增 `stream` flag，默认 false"
       - "默认模型从 X 改为 Y — 老用户首次运行会感知"
     Describe the change from a user / caller perspective, not as a code diff. Examples:
       - "Settings now has a 'Custom endpoint' field, off by default"
       - "Backend /api/chat gains a `stream` flag, defaults to false"
       - "Default model changed from X to Y — existing users notice on first run" -->


## Surface area

<!-- 勾选所有适用项，reviewer 据此决定 review 范围。
     Check every box that applies; reviewers use this to scope the review. -->

- [ ] **Frontend UI** — page / component / setting / interaction under `frontend/`
- [ ] **Backend API** — endpoint / SSE event / request-response shape under `backend/`
- [ ] **Agents / LangGraph** — agent node, graph wiring, prompt change (if applicable)
- [ ] **Sandbox** — sandboxed execution or `docker/`
- [ ] **Skills / plugins** — change under skills/plugins directory
- [ ] **Dependencies** — new/upgraded entry in `backend/pyproject.toml` or `frontend/package.json` (say what it buys us)
- [ ] **Default behavior change** — changes existing behavior without opt-in (default model, default setting, data shape)
- [ ] **Docs / tests / CI only** — no runtime behavior change


## Screenshots / Recording

<!-- 如果勾了 "Frontend UI"，附上展示改动入口的截图——
     用户发现这个改动的地方，不只是功能本身的局部截图。
     行为变化前后对比最好。GIF 也行。
     If you checked "Frontend UI", attach screenshots showing the entry point —
     where users discover the change — not just the feature in isolation.
     Before/after is best for behavior changes. Short GIFs welcome. -->


## Bug fix verification

<!-- 仅 bug fix 填；其他类型删掉本节。
     Skip (delete) this section if this PR is not a bug fix.

     Bug 应该编成一个会失败的测试，在修复前是红的。
     Confirm:
       - 复现 bug 的测试路径:
       - 在 main 上跑过吗？红的吗？(yes / no)
       - 在本分支跑过吗？绿的吗？(yes / no)
       - 如果红测试代价过高，解释原因和你的替代验证方案。

     Bugs should be encoded as a failing test that goes red before the fix.
     Confirm:
       - Test path that reproduces the bug:
       - Did it go red on `main`? (yes / no)
       - Did it go green on this branch? (yes / no)
       - If a red test wasn't cheap to write, explain why and what you did instead. -->

- Test path:
- Red on `main`: <!-- yes / no / N/A -->
- Green on this branch: <!-- yes / no -->
- If no red test, why not, and what alternative validation did you do:


## Validation

<!-- 你实际跑过的命令。至少跑你改动区域的检查：
     What you actually ran. Run at least the checks for the area you changed:

     Backend:   cd backend  && make lint && make test
     Frontend:  cd frontend && pnpm format && pnpm lint && pnpm typecheck \
                && BETTER_AUTH_SECRET=local-dev-secret pnpm build && pnpm test
     Frontend E2E (if frontend/ touched): cd frontend && make test-e2e -->

```bash
# Paste the commands you ran and their pass/fail status
```


## AI assistance

<!-- 本项目欢迎 AI 辅助——大多数 PR 都用 AI 工具，这没问题。
     披露是为了让 reviewer 知道审多细。三项必填，不要删本节。
     This project welcomes AI assistance — most PRs here use AI coding tools.
     Disclosing it just helps reviewers calibrate how closely to read the diff.
     Fill all three fields; do not delete the section. -->

**Tool(s) used:** <!-- e.g. Claude Code, Cursor, GitHub Copilot, Codex, Windsurf, or "none" -->

**How you used it:** <!-- e.g. "generated the module from a spec", "autocomplete only",
     "AI wrote tests, I wrote the impl". A prompt or conversation link is great too. -->

- [ ] I've read and understand every line of this change and take responsibility for it — it's not unreviewed AI output.
