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
- `resolver.py` converts config file and CLI inputs into a resolved build config
  plus runtime output paths.

## Files

| File | Purpose |
| ---- | ------- |
| `cli.py` | CLI entrypoint and argument parsing for `build.py`. |
| `config.py` | Build dataclasses, defaults, normalization, and serialization helpers. |
| `paths.py` | Shared output path and merged variable filename helpers. |
| `pipeline.py` | Main Maple Mono build pipeline, process-pool jobs, and public `main` entrypoint. |
| `resolver.py` | Config-file and CLI override resolution into runtime-ready settings. |
| `util.py` | Pure/helper build functions shared by pipeline phases. |

## Pipeline Flow

```mermaid
flowchart TD
    START["build.py"] --> CLI["source.py.build.cli.main"]
    CLI --> PARSE["parse_args"]
    PARSE --> PIPE_MAIN["pipeline.main(parsed_args, version)"]
    PIPE_MAIN --> CHECK["check_ftcli"]
    CHECK --> RESOLVE["BuildConfigResolver.resolve"]
    RESOLVE --> PLAN["RuntimeBuildPlan.from_config"]

    PLAN --> DRY{"dry run?"}
    DRY -->|"yes, CI"| DRY_CI["print config JSON"]
    DRY -->|"yes, local"| DRY_LOCAL["print resolved_config and runtime_plan"]
    DRY_CI --> END["return"]
    DRY_LOCAL --> END

    DRY -->|"no"| PIPE["MapleBuildPipeline(config, plan).build"]
    PIPE --> PREP["_prepare_outputs"]
    PREP --> CACHE_CLEAN{"cache disabled?"}
    CACHE_CLEAN -->|"yes"| CLEAN["remove fonts and fonts/Woff2"]
    CACHE_CLEAN -->|"no"| DIRS
    CLEAN --> DIRS["ensure base output dirs"]
    DIRS --> START_TIMER["_start_build"]

    START_TIMER --> BASE_DECISION{"cache enabled and has_cache?"}
    BASE_DECISION -->|"yes"| SKIP_BASE["skip base rebuild"]
    BASE_DECISION -->|"no"| BASE_OUTPUTS["_build_base_outputs"]
    BASE_OUTPUTS --> VARIABLE["build_variable_fonts"]
    VARIABLE --> BASE_TTF["build_base_fonts"]
    BASE_TTF --> VARIANTS["_build_variant_outputs"]
    SKIP_BASE --> VARIANTS

    VARIANTS --> NF["build_nerd_fonts"]
    NF --> CJK["build_cjk_extended_outputs"]
    CJK --> CLEAN_FORMATS["cleanup_unselected_base_formats"]
    CLEAN_FORMATS --> RECORD["_write_build_config"]

    RECORD --> ARCHIVE["_archive_outputs"]
    ARCHIVE --> FINISH["_finish_build"]
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
    A["build_cjk_extended_outputs"] --> B["selected locales from config"]
    B --> C{"no locales?"}
    C -->|"yes"| Z["return"]
    C -->|"no"| D["persist_variable = cjk_output_format == variable"]
    D --> E["For each locale"]

    E --> F{"static output?"}
    F -->|"yes"| G["build_cjk_extended_static_fonts_from_cache"]
    G --> H["source/cjk/{locale}/static"]
    H --> I["Resolve static base profiles<br/>NF-CJK when NF was built;<br/>plain CJK also when cjk_both"]
    I --> J["Collect profile base fonts by style<br/>fonts/NF MapleMono-NF or TTF MapleMono"]
    J --> K{"all core styles present in cache<br/>and clean_cache is false?"}
    K -->|"no"| L["generate source/cjk/{locale}/static<br/>from locale CJK variable fonts"]
    L --> LC{"source/cjk/{locale}/MapleMono-{Locale} VFs exist?"}
    LC -->|"no"| LD["raise FileNotFoundError<br/>and exit build"]
    LC -->|"yes"| LE["process_pool: instantiate_static_font_job<br/>for regular and italic instances"]
    LE --> LF["reload generated static cache"]
    LF --> LG{"required styles generated?"}
    LG -->|"no"| LD
    LG -->|"yes"| M
    K -->|"yes"| M["Create CJKStaticMergeJob list<br/>for each base profile"]
    M --> N["process_pool: merge_cached_cjk_static_font_job"]
    N --> NA["merge_ttfonts core static + cached CJK static"]
    NA --> NB["postprocess CJK static font"]
    NB --> O["save fonts/NF-LOCALE or fonts/LOCALE static output"]
    O --> P{"use_hinted?"}
    P -->|"yes"| Q["ftcli ttf autohint fonts/LOCALE"]
    P -->|"no"| R["skip CJK autohint"]
    Q --> S["built_any = True"]
    R --> S
    S --> E

    F -->|"no"| T{"persist variable?"}
    T -->|"yes"| U["output dir fonts/Variable-LOCALE"]
    T -->|"no"| V["output dir fonts/.cjk-temp/LOCALE"]
    U --> W["build_cjk_extended_variable_fonts"]
    V --> W

    W --> X["build_preset_config locale"]
    X --> XA["load source/cjk/config-{locale}.json<br/>locale_name derives CJK base paths"]
    XA --> Y["ensure_cjk_variable_fonts"]
    Y --> AA{"source/cjk/{locale}/MapleMono-{Locale} VFs exist<br/>and clean_cache false?"}
    AA -->|"yes"| AB["reuse preset locale CJK regular and italic VFs"]
    AA -->|"no"| AC["build_cjk_fonts preset vf_only=True"]
    AC --> AD{"CJK VFs generated?"}
    AD -->|"no"| AE["print skip warning<br/>return None"]
    AD -->|"yes"| AF["use generated CJK VFs"]
    AB --> AG["merge regular and italic pairs"]
    AF --> AG

    AG --> AH["merge_vf core Maple VF + CJK VF"]
    AH --> AI["update merged variable names"]
    AI --> AJ{"fix_meta_table?"}
    AJ -->|"yes"| AK["apply_cjk_meta_table"]
    AJ -->|"no"| AL["skip meta table"]
    AK --> AM["save merged variable output"]
    AL --> AM
    AM --> AN{"merged paths returned?"}
    AE --> E
    AN -->|"no"| E
    AN -->|"yes"| AO["built_any = True"]

    AO --> AP{"persist variable?"}
    AP -->|"yes"| E
    AP -->|"no"| AQ["instantiate_cjk_extended_static_fonts"]
    AQ --> AR["for regular and italic merged VFs"]
    AR --> AS["feature_weight_instances"]
    AS --> AT["instantiateVariableFont static=True"]
    AT --> AU["postprocess_cjk_extended_static_font"]
    AU --> AV["save fonts/LOCALE static output"]
    AV --> AW["remove locale temp variable dir"]
    AW --> E

    E --> AX["After all locales"]
    AX --> AY{"not persist_variable?"}
    AY -->|"yes"| AZ["remove fonts/.cjk-temp"]
    AY -->|"no"| BA["keep variable output dirs"]
    AZ --> BB["plan.is_cjk_built = built_any"]
    BA --> BB
```

