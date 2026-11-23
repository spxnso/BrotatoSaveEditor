"""Save-file logic for the Brotato save editor (no GUI dependencies).

Handles Brotato v3 saves:
  run_v3_<profile>.json  -> {"current_run_state": {...}}   (an in-progress run)
  save_v3_<profile>.json -> meta/progress save (unlocks, stats, settings, ...)

The run state schema follows the game's own serialization
(singletons/run_data.gd, singletons/player_run_data.gd):
  current_run_state.players_data[i] holds character, health, level, xp, gold,
  weapons[], items[], effects{} (the stat block), active_sets, ...
  current_run_state.shop_items / locked_shop_items are 4 player slots, each a
  list of [serialized offer, wave] pairs.
Items/weapons are dicts with my_id, name, tier, value, effects, ... (weapons
add weapon_id, type, stats, sets, ...).  Older saves may store plain strings
("weapon_knife_1") instead of dicts; both are supported.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import sys
from pathlib import Path

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = Path(sys._MEIPASS)  # PyInstaller bundle
else:
    BASE_DIR = Path(__file__).resolve().parent
ENTITIES_PATH = BASE_DIR / "data" / "entities.json"
ICON_MANIFEST_PATH = BASE_DIR / "assets" / "icons" / "manifest.json"
ICON_DIR = BASE_DIR / "assets" / "icons"

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}
DANGER_NAMES = {0: "Danger 0 (Harmless)", 1: "Danger 1", 2: "Danger 2",
                3: "Danger 3", 4: "Danger 4", 5: "Danger 5 (Maximum)", -1: "Not set"}

_entities_cache = None
_icon_manifest_cache = None


def load_entities() -> dict:
    """my_id -> {"id", "name", "kind", ...} for items, weapons, characters."""
    global _entities_cache
    if _entities_cache is None:
        try:
            _entities_cache = {e["id"]: e for e in json.loads(ENTITIES_PATH.read_text(encoding="utf-8"))}
        except (OSError, json.JSONDecodeError):
            _entities_cache = {}
    return _entities_cache


def load_icon_manifest() -> dict:
    """icon key -> png file name inside assets/icons/."""
    global _icon_manifest_cache
    if _icon_manifest_cache is None:
        try:
            _icon_manifest_cache = json.loads(ICON_MANIFEST_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _icon_manifest_cache = {}
    return _icon_manifest_cache


def icon_path(key: str):
    """Filesystem path of an icon, or None if the manifest has no entry."""
    fname = load_icon_manifest().get(key)
    if fname:
        p = ICON_DIR / fname
        if p.is_file():
            return p
    return None


def split_id(my_id: str):
    """'weapon_knife_3' -> ('weapon', 'weapon_knife', 3); 'item_acid' -> ('item', 'item_acid', None)."""
    m = re.match(r"^(weapon|item|character|set)_(.+?)(?:_(\d+))?$", my_id or "")
    if not m:
        return ("", my_id or "", None)
    kind = m.group(1)
    return (kind, f"{kind}_{m.group(2)}", int(m.group(3)) if m.group(3) else None)


def icon_key_for(my_id: str) -> str:
    """Manifest key for an id: weapons prefer their tier-specific icon."""
    kind, base, tier = split_id(my_id)
    if kind == "weapon" and tier:
        if f"{base}_{tier}" in load_icon_manifest():
            return f"{base}_{tier}"
        return base
    return my_id


def display_name(my_id: str, entities=None) -> str:
    entities = entities if entities is not None else load_entities()
    kind, base, tier = split_id(my_id)
    ent = entities.get(base) or entities.get(my_id)
    name = ent["name"] if ent else (base.split("_", 1)[-1].replace("_", " ").title() if base else my_id)
    if kind == "weapon" and tier and tier in ROMAN:
        name = f"{name} {ROMAN[tier]}"
    return name


def coerce(text: str, old):
    """Parse user text into a JSON value, keeping the old value's type when possible."""
    text = text.strip()
    if text.lower() in ("null", "none"):
        return None
    if isinstance(old, bool):
        return text.lower() in ("1", "true", "yes", "on")
    if isinstance(old, int) and not isinstance(old, bool):
        try:
            return int(text)
        except ValueError:
            return old
    if isinstance(old, float):
        try:
            return float(text)
        except ValueError:
            return old
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text


# --------------------------------------------------------------------------- save IO

