# Maple Mono Build Pipeline

This package contains the Maple Mono build, CJK, OpenType feature, shared font,
and task-runner implementation.

## Architecture

- `MapleBuildPipeline` in `pipeline.py` owns the top-level build flow, output
  lifecycle, cache behavior, archive behavior, and variant sequencing.
- Process-pool tasks run through top-level `*_job` functions with explicit job
  dataclasses so spawn/pickle behavior stays stable across platforms.
- `font_ops/` contains reusable font naming, metrics, OpenType, merge, and glyph transform operations.
- `resolver.py` converts config file and CLI inputs into a resolved build config,
  runtime output paths, and CJK static base resolution decisions.

## Logging

CLI entrypoints configure one `scripts` logger to write `[LEVEL] [task] message`
records to stderr. Top-level task groups are separated by one blank line. Set
`MAPLE_LOG_LEVEL` to `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` to control
verbosity; the default is `INFO`. `build.py --debug` uses `DEBUG` as the default
for that CLI invocation, while an explicit `MAPLE_LOG_LEVEL` still takes priority.

Machine-readable dry-run output remains on stdout. In particular, CI keeps
`build.py --dry` as JSON-only stdout so it can be piped to tools such as `jq`.
Worker processes configure the same logger before running font jobs.
Downloads with a known content length refresh their percentage and transferred
size on one stderr line instead of emitting one record per chunk.

## Files

| File | Purpose |
| ---- | ------- |
| `config/` | CLI parsing, resolved configuration models, and output path helpers. |
| `pipeline.py` | Public build entrypoint and build orchestration. |
| `resolver.py` | Build configuration and runtime planning. |
| `utils/` | Filesystem, process, download, archive, errors, and version helpers. |
| `font_ops/` | Shared font and glyph operations, transforms, and typed FontTools table boundaries. |
| `cjk/` | CJK data models, JSON/CLI configuration, presets, variable-font operations, and pipeline. |
| `feature/` | Ordered feature catalog, compiler, freeze implementation, and font application. |
| `task/` | Thin task parser and workflow adapters. |

## Pipeline Flow

```mermaid
flowchart TD
    START["build.py"] --> PIPE_MAIN["scripts.pipeline.main(args, version)"]
    PIPE_MAIN --> PARSE["scripts.config.cli.parse_args"]
    PARSE --> RUN["pipeline.run(parsed_args, version)"]
    RUN --> RESOLVE["BuildConfigResolver.resolve"]
    RESOLVE --> PLAN["BuildRuntimeContext.from_config"]

    PLAN --> DRY{"dry run?"}
    DRY -->|"yes, CI"| DRY_CI["print config JSON"]
    DRY -->|"yes, local"| DRY_LOCAL["print resolved_config and runtime_plan"]
    DRY_CI --> END["return"]
    DRY_LOCAL --> END

    DRY -->|"no"| PIPE["MapleBuildPipeline(config, plan).build"]
    PIPE --> PREP["prepare_output_root"]
    PREP --> CACHE_CLEAN{"cache disabled?"}
    CACHE_CLEAN -->|"yes"| CLEAN["remove fonts and fonts/Woff2"]
    CACHE_CLEAN -->|"no"| DIRS
    CLEAN --> DIRS["ensure base output dirs"]
    DIRS --> START_TIMER["start_build_timer"]

    START_TIMER --> BASE_DECISION{"should_build_base_outputs?"}
    BASE_DECISION -->|"yes"| VARIABLE["build_variable_outputs"]
    VARIABLE --> BASE_TTF["build_static_base_outputs"]
    BASE_DECISION -->|"no"| SKIP_BASE["reuse_base_output_cache"]
    BASE_TTF --> NF_DECISION{"should_build_nerd_fonts?"}
    SKIP_BASE --> NF_DECISION

    NF_DECISION -->|"yes"| NF["build_nerd_font_outputs"]
    NF_DECISION -->|"no"| SKIP_NF["skip_nerd_font_outputs"]
    NF --> CJK_DECISION{"should_build_cjk_outputs?"}
    SKIP_NF --> CJK_DECISION

    CJK_DECISION -->|"no"| SKIP_CJK["skip_cjk_outputs"]
    CJK_DECISION -->|"yes"| CJK_MODE{"should_persist_cjk_variable_outputs?"}
    CJK_MODE -->|"yes"| CJK_VAR["build_cjk_variable_outputs"]
    CJK_MODE -->|"no"| CJK_STATIC["build_cjk_static_outputs"]
    SKIP_CJK --> CLEAN_DECISION{"should_cleanup_base_static_formats?"}
    CJK_VAR --> CLEAN_DECISION
    CJK_STATIC --> CLEAN_DECISION

    CLEAN_DECISION -->|"yes"| CLEAN_FORMATS["cleanup_base_static_formats"]
    CLEAN_DECISION -->|"no"| RECORD
    CLEAN_FORMATS --> RECORD["write_build_record"]
    RECORD --> ARCHIVE_DECISION{"should_archive_outputs?"}
    ARCHIVE_DECISION -->|"yes"| ARCHIVE["archive_outputs"]
    ARCHIVE_DECISION -->|"no"| FINISH
    ARCHIVE --> FINISH["finish_build"]
    FINISH --> END
```

