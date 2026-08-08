# Usage

## VSCode / Cursor

Set up Maple Mono in your VS Code settings JSON file:

```jsonc
{
  // Set the font family
  "editor.fontFamily": "Maple Mono NF, Jetbrains Mono, Menlo, Consolas, monospace",
  // Enable ligatures
  "editor.fontLigatures": "'calt'",
  // Or enable selected OpenType features
  "editor.fontLigatures": "'calt', 'cv01', 'ss01', 'zero'",
}
```

## IntelliJ IDEA / PyCharm / WebStorm / GoLand / CLion

1. Open Settings.
2. Select **Editor**.
3. Select **Font**.
4. Choose **Maple Mono NF** in the font menu.
5. Enable **Enable font ligatures**.
6. Open **Typography Settings** to enable supported OpenType stylistic sets and character variants.

> [!NOTE]
> JetBrains IDEs support OpenType stylistic sets, character variants, and other user-facing OpenType features in version **2026.1** and later. This support was introduced in the 2026.1 EAP; configure it under **Settings | Editor | Font | Typography Settings**. See the [2026.1 release notes](https://blog.jetbrains.com/idea/2026/03/whats-fixed-intellij-idea-2026-1/) and [font settings documentation](https://www.jetbrains.com/help/idea/settings-editor-font.html).

## Zed

Open **Command Palette → zed: open settings file** and add the following settings. Zed uses `true`/`false` for binary features and numeric values for features such as character variants:

```jsonc
{
  "buffer_font_family": "Maple Mono NF",
  "buffer_font_features": {
    "calt": true,
    "cv01": 1,
    "ss01": 1,
    "zero": 1
  }
}
```

`buffer_font_features` controls the editor buffer font. Zed's current reference documents this setting for macOS and Windows; see the [Zed settings reference](https://zed.dev/docs/reference/all-settings#buffer-font-features).

## Windows Terminal

Open **Settings → Open JSON file** and add the `font` object to the profile you use. The nested `font` object, including `features`, requires Windows Terminal 1.10 or later:

```jsonc
{
  "profiles": {
    "list": [
      {
        "name": "PowerShell",
        "font": {
          "face": "Maple Mono NF",
          "features": {
            "calt": 1,
            "cv01": 1,
            "ss01": 1,
            "zero": 1
          }
        }
      }
    ]
  }
}
```

Merge these properties into the existing profile instead of adding a duplicate profile. See Microsoft's [profile appearance settings](https://learn.microsoft.com/en-us/windows/terminal/customize-settings/profile-appearance) for the complete schema.

## Kitty

Add this line to `kitty.conf`. kitty supports the extended `font_family` syntax, so the OpenType features apply to the selected font face:

```conf
font_family family="Maple Mono NF" features="+calt +cv01 +ss01 +zero"
```

You can also run `kitten choose-fonts` to select the font and features interactively. See kitty's [font selection documentation](https://sw.kovidgoyal.net/kitty/kittens/choose-fonts/) for the syntax and available options.

## Ghostty

Add the following to Ghostty's `config.ghostty` file. On macOS, the file is normally located at `~/Library/Application Support/com.mitchellh.ghostty/config.ghostty`; on Linux, use `~/.config/ghostty/config.ghostty`:

```conf
font-family = Maple Mono NF
font-feature = +calt, +cv01, +ss01, +zero
```

`font-feature` can be repeated or given a comma-separated list. These features apply to all fonts rendered by Ghostty. See the [Ghostty configuration reference](https://ghostty.org/docs/config/reference#font-feature).
