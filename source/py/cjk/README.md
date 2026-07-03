# Maple Mono CJK Build Pipeline

This package contains the shared CJK build pipeline and the built-in CN/JP
presets.

## Files

| File | Purpose |
| ---- | ------- |
| `builder.py` | Shared configurable CJK build pipeline and CLI argument handling. |
| `cn.py` | Built-in CN preset using `source/cn/WenYuanRoundedSCVF.ttf`. |
| `jp.py` | Built-in JP preset using `source/jp/ResourceHanRoundedJP-VF.otf`. |
| `vf.py` | Shared variable-font, master-merge, and italic helper logic. |

## Data Flow

```mermaid
flowchart TD
    A["Source CJK variable font<br/>glyf or CFF2"] --> B["Select Unicode ranges<br/>cn / jp / tc / kr / custom"]
    B --> C["Subset source font<br/>drop configured tables"]
    C --> D{"Outline format"}

    D -->|"glyf"| G1["Instantiate source masters<br/>output weights 100 / 400 / 800"]
    G1 --> G2["Merge masters into<br/>MapleMono-CN-feature-VF.ttf"]
    G2 --> G3["Build gvar deltas<br/>from source master geometry"]
    G3 --> G4["Finalize regular VF"]

    G2 --> I1["Instantiate feature masters"]
    G1 --> I2["Slant source masters"]
    I1 --> I3["Build italic feature VF"]
    I2 --> I4["Merge slanted masters"]
    I3 --> I4
    I4 --> I5["Finalize italic VF"]

    D -->|"CFF2"| C1["Pin non-weight axes<br/>preserve source CFF2 outlines"]
    C1 --> C2["Finalize regular CFF2 VF"]
    C2 --> C3["Finalize italic CFF2 VF metadata"]

    G4 --> S["Instantiate static fonts"]
    I5 --> S
    C2 --> S
    C3 --> S
    S --> T["Always output TTF static fonts<br/>CFF static instances are converted to glyf"]
    T --> U["Write sha256 and zip archive"]
```

## Master Mapping

`CJKSourceConfig.masters` is keyed by output weights:

```json
{
  "100": { "wght": 220, "ital": 0 },
  "400": { "wght": 470, "ital": 0 },
  "800": { "wght": 900, "ital": 0 }
}
```

The keys are Maple Mono output weights. The values are source-font axis
locations. This lets the pipeline map source geometry directly onto
`source/MapleMono-CN-feature-VF.ttf`, which remains the source of truth for
weight axis metadata and named static instances.

## Design Decisions

| Decision | Rationale |
| -------- | --------- |
| Subset before instantiating masters | Avoid expensive work for glyphs that will be discarded. |
| Keep `MapleMono-CN-feature-VF.ttf` as the metadata source | Reuse weight axis names, static instance names, and feature glyphs consistently. |
| Use a glyf master-merge path for glyf sources | Static masters provide `glyf`/`hmtx`; the pipeline computes `gvar` deltas for added glyphs. |
| Preserve CFF2 variable output for CFF2 sources | Avoid converting variable CFF2 outlines before static instantiation. |
| Always emit static fonts as TTF | Static CFF instances are converted to `glyf` before saving. |
| Keep built-in presets thin | CN and JP presets only define source paths, master mappings, Unicode filters, naming, and output layout. |

## Built-in Presets

| Preset | Source | Outline | Notes |
| ------ | ------ | ------- | ----- |
| CN | `source/cn/WenYuanRoundedSCVF.ttf` | glyf | Merges source masters into the Maple feature VF and emits CN variable/static outputs. |
| JP | `source/jp/ResourceHanRoundedJP-VF.otf` | CFF2 | Keeps CFF2 variable output; static fonts are instantiated and converted to TTF. |

## Main Phases

| Phase | Main functions |
| ----- | -------------- |
| Unicode selection | `unicode_config_from_spec`, `get_allowed_codepoints` |
| Subsetting | `prepare_source_subset`, `subset_font` |
| Master instantiation | `instantiate_masters_from_vf`, `build_master_locations` |
| glyf merge | `merge_cjk_masters_into_vf`, `merge_masters_into_vf` |
| CFF2 variable build | `build_cff2_cjk_fonts`, `cff2_variable_axis_limits` |
| Italic build | `make_italic_variable_font`, `make_italic_master_file` |
| Static output | `instantiate_static_fonts`, `convert_cff_static_to_glyf` |
| Final cleanup | `finalize_variable_font`, `finalize_cff2_variable_font`, `cleanup_static_font_file` |