## Base Font Flow

```mermaid
flowchart TD
    A["prepare_fontmake_sources"] --> TEMP["Create fonts/temp"]
    TEMP --> SRC["Prepare regular and italic<br/>Glyphs sources once"]
    SRC --> PREP["Fill missing master glyphs,<br/>apply aliases and width transforms"]
    PREP --> CHECK["Validate and materialize one<br/>Designspace/UFO tree per source"]
    CHECK --> ISSUES{"Any aggregated source errors?"}
    ISSUES -->|"yes"| FAIL["Write fonts/source-issues.json<br/>and stop before publishing"]
    ISSUES -->|"no"| VF["fontmake Variable TTF<br/>keep overlaps"]
    ISSUES -->|"no"| TTF["fontmake Static TTF<br/>pathops + transformed components"]
    ISSUES -->|"no"| OTF_DECISION{"OTF requested?"}
    OTF_DECISION -->|"yes"| OTF["fontmake Static OTF<br/>CFF optimize + subroutinize"]
    OTF_DECISION -->|"no"| SKIP_OTF["skip OTF"]

    VF --> H["patch variable features"]
    H --> I["update variable names"]
    I --> J{"italic source?"}
    J -->|"yes"| K["add_ital_axis_to_stat"]
    J -->|"no"| L["skip ital STAT"]
    K --> M["patch_instance weight mapping"]
    L --> M
    M --> N{"line_height != 1?"}
    N -->|"yes"| O["adjust_line_height"]
    N -->|"no"| P["keep source metrics"]
    O --> Q["verify_glyph_width"]
    P --> Q
    Q --> R["add_gasp"]
    R --> S["set_monospace_metadata and publish<br/>fonts/Variable"]

    TTF --> AG["dehint and apply shared<br/>static metadata"]
    OTF --> AG
    AG --> AH["update static names and features"]
    AH --> AI["verify glyph width"]
    AI --> AJ["publish fonts/TTF and fonts/OTF"]
    AJ --> AQ["select_build_files fonts/TTF"]
    AQ --> AR["Create MonoAutohintJob list"]
    AR --> AS["run_process_jobs build_mono_autohint_job"]
    AS --> AT["patch hinted feature set"]
    AT --> AU["ttfautohint with Regular reference"]
    AU --> AV["save fonts/TTF-AutoHint file"]
    AV --> AK{"woff2 wanted and not debug?"}
    AK -->|"yes"| AL["WOFF2 task: convert_to_web<br/>with shared executor"]
    AK -->|"no"| AM["skip WOFF2"]
```

The precompiled `source/MapleMono[wght]-VF.ttf` and
`source/MapleMono-Italic[wght]-VF.ttf` files are reference artifacts only. The
build always generates fresh variable fonts from the corresponding `.glyphs`
sources and never falls back to those binaries.

## Nerd Font Flow

```mermaid
flowchart TD
    A["build_nerd_fonts"] --> B{"nerd_font.enable?"}
    B -->|"no"| Z["return"]
    B -->|"yes"| C["create fonts/NF"]
    C --> D["resolve_font_patcher_usage"]
    D --> E["select_build_files ttf_base_dir"]
    E --> F["Create NerdFontBuildJob list"]
    F --> G["run_process_jobs build_nf_job"]

    G --> H{"use Font Patcher?"}
    H -->|"no"| I["build_nf_by_prebuild_nerd_font"]
    H -->|"yes"| J["build_nf_by_font_patcher"]

    I --> K["Select source/MapleMono-NF-Base suffix"]
    K --> L{"width option set?"}
    L -->|"yes"| M["smart_change_width on NF base<br/>save temporary base"]
    L -->|"no"| N["use NF base directly"]
    M --> O["merge_ttfonts with ttf_base_dir font"]
    N --> O
    O --> P["remove temporary base if needed"]

    J --> Q["run FontPatcher with glyph args<br/>mono/propo and extra args"]
    Q --> R["open generated patcher output"]
    R --> S["remove intermediate output"]
    S --> T["patch nonmarkingreturn width if present"]

    P --> U["build_nf common naming"]
    T --> U
    U --> V["update NF family, style, full,<br/>PostScript, unique id"]
    V --> W{"line_height != 1?"}
    W -->|"yes"| X["adjust_line_height"]
    W -->|"no"| Y["keep metrics"]
    X --> AA["verify width unless Font Patcher or Propo"]
    Y --> AA
    AA --> AB["save fonts/NF output"]
    AB --> AC["set plan.is_nf_built"]
```

## CJK Flow

