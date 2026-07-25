# Maple Mono Feature Module

The `scripts/feature/` package defines Maple Mono's OpenType feature rules as
Python objects and compiles them into feature source. The compiler is the source
of truth for generated feature behavior; `source/features/` contains the checked-in
feature files used by the file-based build path.

## Module layout

- `ast.py` provides the small AST used to emit classes, substitutions, lookups,
  and features.
- `regular.py` and `italic.py` expose the Latin feature definitions for each
  style.
- `base/` contains shared features such as `ccmp`, `locl`, case, and numbers.
- `calt/` contains contextual ligatures and tags.
- `cv/` and `ss/` contain character variants and stylistic sets.
- `compiler.py` assembles the selected feature source and exposes the public
  generation helpers.
- `apply.py` chooses generated-source or file-based application during a build.

## Feature application paths

The normal build path prepares one feature source for each regular and italic
Designspace before Fontmake runs. Enabled single substitutions copy the target
glyph outline and advance width into the source glyph in every UFO master, so
static and variable outputs use the same frozen outlines. Enabled contextual or
ligature lookups are attached to `calt`, disabled feature rules are removed,
and ignored features remain available as OpenType features.

`--apply-fea-file` selects the second path. It applies the matching checked-in
file, `source/features/regular.fea` or `source/features/italic.fea`, during the
same source preparation step. Includes are resolved before freeze rules are
applied. CJK static fonts select the corresponding `regular_cn.fea` or
`italic_cn.fea` file after CJK glyphs are merged; only CJK-specific substitutions
are frozen at that later boundary.

## AST examples

`Clazz` declares a reusable glyph class:

```py
from scripts.feature.ast import Clazz, subst

cls_digit = Clazz("Digit", ["zero", "one", "two", "three"])
cls_digit.state()
subst(cls_digit.use(), "a", "b", "c")
```

The two lines produce:

```fea
@Digit = [zero one two three];
sub @Digit a' b by c;
```

`Lookup` groups substitutions into a named lookup block:

```py
from scripts.feature.ast import Lookup, subst

lookup_example = Lookup(
    name="example_lookup",
    desc="Example substitution",
    content=[subst("a", "b", None, "c")],
)
```

Its output is:

```fea
# Example substitution
lookup example_lookup {
  sub a b' by c;
} example_lookup;
```

`Feature` requires the version argument used by the feature catalog:

```py
from scripts.feature.ast import Feature, create

feature_example = Feature(
    tag="calt",
    content=[lookup_example],
    version="1.0",
)
fea_content = create([feature_example])
print(fea_content)
```

The generated feature ends with the matching close tag:

```fea
feature calt {

  # Example substitution
  lookup example_lookup {
    sub a b' by c;
  } example_lookup;

} calt;
```

For a complete generated source, use the compiler's actual parameter names:

```py
from scripts.feature.compiler import generate_fea_string

fea_string = generate_fea_string(is_italic=False, is_cn=True)
print(fea_string)
```

The source ends in the final feature block, such as `} ss13;`, and each lookup
ends with its own `} lookup_name;` line. `uv run task.py fea` is the supported
way to refresh committed generated files.

## Custom tags

Tag helpers live in `calt/tag.py`. `subst_liga` creates one ligature lookup:

```py
from scripts.feature.ast import subst_liga

todo = subst_liga(
    source="TODO:",
    target="tag_todo.liga",
    lookup_name="todo_colon",
)
```

Use `tag_custom` in the same module for multiple trigger/replacement pairs. A
custom tag inherits text color, does not optimize spacing, and may break when
letter spacing is greater than zero; see [#381](https://github.com/subframe7536/maple-font/issues/381#issuecomment-2808022878).

## Generated files and synchronization

Run:

```sh
uv run task.py fea
```

The task writes these five feature files:

- `source/features/regular.fea`
- `source/features/italic.fea`
- `source/features/cn.fea`
- `source/features/regular_cn.fea`
- `source/features/italic_cn.fea`

It also refreshes `source/features/README.md`, `source/schema.json`, the feature
freeze section in `config.json`, the generated feature sections in
`README.md`, `README_CN.md`, and `README_JA.md`, and `scripts/in_browser.py`'s
moving-rule list. Before and after running the task, inspect the complete diff
of every listed output; generated changes outside the intended feature update
must not be kept.
