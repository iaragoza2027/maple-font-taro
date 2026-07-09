# TODO

## Ligatures

- [ ] `[ERRO]` `[DBUG]` `[SUCCESS]` #767

## Character Variant

- [ ] cv12 / cv45: `u` without tail, like JetBrains Mono #785
- [ ] cv67: longer bar (`|`), top + 50, bottom - 100 #732
  - [ ] relative ligatures
- [ ] cv68 / cv69: like monaspace cv12 / cv13 #782

## Unicode

- [x] U+2200–U+22FF, reference from Julia Mono's math symbols #709
- [ ] claude code:
  - [x] spinner: U+273B, U+2605, U+273D, U+2733, U+2722, U+2736, U+2726
  - [ ] progress: U+25D0-25D3
  - [ ] figures: U+21BB, U+21AF
  - [ ] play/pause: U+23F5, U+23FA, U+23F8
  - [ ] alarm/symbol: U+29C9, U+2694, U+2620, U+2691, U+26F6, U+26DD, U+2764
- [x] `─→` should horizonly aligned
- [x] u+266a, u+2303, u+23ce #762
- [x] chess symbols #594
- [x] "♦", "♠", "♥", "♣" #771
- [x] U+2C6D, U+0E3F #772
- [x] U+21E0-U+21E3 #740
- [x] make u+E0B4 / u+E0B6 more rounded #780
- [x] fill ALL sub and sup glyphs, fix wrong unicodes #789
  - [x] pass verify_sup_sub.md visual page

### CN

- [x] 易经六十四卦符号 #580

## Build

- [x] cleanup
- [x] add more details in mermaid dataflow graph
- [x] customizable locale name
- [x] fix cjk base font load priority regression: local cache > download from github release > instantiate from variable font > error
  - [x] stabilize directory hash with config-derived static hash files

## CJK

- [ ] try not to convert CFF2 to glyf, directly use CFF2 to merge variable font and generate ttf when instantiating
- [x] WenYuanRoundedSCVF as SC part
- [ ] ChironGoRoundTCVF as TC + KR (range should reference from Pretendard) part
  - Maple and ChironGoRoundTCVF weight mapping:
    - 100 -> 250
    - 400 -> 620
    - 800 -> 900
- [ ] Resource Han Sans JP as JP part
