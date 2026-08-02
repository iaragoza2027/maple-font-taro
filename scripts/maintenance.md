# Maple Mono Maintenance Guide

This is the operational source of truth for maintainers. The other files under `scripts/` document implementation details; use this guide for source changes, generated files, CJK base refreshes, validation, and releases.

## Start safely

Work from a branch and inspect the worktree before changing anything:

```sh
git status --short
uv sync
```

The FontLab `.vfc` files, CJK preset JSON files, and feature source modules are inputs. Designspace/UFO sources, `.fea` files, release archives, and files under `fonts/` are generated outputs. Regenerate them with the task that owns them instead of editing them by hand. Exported root `source/*.glyphs` files are local intermediates and are ignored.

Do not run a release, publish, push, or page synchronization command until the generated diff has been reviewed. `uv run task.py page --sync` updates and commits the landing-page submodule, while `uv run task.py release ...` commits and pushes a version tag.

## Update the Maple Mono source

1. Edit the tracked regular or italic `.vfc` source in FontLab, then export the matching `source/MapleMono[wght].glyphs` or `source/MapleMono-Italic[wght].glyphs` file for each changed style. The exports are temporary inputs for conversion and must not be committed.
2. Regenerate the committed Designspace and UFO sources:

   ```sh
   uv run task.py designspace
   ```

   Review the complete diff under `source/*.designspace` and `source/*.ufo/`. If conversion reports compatibility errors, inspect `fonts/source-issues.json` before continuing.
3. If feature definitions or feature configuration changed in scripts/feature, regenerate all derived feature data:

   ```sh
   uv run task.py fea
   ```

   Review every generated file listed below. Do not keep unrelated churn.
4. Run a focused build before committing source changes:

   ```sh
   uv run build.py --format ttf --debug
   ```

   Add `--cjk cn` only when the change needs a CJK merge. Use `--dry` first when checking resolved inputs, and omit `--cache` after changing generator code, dependency versions, UFO contents, or another input that is not part of the stage cache identity.

Feature generation updates these tracked outputs:

- `source/features/regular.fea`
- `source/features/italic.fea`
- `source/features/cn.fea`
- `source/features/regular_cn.fea`
- `source/features/italic_cn.fea`
- `source/features/README.md` and `source/features/README_CN.md`
- `source/schema.json` and the feature-freeze section in `config.json`
- Generated feature sections in `README.md`, `README_CN.md`, and `README_JA.md`
- The moving-rule list in `scripts/in_browser.py`

For landing-page data, run `uv run task.py page` only when those generated files are part of the change. Use `--woff2` to regenerate web fonts; reserve `--sync` for an intentional remote submodule update and commit.

When deliberately adopting a new Nerd Font upstream release, build a base TTF first and run `uv run task.py nf`. The task checks the upstream release, updates `nerd_font.version` in `config.json`, downloads the matching patcher, and writes the three tracked NF base fonts under `source/`. Use `uv run task.py nf --no-update` when the configured version is already correct and only the local NF outputs need rebuilding.

## Update CJK base fonts

The four source URLs are maintained manually. Update the `source.download.url` value in the relevant preset before starting a build:

| Locale | Preset                         |
| ------ | ------------------------------ |
| CN     | `source/cjk/cn/config-cn.json` |
| TC     | `source/cjk/tc/config-tc.json` |
| JP     | `source/cjk/jp/config-jp.json` |
| KR     | `source/cjk/kr/config-kr.json` |

Keep the URL pinned to the intended upstream release or ref. The workflow does not look up a latest release; it records the URL, the version/ref segment, the input fingerprint, the static-font hash, the ZIP digest, and the build date in `cjk-base-manifest.json`.

### Published update (recommended)

1. Run the manual **Build CJK Base Fonts** workflow. Leave `force_all` disabled for a normal refresh; the workflow compares each preset and tracked `static-<locale>.sha256` file with the published manifest, then builds only changed locales in parallel. Enable `force_all` when bootstrapping the release or deliberately rebuilding every locale.
2. Review the candidate artifact and any hash update pull request created by the workflow. If a PR was opened, merge it so the changed `source/cjk/<locale>/static-<locale>.sha256` files are on the default branch. A PR is not needed when an input change produces the same static hash. The matching ZIPs stay in the 30-day `cjk-base-candidate` artifact until publishing.
3. Run the manual **Publish CJK Base Fonts** workflow with the successful Build workflow run ID after any required hash PR is merged. It verifies the candidate against the merged source URLs, input fingerprints, and hashes, then creates or updates the `cjk-base` release.
4. Confirm the release contains all four assets named `cn-base-static.zip`, `tc-base-static.zip`, `jp-base-static.zip`, and `kr-base-static.zip`, plus `cjk-base-manifest.json`. The generated release description includes the source version/ref, source URL, static hash, build timestamp, and current UTC update date.

The main release workflow checks those four assets and compares the published manifest hashes with the merged repository hashes. A stale or missing `cjk-base` release therefore blocks the normal release instead of silently producing incomplete CJK assets.

### Local check or rebuild

Use the standalone task for a focused local build or when debugging a preset:

```sh
uv run task.py cjk --help
uv run task.py cjk --preset cn
```

The task rebuilds the regular and italic variable bases and the static instances unless `--vf-only` is selected. Generated CJK fonts, temporary source files, and ZIPs under `source/cjk/` are disposable; the tracked `static-<locale>.sha256` files are updated through the Build workflow's hash pull request and should not be hand-edited. Avoid a full CJK build unless the source URL, outline conversion, or generated base artifacts are part of the requested change.

## Create a Maple Mono release

### Prepare and tag locally

1. Finish source, feature, page, and CJK updates, then run the validation baseline below. Make sure the `cjk-base` release is current and its four hashes match the repository.
2. Preview the next version without changing files:

   ```sh
   uv run task.py release minor --dry
   # or
   uv run task.py release major --dry
   ```

3. When the preview is correct, run the matching command and confirm the prompt:

   ```sh
   uv run task.py release minor
   ```

   The task bumps the project version, builds the release inputs, regenerates Fontsource and variable WOFF2 assets, exports `requirements.txt`, copies CN assets, commits the intended release files, pushes the commit, and pushes the new `vX.Y` tag. Use `major` only for a planned major release.

### Build and publish GitHub release assets

The `Build All Formats and Release` workflow starts from a `v*` tag. It builds the base and CJK archive matrices in parallel, validates every expected archive, and creates a draft GitHub release with `uv run task.py publish release`.

For a manual rerun, use **Run workflow** and enter the existing release tag in the required `release_tag` field (for example, `v8.1`). The workflow checks out that tag; it does not create a new tag or infer one from the default branch. Do not pass a branch name or an unpushed tag.

Before handing off a release, verify the draft contains the generated release manifest and all base, Nerd Font, and locale archives. If an asset is missing, fix the matrix/build input and rerun the workflow rather than uploading an ad-hoc archive.

## Validation baseline

Run the smallest checks that cover the change, and run the full baseline before a release:

```sh
uv run build.py --dry
uv run ruff format --check .
uv run ruff check .
uv run pyrefly check
uv run python -m unittest discover -s scripts/tests
```

For CJK-only changes, add the focused suite before downloading large sources:

```sh
uv run python -m unittest \
  scripts.tests.test_cjk_config \
  scripts.tests.test_cjk_cache \
  scripts.tests.test_cjk_executor
```

After any task, inspect `git diff --check`, `git diff --stat`, and `git status --short`. Generated outputs are part of the change only when the task intentionally updates their source of truth.
