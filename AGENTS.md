# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project Overview

Maple Mono is an open-source monospace font project. The repository contains:

- Font source files and build scripts for Maple Mono.
- OpenType feature generation logic.
- Chinese and Nerd Font merge/build tasks.
- The Astro/Solid landing page in `maple-font-page/`.

Prefer small, maintainable changes that follow the existing project structure.

## Language

- Write code, comments, commit messages, and documentation in English.
- If interacting with the repository owner in chat, respond in Chinese unless asked otherwise.

## Repository Layout

- `build.py`: Main font builder and CLI for custom builds.
- `task.py`: Task runner for feature generation, CN rebuilds, page data updates, publishing, and merge utilities.
- `config.json`: Default build configuration, validated by `source/schema.json`.
- `requirements.txt` and `pyproject.toml`: Python dependencies.
- `source/`: Font sources, generated feature files, Python build logic, schema, and CN assets.
- `source/py/feature/`: Python modules that generate OpenType feature rules.
- `source/features/`: Generated `.fea` files and feature documentation.
- `source/py/task/`: Build task implementations.
- `fonts/`: Generated font outputs. Treat as build artifacts unless a task explicitly requires them.
- `maple-font-page/`: Astro 5 site with Solid components and UnoCSS.
- `resources/`: Images and visual assets used by README/docs.

## Development Setup

Use the existing toolchains:

```sh
uv sync
```

For environments without `uv`:

```sh
pip install -r requirements.txt
```

For the landing page:

```sh
cd maple-font-page
bun install
```

Do not introduce a new package manager or dependency system unless the maintainer asks for it.

## Common Commands

Python/font tasks:

```sh
uv run build.py --dry
uv run build.py --ttf-only --debug
uv run build.py --ttf-only --cn --debug
uv run task.py fea
uv run task.py page
uv run task.py merge
uv run task.py release minor --dry
```

Landing page tasks:

```sh
cd maple-font-page
bun run dev
bun run build
bun run format
```

Use the smallest command that validates the change. Full font builds can be slow and may download large assets.

## Validation Guidelines

- For Python syntax-only changes, run targeted checks such as:

```sh
python -m compileall build.py task.py source/py
```

- For feature generation changes, run:

```sh
uv run task.py fea
```

Then inspect generated `.fea`, README, schema, config, and `source/py/in_browser.py` diffs.

- For build configuration or font build behavior, start with:

```sh
uv run build.py --dry
```

Run heavier builds only when necessary.

- For `maple-font-page/` changes, run:

```sh
cd maple-font-page
bun run format
bun run build
```

If dependencies are missing and network access is unavailable, clearly report which validation could not be run.

## Generated Files and Artifacts

Some files are generated together. Keep them synchronized:

- Changes under `source/py/feature/` often require `uv run task.py fea`.
- `uv run task.py fea` can update:
  - `source/features/*.fea`
  - `source/features/README.md`
  - `source/schema.json`
  - `config.json`
  - `README.md`
  - `README_CN.md`
  - `README_JA.md`
  - `source/py/in_browser.py`
- `uv run task.py page` updates landing page data from built fonts.
- Font outputs under `fonts/` are generated artifacts. Do not edit them manually.

Avoid committing generated churn unless it is required by the source change.

## Font Build Notes

- CN builds can download large base font archives and take a long time.
- Nerd Font builds may depend on external patcher assets or FontForge.
- `config.json` CLI options are overridden by `build.py` arguments.
- The CN version is disabled by default. Enable with `--cn` only when the change requires it.
- Use `--debug`, `--ttf-only`, and `--least-styles` for faster local validation when appropriate.
- Do not change font naming, versioning, or release packaging behavior casually.

## Python Code Style

- Keep functions focused and names explicit.
- Prefer existing helpers in `source/py/utils.py`, `source/py/task/_utils.py`, and nearby modules.
- Avoid adding dependencies for small parsing or file operations.
- Use structured parsing for JSON/YAML/font data instead of ad hoc string manipulation.
- Keep generated-output ordering stable to reduce noisy diffs.
- Add comments only when they explain non-obvious font/build logic.

## Frontend Code Style

The landing page uses Astro, Solid 1.x, TypeScript, and UnoCSS.

- Follow existing component patterns in `maple-font-page/src/`.
- Prefer existing UI components in `maple-font-page/src/components/ui/`.
- Keep localized text in the existing locale files.
- Use UnoCSS utilities and project presets instead of one-off CSS when possible.
- Do not add marketing-style landing sections unless the requested change needs them.
- Validate responsive behavior for visible UI changes.

## Dependency and Network Policy

- Do not add Python, Bun, or frontend dependencies without a clear need.
- Prefer existing libraries already declared in `pyproject.toml`, `requirements.txt`, or `maple-font-page/package.json`.
- Commands that download CN base fonts, Nerd Font assets, npm/bun packages, or release data require network access. Ask for approval when the environment blocks network access.

## Editing Rules

- Preserve user changes. Check `git status --short` before broad edits.
- Keep changes scoped to the requested task.
- Do not run destructive cleanup commands unless explicitly requested.
- Do not manually edit binary font/source assets unless the task is specifically about those assets.
- Do not rewrite generated files by hand when a project task can regenerate them.

## Review Checklist

Before finishing:

- Confirm the changed files are intentional with `git diff --stat` or `git status --short`.
- Run the smallest relevant validation command.
- Note any skipped validation and why.
- Mention generated files if the change required regeneration.