```mermaid
flowchart TD
    A["MapleBuildPipeline CJK decision"] --> B["resolved CJK build entries"]
    B --> C{"no entries?"}
    C -->|"yes"| Z["skip_cjk_outputs"]
    C -->|"no"| D{"cjk_output_format == variable?"}

    D -->|"yes"| VAR["build_cjk_extended_variable_outputs"]
    VAR --> V0["For each resolved entry"]
    V0 --> V1["entry.build_config<br/>locale_name derives output names"]
    V1 --> V2["ensure_cjk_variable_fonts"]
    V2 --> V3{"preset CJK VFs exist<br/>and clean_cache is false?"}
    V3 -->|"yes"| V4["reuse preset regular and italic CJK VFs"]
    V3 -->|"no"| V5["build_cjk_fonts(vf_only=True)"]
    V4 --> V6["merge_vf core Maple VF + CJK VF"]
    V5 --> V6
    V6 --> V7["name merged VF with locale_name"]
    V7 --> V8["save fonts/Variable-LOCALE"]
    V8 --> V0

    D -->|"no"| STAT["build_cjk_extended_static_outputs"]
    STAT --> S0["For each selected locale"]
    S0 --> S1["Resolve static base profiles<br/>NF-CJK and/or plain CJK"]
    S1 --> S2["Collect required styles from core static fonts"]
    S2 --> S3["BuildRuntimeContext.resolve_cjk_static_base"]
    S3 --> S4{"valid local cache?"}
    S4 -->|"yes"| S8["load static CJK base fonts"]
    S4 -->|"no"| S5{"download supported locale?"}
    S5 -->|"yes"| S6["download cjk-base/{locale}-static.zip<br/>then verify config-derived hash"]
    S5 -->|"no"| S7["skip download"]
    S6 --> S8
    S7 --> S9["build_cjk_fonts from variable source<br/>skip hash validation"]
    S6 -->|"invalid or incomplete"| S9
    S9 --> S8
    S8 --> S10{"required styles present?"}
    S10 -->|"no"| SERR["raise FileNotFoundError"]
    S10 -->|"yes"| S11["Create CJKStaticMergeJob list"]
    S11 --> S12["process_pool: merge core static + CJK static"]
    S12 --> S13["postprocess names with locale_name"]
    S13 --> S14["save fonts/LOCALE or fonts/NF-LOCALE"]
    S14 --> S15{"use_hinted?"}
    S15 -->|"yes"| S16["autohint_static_fonts output dirs"]
    S15 -->|"no"| S17["skip CJK autohint"]
    S16 --> S0
    S17 --> S0

    VAR --> DONE["plan.is_cjk_built = built_any"]
    STAT --> CLEAN["remove fonts/.cjk-temp"]
    CLEAN --> DONE
```

## Finish and Archive Flow

```mermaid
flowchart TD
    A["After NF and CJK decisions"] --> B{"should_cleanup_base_static_formats?"}
    B -->|"no"| D["keep TTF and TTF-AutoHint"]
    B -->|"yes"| E["cleanup_base_static_formats"]
    D --> F["write_build_record"]
    E --> F
    F --> G["write fonts/build-config.json"]
    G --> I{"should_archive_outputs?"}
    I -->|"no"| Q["finish_build"]
    I -->|"yes"| J["archive_outputs<br/>create fonts/archive"]
    J --> K["iterate fonts output entries"]
    K --> L{"archive dir or json?"}
    L -->|"yes"| K
    L -->|"no"| M{"cache mode and base output?"}
    M -->|"yes"| K
    M -->|"no"| N["archive_fonts entry with build config"]
    N --> O["write archive sha256"]
    O --> K
    K --> Q
    Q --> R{"is_ci?"}
    R -->|"yes"| S["return"]
    R -->|"no"| T["print finish time, duration,<br/>family name, freeze config,<br/>absolute fonts path"]
```

## Design Decisions

| Decision | Rationale |
| -------- | --------- |
| Keep `config.cli` pure and use `pipeline.main(args, version)` as the public entrypoint | Allow CLI parsing to be reused without importing or executing the build pipeline. |
| Keep process-pool workers at module top level | Avoid pickling bound methods, closures, or partials. |
| Use explicit job dataclasses | Make each parallel task's inputs visible and serializable. |
| Reuse one executor across the build lifecycle | Avoid repeatedly starting workers between base, web, Nerd Font, and CJK stages; CFF glyph chunks retain a specialized pool for their custom initializer. |
| Keep build configuration and resolution outside `pipeline.py` | Keep the execution pipeline focused on build orchestration. |
| Resolve CJK static bases in `BuildRuntimeContext` | Keep cache, download, hash, and variable fallback decisions outside the execution pipeline. |

## Main Phases

| Phase | Main owner |
| ----- | ---------- |
| Config and CLI | `cli.py`, `BuildConfigResolver` |
| Runtime orchestration | `MapleBuildPipeline` |
| CJK static base resolution | `BuildRuntimeContext.resolve_cjk_static_base` |
| Fontmake source build | `prepare_fontmake_sources`, `compile_fontmake_format` |
| Base static postprocess | `StaticPostprocessJob`, `postprocess_static_font_job` |
| Autohint output | `MonoAutohintJob`, `build_mono_autohint_job` |
| Web font conversion | `convert_to_web` |
| Nerd Font output | `NerdFontBuildJob`, `build_nf_job` |
| CJK extended output | `build_cjk_extended_outputs` and CJK utilities |
| Build record and archive | `MapleBuildPipeline` |
