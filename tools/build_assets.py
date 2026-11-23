#!/usr/bin/env python3
"""Build data/entities.json and assets/icons/* for the Brotato save editor.

Entity id/name data is pulled from the BrotatoMods community data set
(AlperenEvci/brotato-shop-advisor) and icons are pulled from the official
Brotato wiki (https://brotato.wiki.spellsandguns.com) via its MediaWiki API.

Usage: python3 tools/build_assets.py [--out DIR]
Requires: requests, pillow (build-time only, not needed by the app itself).
"""
import argparse
import io
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import quote

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
WIKI = "https://brotato.wiki.spellsandguns.com"
DATA_REPO = "AlperenEvci/brotato-shop-advisor"
DATA_FILES = {
    "items": "data/items_merged.json",
    "weapons": "ingestion/data/weapons.json",
    "characters": "ingestion/data/characters.json",
}
ICON_SIZE = 48
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}

STAT_KEYS = [
    "stat_max_hp", "stat_hp_regeneration", "stat_lifesteal", "stat_percent_damage",
    "stat_melee_damage", "stat_ranged_damage", "stat_elemental_damage",
    "stat_attack_speed", "stat_crit_chance", "stat_engineering", "stat_range",
    "stat_armor", "stat_dodge", "stat_speed", "stat_luck", "stat_harvesting",
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def gh_raw(path: str) -> dict:
    url = f"https://raw.githubusercontent.com/{DATA_REPO}/main/{path}"
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return r.json()


def fetch_all_images() -> list[dict]:
    images = []
    params = {"action": "query", "list": "allimages", "ailimit": "500",
              "aiprop": "url|size", "format": "json"}
    while True:
        r = requests.get(f"{WIKI}/api.php", params=params, headers=UA, timeout=60)
        r.raise_for_status()
        data = r.json()
        images.extend(data["query"]["allimages"])
        if "continue" not in data:
            break
        params.update(data["continue"])
    return images


def build_entities() -> list[dict]:
    entities = []
    for kind, fname in DATA_FILES.items():
        for entry in gh_raw(fname):
            e = {"id": entry["my_id"], "name": entry["name"], "kind": kind[:-1] if kind != "items" else "item"}
            if kind == "items":
                e["tier"] = entry.get("tier")
            if kind == "weapons":
                e["rarity"] = entry.get("rarity")
                e["classes"] = entry.get("classes", [])
                damage_types = entry.get("damage_types", [])
                e["damage_types"] = damage_types
                e["wtype"] = "melee" if "Melee" in damage_types else "ranged"
            e["dlc"] = bool(entry.get("dlc"))
            entities.append(e)
    return entities


def candidates_for(entity: dict) -> list[tuple[str, list[str]]]:
    """Return [(manifest_key, [normalized wiki-name candidates])]."""
    my_id, name, kind = entity["id"], entity["name"], entity["kind"]
    base_names = [name, name + " icon", my_id.split("_", 1)[-1].replace("_", " ")]
    out = []
    if kind == "weapon":
        for tier in (1, 2, 3, 4):
            names = [f"{name} {ROMAN[tier]}", f"{name} {tier}", name, name + " icon"]
            out.append((f"{my_id}_{tier}", names + base_names))
        out.append((my_id, base_names))
    else:
        out.append((my_id, base_names + [f"{name} icon"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent))
    args = ap.parse_args()
    root = Path(args.out)
    icons_dir = root / "assets" / "icons"
    data_dir = root / "data"
    icons_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    from PIL import Image

    print("fetching entity data ...")
    entities = build_entities()
    print(f"  {len(entities)} entities")

    print("fetching wiki file index ...")
    images = fetch_all_images()
    print(f"  {len(images)} files on wiki")
    index = {}
    for img in images:
        fname = img["name"]
        stem = fname.rsplit(".", 1)[0] if "." in fname else fname
        index.setdefault(norm(stem), img)

    def find(names):
        for n in names:
            hit = index.get(norm(n))
            if hit:
                return hit
        return None

    manifest = {}
    missing = []
    total = 0

    def download(key: str, names) -> None:
        nonlocal total
        hit = find(names)
        if not hit:
            missing.append((key, names[0]))
            return
        r = requests.get(hit["url"], headers=UA, timeout=60)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGBA")
        w, h = im.size
        scale = min(ICON_SIZE / w, ICON_SIZE / h, 1.0)
        if scale < 1.0:
            im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
        canvas = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
        canvas.paste(im, ((ICON_SIZE - im.size[0]) // 2, (ICON_SIZE - im.size[1]) // 2), im)
        canvas.save(icons_dir / f"{key}.png")
        manifest[key] = f"{key}.png"
        total += 1

    for e in entities:
        for key, names in candidates_for(e):
            download(key, names)

    print("stat icons ...")
    for sk in STAT_KEYS:
        pretty = sk[len("stat_"):].replace("_", " ")
        download(sk, [pretty, pretty.title(), sk.replace("_", " ")])

    print("app icon ...")
    logo = None
    for img in images:
        n = norm(img["name"])
        if "logo" in n and ("brotato" in n or "icon" in n):
            logo = img
            break
    if logo is None:
        for img in images:
            if norm(img["name"]) in ("brotato", "brotatologo"):
                logo = img
                break
    if logo:
        r = requests.get(logo["url"], headers=UA, timeout=60)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGBA")
        im.thumbnail((128, 128), Image.LANCZOS)
        im.save(icons_dir / "app_icon.png")
        manifest["app_icon"] = "app_icon.png"
        print(f"  app icon: {logo['name']}")
    else:
        print("  WARNING: no logo found")

    (data_dir / "entities.json").write_text(
        json.dumps(entities, ensure_ascii=False, indent=1), encoding="utf-8")
    (icons_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    print(f"downloaded {total} icons -> {icons_dir}")
    print(f"missing {len(missing)}: {[m[0] for m in missing][:20]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
