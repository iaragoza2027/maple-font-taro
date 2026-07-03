# TODO

## Ligatures

- [ ] `[ERRO]` `[DBUG]` `[SUCCESS]` #767

## Character Variant

- [ ] cv12 / cv45: `u` without tail, like JetBrains Mono #785
- [ ] cv67: longer bar (`|`), top + 50, bottom - 100 #732
  - [ ] relative ligatures
- [ ] cv68 / cv69: like monaspace cv12 / cv13 #782

## Unicode

- [ ] U+22C4–U+22FF, reference from Julia Mono's math symbols #709
- [ ] u+266a, u+2303, u+23ce #762
- [ ] chess symbols #594
- [ ] "♦", "♠", "♥", "♣" #771
- [ ] U+2C6D, U+0E3F #772
- [ ] U+21E0-U+21E3 #740
- [x] make u+E0B4 / u+E0B6 more rounded #780
- [ ] fill ALL sub and sup glyphs, fix wrong unicodes #789

### CN

- [x] 易经六十四卦符号 #580

## CJK

- [ ] try not to convert CFF2 to glyf, directly use CFF2 to merge variable font and generate ttf when instantiating
- [x] WenYuanRoundedSCVF as SC part
- [ ] ChironGoRoundTCVF as TC + KR (range should reference from Pretendard) part
  - Maple and ChironGoRoundTCVF weight mapping:
    - 100 -> 250
    - 400 -> 620
    - 800 -> 900
- [ ] M PLUS Rounded 1c variable as JP part
