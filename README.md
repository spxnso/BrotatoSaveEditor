# Brotato Save Editor

A desktop save editor for [Brotato](https://store.steampowered.com/app/1942280/Brotato/)
(Steam, by Blobfish), written in Python with **tkinter** — no third-party
runtime dependencies.

Edit your in-progress run: items, weapons (incl. per-weapon stats), character
stats, gold/materials, wave, difficulty, shop offers — or your meta save
(unlocks). Item, weapon, character and stat icons shown in the UI are pulled
from the official [Brotato Wiki](https://brotato.wiki.spellsandguns.com) and
bundled in `assets/icons/`.

![tabs](assets/icons/app_icon.png)

## Requirements

- Python 3.8+ with tkinter (included in standard Windows/macOS installers;
  on Debian/Ubuntu: `sudo apt install python3-tk`)

## Run

```bash
python3 brotato_save_editor.py
# or open a save directly:
python3 brotato_save_editor.py "C:/Users/<you>/AppData/Roaming/Brotato/<steam_id>/run_v3_0.json"
```

Then **File > Open…** (or *Open Brotato save folder…*, which auto-detects the
save directory), edit, and **Save** (Ctrl+S). A `<file>.editor.bak` backup is
written next to the save on every save.

> Close the game before saving — Brotato rewrites `run_v3_*.json` / `save_v3_*.json`
> whenever it exits, which would overwrite your edits.

## Save file locations

| OS | Path |
|----|------|
| Windows | `%APPDATA%\Brotato\<steam_id>\run_v3_0.json` and `save_v3_0.json` |
| Linux / Steam Deck (Proton) | `~/.local/share/Steam/steamapps/compatdata/1942280/pfx/drive_c/users/steamuser/AppData/Roaming/Brotato/<steam_id>/` |

- `run_v3_<n>.json` — the current run: `current_run_state.players_data[0]` holds
  `current_character`, `current_health`, `current_level`, `current_xp`, `gold`,
  `weapons[]`, `items[]`, `effects{}` (the stat block), …; run-level fields
  (`current_wave`, `current_difficulty`, `shop_items`, …) sit next to it.
- `save_v3_<n>.json` — meta/progress save: `characters_unlocked`,
  `items_unlocked`, `weapons_unlocked`, challenges, records, …

Both are plain JSON (v3 format); the editor also copes with older saves that
store items/weapons as plain strings.

## Features

- **Run tab** — wave, difficulty (Danger 0–5), zone, gold/materials, health,
  level, XP, character (with icon), rerolls, endless/co-op flags, and any other
  scalar run field. Creates an empty run state if `has_run_state` is false.
- **Stats tab** — searchable editor for the player's `effects` dict
  (`stat_max_hp`, `stat_luck`, …) with wiki stat icons; add/delete stats.
- **Items / Weapons tabs** — icon rows with editable id, tier, value, lock;
  add any item/weapon (weapons in tiers I–IV) from a searchable dropdown;
  per-weapon `stats…` dialog (damage, cooldown, projectiles, …).
- **Shop tab** — edit `shop_items` / `locked_shop_items` offers (icon, price,
  wave, locked).
- **Unlocks tab** (meta saves) — add/remove unlocked characters, weapons,
  items, upgrades, consumables, challenges, zones, difficulties.
- **Raw JSON tab** — full tree editor (edit/add/delete any node) for anything
  else.

## Project layout

```
brotato_save_editor.py   GUI app (tkinter)
brotato_model.py         save-file logic (pure stdlib, unit-tested)
data/entities.json       item/weapon/character ids + names (from BrotatoMods community data)
assets/icons/            wiki icons (48x48 PNG) + manifest.json + app_icon.png
tools/build_assets.py    re-downloads icons/entities from the wiki + GitHub
tests/                   unittest suite (model + headless GUI logic via a fake tkinter)
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Building an executable

```bash
pip install -r requirements-build.txt
pyinstaller --clean --noconfirm brotato_save_editor.spec
# -> dist/BrotatoSaveEditor.exe (Windows) / dist/BrotatoSaveEditor (Linux/macOS)
```

The build bundles `data/` and `assets/` (icons) into the single-file exe.

## CI / releases

`.github/workflows/build.yml` runs the unit tests on every push to `main`.
When a **GitHub release is published** (or the workflow is run manually via
*Actions > Build & Release > Run workflow*), it builds the executable with
PyInstaller on Windows, Linux and macOS and **attaches the binaries to that
release** (also available as workflow artifacts). Publishing a release
tagged e.g. `v1.0.0` is all that is needed:

```bash
git tag v1.0.0 && git push origin v1.0.0
# then create a release for the tag on GitHub
```

## Rebuilding the icon assets

```bash
pip install requests pillow
python3 tools/build_assets.py
```

This re-fetches the entity id/name table from the BrotatoMods community data
(`AlperenEvci/brotato-shop-advisor`) and all icons from the official Brotato
wiki MediaWiki API (`brotato.wiki.spellsandguns.com`), resizing them to 48×48
PNGs in `assets/icons/`.

## Disclaimer

For offline, single-player use on your own save files. Brotato is © Blobfish;
icons are © their respective owners, fetched from the community wiki.