def load_save(path):
    """Return (data, kind) where kind is 'run', 'meta' or 'unknown'."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return data, "unknown"
    if "current_run_state" in data:
        return data, "run"
    if "version" in data or "characters_unlocked" in data or "data" in data:
        return data, "meta"
    return data, "unknown"


def save_save(path, data, backup: bool = True) -> Path:
    """Write JSON back to disk, keeping a .editor.bak copy of the previous file."""
    path = Path(path)
    backup_path = path.with_suffix(path.suffix + ".editor.bak")
    if backup and path.exists():
        shutil.copy2(path, backup_path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return backup_path


# --------------------------------------------------------------------------- run state

def get_run_state(data):
    if isinstance(data, dict):
        return data.get("current_run_state")
    return None


def get_players(run_state) -> list:
    if not isinstance(run_state, dict):
        return []
    players = run_state.get("players_data")
    if isinstance(players, list) and players:
        return players
    # legacy (pre-players_data) layout: fields directly on the run state
    if run_state.get("has_run_state"):
        return [run_state]
    return []


def get_player(run_state, index: int = 0):
    players = get_players(run_state)
    if 0 <= index < len(players):
        return players[index]
    return None


def entry_id(entry) -> str:
    """my_id of an item/weapon entry whether it is a dict or a legacy string."""
    if isinstance(entry, dict):
        return entry.get("my_id", "")
    if isinstance(entry, str):
        return entry
    return ""


def entry_as_dict(entry, entities=None) -> dict:
    """Normalize an item/weapon entry to a dict (legacy strings get a minimal dict)."""
    if isinstance(entry, dict):
        return entry
    my_id = entry if isinstance(entry, str) else ""
    kind, base, tier = split_id(my_id)
    if kind == "weapon":
        return new_weapon(my_id, entities)
    return new_item(my_id, entities)


def set_entry_id(entry, new_id: str) -> None:
    if isinstance(entry, dict):
        entry["my_id"] = new_id
        if "name" in entry:
            entry["name"] = new_id.upper()


# --------------------------------------------------------------------------- templates

def _base_weapon_stats(wtype: str) -> dict:
    stats = {
        "type": wtype,
        "cooldown": 1.0, "damage": 10, "accuracy": 1.0, "crit_chance": 0.03,
        "crit_damage": 1.5, "min_range": 0, "max_range": 150, "knockback": 0,
        "knockback_piercing": 0, "can_have_positive_knockback": True,
        "can_have_negative_knockback": True, "effect_scale": 1.0,
        "scaling_stats": [], "lifesteal": 0.0, "shooting_sounds": [],
        "sound_db_mod": -5, "is_healing": False, "recoil": 25,
        "recoil_duration": 0.1, "additional_cooldown_every_x_shots": 0,
        "additional_cooldown_multiplier": 1.0,
    }
    if wtype == "ranged":
        stats.update({
            "nb_projectiles": 1, "projectile_spread": 0.0, "piercing": 0,
            "piercing_dmg_reduction": 0.5, "bounce": 0, "bounce_dmg_reduction": 0.5,
            "can_bounce": True, "projectile_speed": 3000,
            "increase_projectile_speed_with_range": False,
        })
    else:
        stats.update({"deal_dmg_on_return": False, "attack_type": 0,
                      "alternate_attack_type": False})
    return stats


def new_item(my_id: str, entities=None) -> dict:
    return {
        "my_id": my_id,
        "name": my_id.upper(),
        "tier": "1",
        "value": "0",
        "effects": [],
        "tracking_text": "",
        "is_locked": False,
        "is_cursed": False,
        "curse_factor": 0.0,
        "is_lockable": True,
        "max_nb": "-1",
        "tags": [],
        "item_appearances": [],
    }


def new_weapon(my_id: str, entities=None) -> dict:
    entities = entities if entities is not None else load_entities()
    kind, base, tier = split_id(my_id)
    ent = entities.get(base, {})
    wtype = ent.get("wtype", "ranged")
    return {
        "my_id": my_id,
        "name": my_id.upper(),
        "tier": str(tier or 1),
        "value": "0",
        "effects": [],
        "tracking_text": "",
        "is_locked": False,
        "is_cursed": False,
        "curse_factor": 0.0,
        "is_lockable": True,
        "weapon_id": base,
        "type": "1" if wtype == "ranged" else "0",
        "stats": _base_weapon_stats(wtype),
        "dmg_dealt_last_wave": "0",
        "tracked_value": "0",
        "tracked_value_added_this_wave": "0",
        "add_to_chars_as_starting": [],
        "sets": [],
    }


def new_shop_offer(my_id: str, wave: int = 1, price: int = 0, entities=None) -> list:
    kind, base, tier = split_id(my_id)
    offer = new_weapon(my_id, entities) if kind == "weapon" else new_item(my_id, entities)
    offer["value"] = str(price)
    return [offer, wave]


def empty_player() -> dict:
    effects = {k: 0 for k in (
        "stat_max_hp", "stat_hp_regeneration", "stat_lifesteal", "stat_percent_damage",
        "stat_melee_damage", "stat_ranged_damage", "stat_elemental_damage",
        "stat_attack_speed", "stat_crit_chance", "stat_engineering", "stat_range",
        "stat_armor", "stat_dodge", "stat_speed", "stat_luck", "stat_harvesting")}
    effects["stat_max_hp"] = 10
    return {
        "current_character": "character_well_rounded",
        "current_health": 10,
        "current_level": 1,
        "current_xp": 0,
        "gold": 0,
        "selected_weapon": None,
        "selected_item": None,
        "weapons": [],
        "items": [],
        "appearances": [],
        "effects": effects,
        "active_sets": {},
        "active_set_effects": [],
        "unique_effects": [],
        "additional_weapon_effects": [],
        "tier_iv_weapon_effects": [],
        "tier_i_weapon_effects": [],
        "chal_recycling_current": 0,
        "consumables_picked_up_this_run": [],
        "curse_locked_shop_items_pity": 0,
        "banned_items": [],
        "remaining_ban_token": 0,
        "uses_ban": False,
    }


def empty_run_state() -> dict:
    return {
        "has_run_state": True,
        "players_data": [empty_player()],
        "enemy_scaling": {"damage": 1, "health": 1, "speed": 1},
        "constant_projectile": False,
        "nb_of_waves": 20,
        "current_zone": 0,
        "current_wave": 1,
        "current_difficulty": 0,
        "bonus_gold": 0,
        "total_bonus_gold": 0,
        "retries": 0,
        "elites_spawn": [],
        "bosses_spawn": [],
        "events_spawn": [],
        "events_fog_of_war": [],
        "events_bullet_hell": [],
        "shop_effects_checked": False,
        "elites_killed_this_run": [],
        "bosses_killed_this_run": [],
        "loot_aliens_killed_this_run": [],
        "challenges_completed_this_run": [],
        "locked_shop_items": [[], [], [], []],
        "current_background": "bg_forest",
        "max_endless_wave_record_beaten": -1,
        "is_endless_run": False,
        "is_coop_run": False,
        "play_mode": 0,
        "is_streamplay_run": False,
        "enabled_dlcs": [],
        "shop_items": [[], [], [], []],
        "reroll_price": 2,
        "last_reroll_price": -1,
        "initial_free_rerolls": 0,
        "free_rerolls": 0,
        "tracked_item_effects": {},
    }


def ensure_run_state(data) -> dict:
    """Return the current_run_state dict, creating an empty run if needed."""
    if not isinstance(data, dict):
        raise TypeError("save root is not a JSON object")
    state = data.get("current_run_state")
    if not isinstance(state, dict):
        state = empty_run_state()
        data["current_run_state"] = state
    elif not state.get("has_run_state"):
        merged = empty_run_state()
        merged.update(state)
        merged["has_run_state"] = True
        data["current_run_state"] = merged
        state = merged
    return state


# --------------------------------------------------------------------------- meta save helpers

META_LIST_KEYS = {
    "characters_unlocked": "Characters",
    "weapons_unlocked": "Weapons",
    "items_unlocked": "Items",
    "upgrades_unlocked": "Upgrades (level-up choices)",
    "consumables_unlocked": "Consumables",
    "challenges_completed": "Challenges",
    "zones_unlocked": "Zones",
    "difficulties_unlocked": "Difficulties",
}


def meta_add_unlock(data, key: str, my_id: str) -> bool:
    """Add my_id to a meta-save unlock list. Returns True if added."""
    lst = data.get(key)
    if not isinstance(lst, list):
        return False
    if my_id not in lst:
        lst.append(my_id)
        return True
    return False
