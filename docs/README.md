# Project Documentation

This directory contains architecture documentation, coding standards, decision records, and contributor-facing guidance for the `agentic-systems-lab` monorepo.

## Contents

| Path | Description |
| --- | --- |
| `ARCHITECTURE.md` | Umbrella architecture — system-level map linking the per-package deep dives |
| `architecture-runtime.md`, `architecture-ui.md`, `architecture-eval.md`, `architecture-tools.md` | Per-package architecture deep dives |
| `ROADMAP.md` | Epics shipped (1/2/3/5/6), Epic 4 tombstone, Sprint B items, proposed Epic 7+ |
| `KNOWN_LIMITATIONS.md` | Honest accounting of items shipped with caveats |
| `MIGRATIONS.md` | Breaking changes since v0.3.0 |
| `ONBOARDING.md` | Canonical 5-minute to 1-hour onboarding path |
| `CODING_STANDARDS.md` | Coding standards and style guidelines |
| `GLOSSARY.md` | Domain-specific term definitions |
| `adr/` | Architecture Decision Records — start at `adr/ADR-INDEX.md` |
| `../CHANGELOG.md` | User-facing changelog (at repo root) |
| `../CONTRIBUTING.md` | Monorepo contribution policy (at repo root) |

## Table of Contents
- [Purpose](#purpose)
- [Quick start](#quick-start)
- [How to add or update runtime role docs](#how-to-add-or-update-runtime-role-docs)
- [Previewing docs (Windows / PowerShell)](#previewing-docs-windows--powershell)
- [Contacts & references](#contacts--references)

## Purpose
This directory holds architecture documentation, decision records, and contributor-facing guidance for documentation PRs. Aim for clarity, reproducibility, and reviewer-friendly diffs.

## Quick start
- Add any new doc pages under `docs/` (follow file naming conventions).
- Open a pull request and include a concise summary of changed docs, screenshots, or sample outputs when useful.

### Contributor todo (minimal)
- [ ] Add supporting docs under `docs/` (if applicable)
- [ ] Run local docs preview (PowerShell)
- [ ] Attach screenshots / sample outputs to PR
- [ ] Request reviewer(s) and assign labels

## How to add or update runtime role docs
1. Document new runtime-facing roles in the relevant architecture or workflow guide.
2. Add supporting docs in `docs/` if the role needs detailed usage or examples.
3. Update any tests or fixtures that reference the role name.
4. Submit a docs PR with a concise verification summary.

## Previewing docs (Windows / PowerShell)

```powershell
# Install a light markdown server (one-time)
npm install -g markserv

# Run preview from repo root (serves README.md at http://localhost:3000)
markserv docs --port 3000
```

```powershell
# Alternatively, open a single file in the default Windows markdown previewer:
Start-Process docs\README.md
```

## Contacts & references
- Maintainers: see repository CODEOWNERS and PR templates.
- Runtime role documentation: architecture and workflow guides
- Runtime package docs: `agentic-workflows-v2/docs/README.md`
