# Maple Mono CN WenYuan Build Pipeline

```mermaid
flowchart TD
    A["<b>WenYuanRoundedSCVF.ttf</b><br/>wght: 100–400–<b>900</b> | ital: 0–0–1"] --> B["<b>get_wenyuan_keep_codepoints()</b><br/>compute CJK-range codepoints"]
    B --> C["<b>subset_font()</b><br/>+ <b>keep_only_unicode_glyphs()</b><br/>trim source to needed glyphs"]
    C --> D["<b>wenyuan-subset.ttf</b><br/>(subsetted VF on disk)"]

    D --> E["<b>instantiate_wenyuan_master_files()</b><br/>interpolate 3 static masters<br/>wght=200 as min / 450 as regular / 900 as max, ital=0"]
    E --> F["<b>Mapping 3 subsetted masters</b><br/>min (100) · regular (400) · max (800)<br/>Match feature font<br/>"]
    F --> H["<b>save to disk</b><br/>source/cn/temp/masters/<br/>wenyuan-*-master.ttf"]

    %% ── Regular: merge masters directly into feature font ──
    F --> MRG["<b>merge_masters_into_vf()</b><br/>for each new glyph:<br/>  glyf ← regular master<br/>  hmtx ← regular master<br/>  gvar ← Δ(min→reg) + Δ(reg→max)"]
    P["<b>MapleMono-CN-feature-VF.ttf</b><br/>(fvar: wght 100–400–800)"] --> MRG
    MRG --> RPOST["<b>apply_horizontal_metrics()</b><br/><b>normalize_widths()</b><br/><b>prune_stat() + recalculate_font()</b>"]
    RPOST --> Q["<b>normalize_cn_weight_axis()</b><br/>+ prune + recalculate"]
    Q --> R["<b>MapleMono-CN-VF.ttf</b>"]

    %% ── Italic Feature ──
    P2["<b>MapleMono-CN-feature-VF.ttf</b><br/>(loaded fresh)"] --> FM["<b>instantiate 3 masters</b><br/>wght=100 / 400 / 800"]
    FM --> FS["<b>make_italic_variable_font()</b><br/>skew each master → rebuild"]
    FS --> FT["<b>italic Feature VF</b>"]

    %% ── Italic WenYuan: slant masters, merge directly into italic feature ──
    H --> SW["<b>skew each master</b><br/>(same italic angle)"]
    SW --> IM["<b>merge_masters_into_vf()</b><br/>glyf/hmtx ← slanted regular<br/>gvar ← Δ(slanted min→reg) + Δ(reg→slanted max)"]
    FT --> IM
    IM --> IPOST["<b>apply_horizontal_metrics()</b><br/><b>prune_stat() + recalculate_font()</b>"]
    IPOST --> IX["<b>normalize_cn_weight_axis()</b><br/>+ prune + recalculate"]
    IX --> Y["<b>MapleMono-CN-Italic-VF.ttf</b>"]

    R --> Z["<b>instantiate_wenyuan_static_fonts()</b><br/>8 weights × 2 styles"]
    Y --> Z
    Z --> Z1["<b>static-wenyuan/</b><br/>MapleMonoCN-*.ttf × 16"]
    Z1 --> Z2["<b>cleanup_static_font_file()</b><br/>drop kern/GPOS, Mac names"]
    Z2 --> Z3["<b>archive → cn-base-static-wenyuan.zip</b>"]

    %% ── Rejected shortcut ──
    D -.-> REJ
    REJ["<b>REJECTED: direct merge_vf()</b><br/>axis mismatch:<br/>wght max 900≠800<br/>+ extra ital axis"]

    style A fill:#f9d5e5,stroke:#333
    style P fill:#d5e8d4,stroke:#333
    style P2 fill:#d5e8d4,stroke:#333
    style R fill:#dae8fc,stroke:#333
    style Y fill:#dae8fc,stroke:#333
    style Z3 fill:#ffe6cc,stroke:#333
    style MRG fill:#e1d5e7,stroke:#9673a6
    style REJ fill:#f8cecc,stroke:#b85450,stroke-dasharray:5
```

## Key design decisions

| Decision                                             | Rationale                                                                                                                                                                                                                      |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Subset source first**                              | Avoid instantiating masters with CJK glyphs that will be discarded later                                                                                                                                                       |
| **Merge masters → feature font directly**            | Static masters carry `glyf`/`hmtx` at 3 weights; `gvar` deltas computed inline during merge. No intermediate WenYuan VF — `load_wenyuan_template` + `rebuild_weight_masters_with_regular_default` eliminated from regular path |
| **Reuse subsetted masters for italic**               | The 3 saved masters are mechanically slanted, then merged directly into the italic feature VF via `merge_masters_into_vf` — same pattern as regular path, no intermediate italic WenYuan VF                                    |
| **Feature font loaded fresh per merge**              | It is small (`MapleMono-CN-feature-VF.ttf`); loading twice is cheaper than deep-copying                                                                                                                                        |
| **Feature font made italic before italic merge**     | Feature font is slanted via `make_italic_variable_font`; then slanted WenYuan masters are merged directly into it — same `merge_masters_into_vf` as regular path                                                               |
| **`normalize_cn_weight_axis` only on merged result** | Feature font's `fvar` is the target; wenyuan `gvar` is written in normalized coords (−1…1)                                                                                                                                     |
| **Zero glyph overlap**                               | Feature (Maple Mono specific glyphs) and WenYuan (CJK) are disjoint → merge is purely additive                                                                                                                                 |

## Functions by phase

| Phase               | Functions                                                                        |
| ------------------- | -------------------------------------------------------------------------------- |
| Subset              | `get_wenyuan_keep_codepoints`, `subset_font`, `keep_only_unicode_glyphs`         |
| Instantiate masters | `instantiate_wenyuan_master_files`, `instantiate_variable_font_file`             |
| Merge masters → VF  | `merge_masters_into_vf` (new: copies glyf/hmtx + builds gvar per glyph)          |
| Post-process        | `apply_horizontal_metrics`, `normalize_widths`, `prune_stat`, `recalculate_font` |
| Italic (WenYuan)    | skew saved masters → `merge_masters_into_vf` (same as regular path)              |
| Italic (Feature)    | instantiate 3 masters → `make_italic_variable_font`                              |
| Finalize            | `normalize_cn_weight_axis` (feature font's `fvar` is the target)                 |
| Static output       | `instantiate_wenyuan_static_fonts`, `cleanup_static_font_file`                   |
