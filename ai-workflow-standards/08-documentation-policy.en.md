# 08 · Documentation Policy

> **Docs are not backfill — they are written alongside code.** Code changed but docs not updated = work is not done.
> Chinese counterpart: `08-documentation-policy.zh_CN.md`.

---

## 1. Documentation Tiers

| Document | Audience | When to update | Purpose |
|----------|----------|----------------|---------|
| `README.md` | First-time visitor | Any user-visible behavior change | Project pitch, quick start, doc navigation |
| `ARCHITECTURE.md` | Anyone wanting the design | Architecture-level change | High-level diagram, module responsibilities, data flow |
| `CLAUDE.md` | AI assistants (and you reading it) | Command / workflow / internal system change | Deep context: architecture, commands, conventions, gotchas |
| `docs/CONFIGURATION.md` | Users configuring the project | Config field change | Every `config.yaml` field's meaning and default |
| `docs/API.md` | API callers | Endpoint change | Method, params, response per endpoint |
| `docs/CONTRIBUTING.md` | Contributors | Dev workflow change | Link to this standards suite, local setup, commit conventions |
| `docs/CHANGELOG.md` | Users upgrading | Every release | List of changes per version |
| `docs/RFC-INDEX.md` | Anyone studying decision history | Every new RFC | RFC list (see section 7 of `03-rfc-process.en.md`) |
| `docs/postmortems/` | Anyone learning from incidents | After major incidents | Timeline, impact, root cause, action items |

## 2. The Role of README.md

The README is the project's **front door**. Required:

- **3 lines max to say what the project is**: pitch, what it solves, who it's for.
- **5 minutes max to a running app**: complete install, configure, start commands.
- **Clear doc navigation**: links to ARCHITECTURE / API / CONFIGURATION / CONTRIBUTING.

Anti-patterns:
- ❌ README goes into architecture detail (belongs in ARCHITECTURE).
- ❌ README explains dev workflow (belongs in CONTRIBUTING).
- ❌ README documents config field details (belongs in CONFIGURATION).
- ❌ README has no quick start.
- ❌ README hasn't been updated in months.

## 3. The Role of CLAUDE.md

CLAUDE.md (or AGENTS.md, .cursor/rules) is the **project-level system prompt** for AI assistants. Required:

- **Architecture overview**: module breakdown, dependency direction, data flow.
- **Common commands**: exact commands for lint / test / build / dev.
- **Code conventions**: style, naming, file organization.
- **Red lines**: architectural layering, dependency direction, security constraints.
- **Gotchas**: easy-to-trap behaviors, non-obvious semantics.
- **Testing strategy**: how to write tests, what to run, runtime gates like blocking-IO checks.

After every code change, **ask yourself**: does this change require a CLAUDE.md update?

- Changed module structure → yes.
- Added a new command → yes.
- Changed internal conventions → yes.
- Added a new gotcha → yes.
- Pure implementation detail → usually no.

## 4. Doc Sync Discipline

### Principle

**Docs and code land in the same commit / PR.** "Code first, docs later" → the docs never get written.

### Decision Tree

```
Code change →
  User-visible behavior change?
    → yes: update README
  Architecture / module structure / commands / workflow change?
    → yes: update ARCHITECTURE and/or CLAUDE.md
  Config field change?
    → yes: update config.example.yaml + CONFIGURATION.md
  API change?
    → yes: update API.md (if OpenAPI auto-gen, verify the gen result)
  Dev workflow change?
    → yes: update CONTRIBUTING.md
  Dependency change?
    → yes: update README prerequisites + (CI config)
  None of the above?
    → usually pure implementation detail, no doc update needed
```

## 5. CHANGELOG Discipline

`docs/CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/):

```markdown
# Changelog

## [Unreleased]

### Added
- New feature X

### Changed
- Default Y changed from A to B

### Deprecated
- Z is being removed; use W instead

### Removed
- Removed V

### Fixed
- Fixed bug U

### Security
- Fixed CVE-XXXX-XXXXX

## [1.2.0] - 2026-06-15
...
```

### When to write CHANGELOG

- Every PR merged to main → add a line under `[Unreleased]`.
- Every release → rename `[Unreleased]` to `[version] - date`, create a fresh `[Unreleased]`.

### What to record

- User-visible feature / behavior changes (added / changed / deprecated / removed / fixed / security).
- **Do not record** internal refactors, test additions, CI config (unless it affects release artifacts).

## 6. API Documentation

### Prefer auto-generation

- Backend: FastAPI → `GET /openapi.json` → Swagger UI / Redoc.
- Frontend: tRPC / Zod → auto-derived schema.
- gRPC: protobuf → buf generator.

### Hand-written supplement

Auto-gen can tell callers "params and return shape," **not**:

- When to use / not use the endpoint.
- Boundary case behavior (rate limits, retries, idempotency).
- Business meaning of error codes.

Hand-write these in `docs/API.md` or in OpenAPI `description` fields.

## 7. Code Comments

### Default: no comments

Code is **comment-free by default**. Clear naming + complete types + test coverage = self-explanatory.

### When comments are required

Comments explain **why**, not **what**:

```python
# Bad
i += 1  # increment i by 1

# Good
# Deadline is +7 days because the legal review window requires a week minimum.
deadline = today + timedelta(days=7)
```

**Must-comment scenarios**:
- Non-obvious business rules, compliance constraints, external contracts.
- Workarounds (link to the relevant issue / RFC).
- Performance optimization rationale ("dict instead of list for O(1) lookup").
- Magic number provenance.
- Counter-intuitive behavior ("this looks weird because of historical reason X").

### Do not write

- Comments that duplicate what code already says (`# set name to empty` above `name = ""`).
- References to obsolete issues / PRs (links will rot).
- Temporary "modified X" notes (those belong in commit messages).

## 8. README Documentation Navigation Example

```markdown
## Documentation

- [Architecture](docs/ARCHITECTURE.md) — high-level design and module layout
- [Configuration](docs/CONFIGURATION.md) — every config field explained
- [API reference](docs/API.md) — endpoint catalog
- [Contributing](docs/CONTRIBUTING.md) — dev setup and workflow
- [Changelog](docs/CHANGELOG.md) — release history
- [RFCs](docs/rfc-index.md) — design decision history
```

## 9. Documentation Self-Review

Add one item to your PR self-review checklist:

- [ ] Did this change require a doc update? If yes, was it done?

If a reviewer (including future you) asks "why doesn't the doc mention X" → doc sync was missed.

## 10. Stale Doc Cleanup

- Quarterly: walk through `docs/` and delete outdated content.
- Deleted content that still has value → move to `docs/archive/`.
- Code that references outdated docs → update together.

## 11. Multilingual Documentation

For bilingual projects (this standards suite uses CN/EN pairs):

- **Align structure in each pair**: CN and EN share the same sections in the same order for easy cross-reference.
- **Keep code samples English**: avoid CN/EN drift in code strings and comments.
- **Sync updates**: changing one file requires changing the other immediately. No "CN first, EN translated later."
- **Cross-link at the top**: each file links to its counterpart at the top.

---

**One-line summary**: documentation is code's **shadow** — when code moves, the shadow must move with it. Code changed, docs unchanged → the project becomes a maze only you can read, and future you (and AI assistants) will get lost.
