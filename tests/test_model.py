"""Tests for brotato_model (pure save-file logic). Run: python3 -m unittest discover -s tests -v"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import brotato_model as model

SAMPLE_RUN = {"current_run_state": {"has_run_state": False}}


class TestIds(unittest.TestCase):
    def test_split_id(self):
        self.assertEqual(model.split_id("weapon_knife_3"), ("weapon", "weapon_knife", 3))
        self.assertEqual(model.split_id("item_acid"), ("item", "item_acid", None))
        self.assertEqual(model.split_id("character_bull"), ("character", "character_bull", None))
        self.assertEqual(model.split_id("nonsense"), ("", "nonsense", None))

    def test_display_name(self):
        ents = model.load_entities()
        self.assertTrue(ents, "entities.json should load")
        self.assertEqual(model.display_name("weapon_knife_3", ents), "Knife III")
        self.assertEqual(model.display_name("character_well_rounded", ents), "Well Rounded")
        self.assertEqual(model.display_name("item_unknown_thing", ents), "Unknown Thing")

    def test_icon_key(self):
        self.assertEqual(model.icon_key_for("weapon_knife_3"), "weapon_knife_3")
        self.assertEqual(model.icon_key_for("weapon_knife"), "weapon_knife")
        self.assertEqual(model.icon_key_for("item_acid"), "item_acid")
        # every entity should resolve to an icon file on disk
        for e in ents_list():
            if e["id"] == "character_wiki_editing":  # wiki maintenance pseudo-character, no icon
                continue
            p = model.icon_path(model.icon_key_for(e["id"]))
            if e["kind"] == "weapon":
                p = p or model.icon_path(e["id"])
            self.assertIsNotNone(p, f"no icon for {e['id']}")

    def test_coerce(self):
        self.assertEqual(model.coerce("42", 1), 42)
        self.assertEqual(model.coerce("3.5", 1.0), 3.5)
        self.assertEqual(model.coerce("abc", 1), 1)  # invalid int keeps old
        self.assertEqual(model.coerce("true", False), True)
        self.assertEqual(model.coerce('"x"', "y"), "x")
        self.assertIsNone(model.coerce("null", 5))


def ents_list():
    return list(model.load_entities().values())


class TestSaveIO(unittest.TestCase):
    def test_load_kinds(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "run_v3_0.json"
            p.write_text(json.dumps(SAMPLE_RUN))
            data, kind = model.load_save(p)
            self.assertEqual(kind, "run")
            self.assertEqual(data, SAMPLE_RUN)

            p2 = Path(td) / "save_v3_0.json"
            p2.write_text(json.dumps({"version": 3, "characters_unlocked": []}))
            _, kind2 = model.load_save(p2)
            self.assertEqual(kind2, "meta")

    def test_save_backup_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "run_v3_0.json"
            p.write_text(json.dumps(SAMPLE_RUN))
            data, _ = model.load_save(p)
            data["current_run_state"]["has_run_state"] = True
            bak = model.save_save(p, data)
            self.assertTrue(bak.exists())
            self.assertEqual(json.loads(bak.read_text()), SAMPLE_RUN)
            self.assertTrue(json.loads(p.read_text())["current_run_state"]["has_run_state"])
            self.assertFalse(Path(str(p) + ".tmp").exists())


class TestRunState(unittest.TestCase):
    def test_ensure_on_empty_sample(self):
        data = json.loads(json.dumps(SAMPLE_RUN))
        state = model.ensure_run_state(data)
        self.assertTrue(state["has_run_state"])
        self.assertEqual(len(state["players_data"]), 1)
        self.assertEqual(state["players_data"][0]["current_character"], "character_well_rounded")
        self.assertEqual(len(state["shop_items"]), 4)
        self.assertEqual(state["current_wave"], 1)

    def test_get_players_legacy(self):
        legacy = {"has_run_state": True, "current_wave": 7, "gold": 5, "weapons": [], "items": []}
        self.assertEqual(model.get_players(legacy), [legacy])
        self.assertEqual(model.get_player(legacy)["current_wave"], 7)

    def test_templates(self):
        item = model.new_item("item_acid")
        self.assertEqual(item["my_id"], "item_acid")
        self.assertEqual(item["name"], "ITEM_ACID")
        self.assertIsInstance(item["tier"], str)

        w = model.new_weapon("weapon_knife_2")
        self.assertEqual(w["weapon_id"], "weapon_knife")
        self.assertEqual(w["stats"]["type"], "melee")
        self.assertEqual(w["type"], "0")
        w2 = model.new_weapon("weapon_pistol_1")
        self.assertEqual(w2["stats"]["type"], "ranged")
        self.assertEqual(w2["type"], "1")

        offer = model.new_shop_offer("item_acid", wave=3, price=65)
        self.assertEqual(offer[1], 3)
        self.assertEqual(offer[0]["value"], "65")
        self.assertEqual(offer[0]["my_id"], "item_acid")

    def test_entry_helpers(self):
        self.assertEqual(model.entry_id("weapon_knife_1"), "weapon_knife_1")
        self.assertEqual(model.entry_id({"my_id": "item_acid"}), "item_acid")
        d = model.entry_as_dict("item_acid")
        self.assertEqual(d["my_id"], "item_acid")
        d2 = dict(d)
        model.set_entry_id(d2, "item_sausage")
        self.assertEqual(d2["my_id"], "item_sausage")
        self.assertEqual(d2["name"], "ITEM_SAUSAGE")


class TestMeta(unittest.TestCase):
    def test_meta_add_unlock(self):
        data = {"characters_unlocked": ["character_well_rounded"]}
        self.assertTrue(model.meta_add_unlock(data, "characters_unlocked", "character_bull"))
        self.assertFalse(model.meta_add_unlock(data, "characters_unlocked", "character_bull"))
        self.assertFalse(model.meta_add_unlock(data, "nope", "x"))
        self.assertEqual(data["characters_unlocked"], ["character_well_rounded", "character_bull"])


if __name__ == "__main__":
    unittest.main()
