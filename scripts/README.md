# Maple Mono Build Pipeline

This package contains the top-level Maple Mono build pipeline, CLI config
resolution, runtime path planning, and shared build helpers.

## Architecture

- `MapleBuildPipeline` in `pipeline.py` owns the top-level build flow, output
  lifecycle, cache behavior, archive behavior, and variant sequencing.
- Process-pool tasks run through top-level `*_job` functions with explicit job
  dataclasses so spawn/pickle behavior stays stable across platforms.
- `util.py` contains helper functions that do not own the pipeline lifecycle,
  including font naming, CJK post-processing, and style/path selection helpers.
- `resolver.py` converts config file and CLI inputs into a resolved build config,
  runtime output paths, and CJK static base resolution decisions.

## Files

| File | Purpose |
| ---- | ------- |
| `cli.py` | CLI entrypoint and argument parsing for `build.py`. |
| `config.py` | Build dataclasses, defaults, normalization, and serialization helpers. |
| `paths.py` | Shared output path and merged variable filename helpers. |
| `pipeline.py` | Main Maple Mono build pipeline, process-pool jobs, and public `main` entrypoint. |
| `resolver.py` | Config-file and CLI override resolution, runtime paths, and CJK static base fallback planning. |
| `util.py` | Pure/helper build functions shared by pipeline phases. |

## Pipeline Flow

```mermaid
flowchart TD
    START["build.py"] --> CLI["scripts.build.cli.main"]
    CLI --> PARSE["parse_args"]
    PARSE --> PIPE_MAIN["pipeline.main(parsed_args, version)"]
    PIPE_MAIN --> CHECK["check_ftcli"]
    CHECK --> RESOLVE["BuildConfigResolver.resolve"]
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
    A["build_variable_fonts"] --> B["Open source variable fonts<br/>MapleMono[wght]-VF.ttf<br/>MapleMono-Italic[wght]-VF.ttf"]
    B --> C["rename_glyph_name<br/>using .glyphs mapping"]
    C --> D["alias_codepoints"]
    D --> E{"width option set?"}
    E -->|"yes"| F["smart_change_width"]
    E -->|"no"| G["skip width transform"]
    F --> H["patch variable features"]
    G --> H
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
    R --> S["save fonts/Variable family VF"]
    S --> T["ftcli fix monospace fonts/Variable"]
    T --> U["instantiate_base_static_fonts"]

    U --> V["Read named wght instances<br/>from regular variable font"]
    V --> W["Create MapleStaticInstanceJob<br/>for regular and italic VFs"]
    W --> X["create_font_executor"]
    X --> Y["top-level worker<br/>instantiate_maple_static_font_job"]
    Y --> Z["get_static_worker_font cache"]
    Z --> AA["instantiateVariableFont static=True"]
    AA --> AB["save fonts/TTF raw static fonts"]

    AB --> AC["build_base_fonts"]
    AC --> AD["select_build_files fonts/TTF"]
    AD --> AE["Create MonoBuildJob list"]
    AE --> AF["run_process_jobs build_mono_job"]
    AF --> AG["ftcli fix italic-angle, monospace,<br/>strip names, correct contours,<br/>dehint, transformed components"]
    AG --> AH["update static names and features"]
    AH --> AI["verify glyph width"]
    AI --> AJ["save final fonts/TTF file"]
    AJ --> AK{"woff2 wanted and not debug?"}
    AK -->|"yes"| AL["ftcli converter ft2wf"]
    AK -->|"no"| AM["skip WOFF2"]
    AL --> AN{"otf wanted and not debug?"}
    AM --> AN
    AN -->|"yes"| AO["ftcli ttf2otf<br/>correct contours<br/>cff set-names"]
    AN -->|"no"| AP["skip OTF"]

    AP --> AQ["select_build_files fonts/TTF"]
    AQ --> AR["Create MonoAutohintJob list"]
    AR --> AS["run_process_jobs build_mono_autohint_job"]
    AS --> AT["patch hinted feature set"]
    AT --> AU["ttfautohint with Regular reference"]
    AU --> AV["save fonts/TTF-AutoHint file"]
```

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
    S15 -->|"yes"| S16["ftcli ttf autohint output dirs"]
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
| Keep the public `pipeline.main(parsed_args, version)` entrypoint | Preserve compatibility with `scripts.build.cli` and `build.py`. |
| Keep process-pool workers at module top level | Avoid pickling bound methods, closures, or partials. |
| Use explicit job dataclasses | Make each parallel task's inputs visible and serializable. |
| Keep helper logic in `util.py` | Reduce pipeline size while keeping lifecycle and worker code in one place. |
| Resolve CJK static bases in `BuildRuntimeContext` | Keep cache, download, hash, and variable fallback decisions outside the execution pipeline. |

## Main Phases

| Phase | Main owner |
| ----- | ---------- |
| Config and CLI | `cli.py`, `BuildConfigResolver` |
| Runtime orchestration | `MapleBuildPipeline` |
| CJK static base resolution | `BuildRuntimeContext.resolve_cjk_static_base` |
| Variable font build | `build_variable_fonts` |
| Static TTF instantiation | `MapleStaticInstanceJob`, `instantiate_maple_static_font_job` |
| Base TTF postprocess | `MonoBuildJob`, `build_mono_job` |
| Autohint output | `MonoAutohintJob`, `build_mono_autohint_job` |
| Nerd Font output | `NerdFontBuildJob`, `build_nf_job` |
| CJK extended output | `build_cjk_extended_outputs` and CJK utilities |
| Build record and archive | `MapleBuildPipeline` |
