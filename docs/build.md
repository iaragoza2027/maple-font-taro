# Custom Build

The [`config.json`](../config.json) file configures the build process. Check the [schema](../source/schema.json) and [OpenType feature documentation](./opentype-features.md) for the complete configuration surface.

CLI options override `config.json`. Run `python build.py --help` after installing dependencies to see the current options.

## Build In Browser

Go to [Playground](https://font.subf.dev/en/playground), and click the "Custom Build" button in the bottom left corner

- Only supports freezing OpenType features currently.

## Use GitHub Actions

You can use [Github Actions](https://github.com/subframe7536/maple-font/actions/workflows/custom.yml) to build the font.

1. Fork the repo.
2. (Optional) Change the content in `config.json`.
3. Go to the Actions tab.
4. Click on the `Custom Build` menu item on the left.
5. Click on the `Run workflow` button with options set.
6. Wait for the build to finish.
7. Download the font archives from Releases.

## Use Docker

```shell
git clone https://github.com/subframe7536/maple-font --depth 1
docker build -t maple-font .
docker run -v "$(pwd)/fonts:/app/fonts" -e BUILD_ARGS="--normal" maple-font
```

## Local Build

V8 is currently available from the `variable` branch. Make sure you have Python 3.10+ and `pip` installed.

```shell
git clone https://github.com/subframe7536/maple-font --depth 1
cd maple-font
pip install -r requirements.txt
python build.py
```

> [!TIP]
> For `Ubuntu` or `Debian`, maybe `python-is-python3` is needed as well.
>
> If you have trouble installing the dependencies, just create a new GitHub Codespace and run the commands there.

The commands above build the development version and write generated fonts under `fonts/`. They do not replace the v7.9 packages already installed by Scoop, Homebrew, Arch, Nix, or a CDN.
