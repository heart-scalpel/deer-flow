# AI Collaboration Standards Suite · English Index

> A **project-agnostic** workflow standard for AI assistants (Claude Code / Cursor / Copilot / etc.).
> Full-stack web (Python backend + TS frontend), solo development (you + AI assistant).
> Chinese counterpart: [`README.zh_CN.md`](./README.zh_CN.md)

---

## What This Suite Is For

It standardizes "how to develop a new project in collaboration with an AI assistant." Copy the entire `ai-workflow-standards/` directory into any new project's root, and an AI assistant that reads it will work to a single consistent standard.

**Fits**: full-stack web (Python backend + TS frontend), solo development, where you want RFC + PR + CI + TDD discipline.

**Does not fit**: pure algorithm libraries, embedded, mobile-native, enterprise governance-heavy scenarios (those need a CoC, security disclosure process, multi-team coordination, etc.).

---

## When an AI Assistant First Enters the Project

Read in this order:

1. **`00-operating-principles.en.md`** — operating principles and red lines (highest priority).
2. **`README.md`** (project's own) — project pitch and quick start.
3. **`CLAUDE.md`** / **`ARCHITECTURE.md`** (project's own) — deep context.
4. **The specific workflow file relevant to the task** (per the table below).

---

## File Index

| File | When to read | One-line purpose |
|------|--------------|------------------|
| [`00-operating-principles.en.md`](./00-operating-principles.en.md) | **Always read first** | AI collaboration red lines and defaults |
| [`01-project-init.en.md`](./01-project-init.en.md) | Day one of a new project | Project init checklist |
| [`02-development-workflow.en.md`](./02-development-workflow.en.md) | Before writing code | Branching, commits, TDD, local validation |
| [`03-rfc-process.en.md`](./03-rfc-process.en.md) | Before a big change | When to write an RFC, how |
| [`04-feature-workflow.en.md`](./04-feature-workflow.en.md) | When building a feature | End-to-end idea → merge flow |
| [`05-bug-fix-workflow.en.md`](./05-bug-fix-workflow.en.md) | When fixing a bug | Red-test-first fix flow |
| [`06-pr-workflow.en.md`](./06-pr-workflow.en.md) | When opening a PR | PR template, self-review, merge strategy |
| [`07-ci-cd-standards.en.md`](./07-ci-cd-standards.en.md) | When setting up CI | Required checks, GitHub Actions templates |
| [`08-documentation-policy.en.md`](./08-documentation-policy.en.md) | After code changes | Documentation sync discipline |

Templates (`templates/`):

| Template | Use |
|----------|-----|
| [`templates/PULL_REQUEST_TEMPLATE.md`](./templates/PULL_REQUEST_TEMPLATE.md) | Copy to `.github/pull_request_template.md` |
| [`templates/bug-report.md`](./templates/bug-report.md) | Copy to `.github/ISSUE_TEMPLATE/bug-report.md` |
| [`templates/rfc-template.md`](./templates/rfc-template.md) | Starting point for a lightweight RFC |
| [`templates/design-spec-template.md`](./templates/design-spec-template.md) | Starting point for a full design spec |

---

## Minimal Loading Rules for AI Assistants

If you are an AI assistant and this directory exists at the project root:

1. **At conversation start**: read `00-operating-principles.en.md` (required) + the project's `CLAUDE.md`.
2. **When given a task**: load relevant files per the table below.

| User task | Load |
|-----------|------|
| "Help me initialize the project" | `01` + `templates/*` |
| "I want to add feature X" | `03` (decide if RFC triggers) → `04` → `02` → `06` |
| "There's a bug" / "Bug report came in" | `05` → `02` → `06` |
| "I finished the code" | `02` (local validation) → `08` (doc sync) → `06` (open PR) |
| "Set up CI" | `07` |
| "How do I write this commit" | `02` section 3 |

3. **Conflict priority**: `00` > project's `CLAUDE.md` > specific workflow files (`02-08`) > your default behavior.

---

## How to Use This Suite

### Option A: Drop into a new project

```bash
# Assuming the new project lives at ~/code/my-new-app
cp -r ai-workflow-standards/ ~/code/my-new-app/

# Then in the new project:
cd ~/code/my-new-app
# Move templates/PULL_REQUEST_TEMPLATE.md to .github/
# Move templates/bug-report.md to .github/ISSUE_TEMPLATE/
# Move templates/rfc-template.md and design-spec-template.md to docs/
```

Run the init checklist in `01-project-init.en.md`.

### Option B: Feed to AI as system prompt

Add the entire directory to the AI assistant's "project docs" or "system prompt." Claude Code auto-reads the root `CLAUDE.md`; add a line there:

```markdown
## Workflow

This project follows the AI workflow standards in `ai-workflow-standards/`.
Start by reading `ai-workflow-standards/00-operating-principles.en.md`.
```

### Option C: Use as a contract with your future self

Even solo, treat this as a contract with the future-you. Every rule explains its why, so when future-you returns to it, nothing is opaque.

---

## What This Suite Is Not

- ❌ A complete project template (no concrete code; only process).
- ❌ An enterprise governance framework (no CoC, no security disclosure flow, no multi-team coordination).
- ❌ Best practices for a specific framework (does not pin specific Django / FastAPI / Next.js patterns).
- ❌ Inflexible dogma — when a part doesn't fit a specific project, change it and record why.

## What This Suite Is

- ✅ A scaffold that lets "solo developer + AI assistant" keep engineering discipline.
- ✅ A copyable, modifiable, extensible starting point.
- ✅ A unified context that makes AI behavior predictable and decisions traceable.

---

## Maintenance

- Changes to this suite go through PRs (even on personal projects).
- Editing one file → sync the language counterpart.
- Accumulating new lessons → fold into the relevant file, don't splinter into new fragments.

---

**One-line summary**: copy this into a new project, have the AI read `00` first, and every "how should I write this code" question has a standard answer.
