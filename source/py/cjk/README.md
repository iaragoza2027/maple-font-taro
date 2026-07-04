# Maple Mono CJK Build Pipeline

This package contains the shared CJK build pipeline and the built-in CN/JP
presets.

## Files

| File | Purpose |
| ---- | ------- |
| `config.py` | Shared dataclasses, Unicode presets, JSON loading, and CLI argument parsing. |
| `builder.py` | Shared configurable CJK build pipeline and build entrypoints. |
| `cn.py` | Built-in CN preset using `source/cn/WenYuanRoundedSCVF.otf`. |
| `jp.py` | Built-in JP preset using `source/jp/ResourceHanRoundedJP-VF.otf`. |
| `verify_cff_to_glyf.py` | Fast verifier that contrasts independent cu2qu against joint multi-master conversion on a temporary tiny subset. |
| `vf.py` | Shared variable-font, master-merge, and italic helper logic. |

## Data Flow

```mermaid
flowchart TD
    A["Source CJK variable font<br/>glyf or CFF2"] --> B["Select Unicode ranges<br/>cn / jp / tc / kr / custom"]
    BASE["Maple feature VF<br/>weight metadata and feature glyphs"]
    B --> C["Subset source font<br/>drop configured tables"]

    subgraph SP["process_pool: instantiate source masters"]
        S100["100 source master<br/>static instance"]
        S400["400 source master<br/>static instance"]
        S800["800 source master<br/>static instance"]
    end

    C --> S100
    C --> S400
    C --> S800

    S100 --> F{"Outline format"}
    S400 --> F
    S800 --> F
    F -->|"glyf"| G0["Scale, transform, normalize<br/>in each TTF master task"]
    F -->|"CFF2"| CFF0["Raw CFF source masters<br/>no outline transform yet"]

    subgraph CFFP["process_pool: joint cu2qu by glyph chunks"]
        CFF100["Chunk worker loads<br/>100 / 400 / 800 CFF masters"]
        CFF200["Convert one glyph chunk<br/>with Cu2QuMultiPen"]
        CFF300["Return compatible glyf glyphs<br/>for all three masters"]
        CFF100 --> CFF200 --> CFF300
    end

    CFF0 --> CFF100
    CFF300 --> G1["Install glyf tables<br/>into 100 / 400 / 800 masters"]
    G1 --> G2["Apply transform, normalize,<br/>recalculate, save TTF masters"]
    G0 --> M0["Transformed TTF source masters"]
    G2 --> M0

    subgraph REG["Regular variable base build"]
        R0["Merge transformed TTF masters<br/>into Maple feature VF"]
        R1["Build gvar deltas<br/>from 100 / 400 / 800 geometry"]
        R2["Finalize regular variable base font<br/>metrics, names, STAT, instances"]
        R0 --> R1 --> R2
    end

    subgraph ITALIC["Italic variable base build"]
        subgraph ISP["process_pool: skew transformed TTF masters"]
            IS100["Skew 100 master"]
            IS400["Skew 400 master"]
            IS800["Skew 800 master"]
        end

        subgraph IFP["process_pool: instantiate and skew feature masters"]
            IF100["Italic feature 100 master"]
            IF400["Italic feature 400 master"]
            IF800["Italic feature 800 master"]
        end

        I1["Rebuild italic feature VF<br/>from italic feature masters"]
        I2["Merge slanted glyf masters"]
        I3["Build gvar deltas<br/>from slanted 100 / 400 / 800 geometry"]
        I4["Finalize italic variable base font<br/>italic metadata, metrics, names"]

        IS100 --> I2
        IS400 --> I2
        IS800 --> I2
        IF100 --> I1
        IF400 --> I1
        IF800 --> I1
        I1 --> I2 --> I3 --> I4
    end

    IB0["Source master paths<br/>available for italic build"]
    M0 --> R0
    BASE --> R0
    M0 --> IB0
    BASE --> IB0
    IB0 --> IS100
    IB0 --> IS400
    IB0 --> IS800
    IB0 --> IF100
    IB0 --> IF400
    IB0 --> IF800
    R2 --> M["Save regular variable base font"]
    I4 --> N["Save italic variable base font"]
    M --> O["process_pool: instantiate named static TTF weights<br/>from saved variable base fonts"]
    N --> O
    O --> P["Update names, cleanup tables,<br/>write sha256 and zip archive"]
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
| Convert CFF2 sources to TTF masters early | Avoid rebuilding CFF2 variable fonts and keep the regular/italic merge path shared. |
| Convert CFF masters by glyph chunks | Joint `cu2qu` keeps masters compatible while process-pool chunks keep large subsets fast. |
| Always emit variable and static fonts as TTF | CFF2 source outlines are converted to compatible `glyf` masters during source master preparation. |
| Keep built-in presets thin | CN and JP presets only define source paths, master mappings, Unicode filters, naming, and output layout. |

## Built-in Presets

| Preset | Source | Outline | Notes |
| ------ | ------ | ------- | ----- |
| CN | `source/cn/WenYuanRoundedSCVF.otf` | glyf | Merges source masters into the Maple feature VF and emits CN variable/static outputs. |
| JP | `source/jp/ResourceHanRoundedJP-VF.otf` | CFF2 | Converts source masters to TTF, then uses the shared glyf variable/static pipeline. |

## Main Phases

| Phase | Main functions |
| ----- | -------------- |
| Config and CLI | `config_from_json`, `config_from_cli`, `add_cjk_arguments` |
| Unicode selection | `unicode_config_from_spec`, `get_allowed_codepoints` |
| Subsetting | `prepare_source_subset`, `subset_font` |
| Master instantiation | `prepare_source_masters`, `instantiate_masters_from_vf` |
| glyf merge | `merge_cjk_masters_into_vf`, `merge_masters_into_vf` |
| CFF2 conversion | `convert_cff_static_to_glyf`, `update_maxp_for_glyf` |
| Italic build | `make_italic_variable_font`, `make_italic_master_file` |
| Static output | `instantiate_static_fonts`, `convert_cff_static_to_glyf` |
| Final cleanup | `finalize_variable_font`, `instantiate_static_font_file` |