## Finish and Archive Flow

```mermaid
flowchart TD
    A["After variant outputs"] --> B["cleanup_unselected_base_formats"]
    B --> C{"ttf format wanted?"}
    C -->|"yes"| D["keep TTF and TTF-AutoHint"]
    C -->|"no"| E["remove TTF and TTF-AutoHint"]
    D --> F["_write_build_config"]
    E --> F
    F --> G["write fonts/build-config.json"]
    G --> H["_archive_outputs"]
    H --> I{"archive enabled?"}
    I -->|"no"| Q["_finish_build"]
    I -->|"yes"| J["create fonts/archive"]
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
| Keep the public `pipeline.main(parsed_args, version)` entrypoint | Preserve compatibility with `source.py.build.cli` and `build.py`. |
| Keep process-pool workers at module top level | Avoid pickling bound methods, closures, or partials. |
| Use explicit job dataclasses | Make each parallel task's inputs visible and serializable. |
| Keep helper logic in `util.py` | Reduce pipeline size while keeping lifecycle and worker code in one place. |
| Reuse cached static CJK bases when possible | Avoid unnecessary variable CJK merge work for static-only CJK builds. |

## Main Phases

| Phase | Main owner |
| ----- | ---------- |
| Config and CLI | `cli.py`, `BuildConfigResolver` |
| Runtime orchestration | `MapleBuildPipeline` |
| Variable font build | `build_variable_fonts` |
| Static TTF instantiation | `MapleStaticInstanceJob`, `instantiate_maple_static_font_job` |
| Base TTF postprocess | `MonoBuildJob`, `build_mono_job` |
| Autohint output | `MonoAutohintJob`, `build_mono_autohint_job` |
| Nerd Font output | `NerdFontBuildJob`, `build_nf_job` |
| CJK extended output | `build_cjk_extended_outputs` and CJK utilities |
| Build record and archive | `MapleBuildPipeline` |
