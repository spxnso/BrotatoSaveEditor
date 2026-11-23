"""Headless GUI-logic tests using the fake tkinter in fake_tk.py.

Run: python3 -m unittest discover -s tests -v   (from the project root)
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_tk
fake_tk.install()

import brotato_model as model
import brotato_save_editor as gui


def make_run_file(path):
    data = {"current_run_state": model.empty_run_state()}
    state = data["current_run_state"]
    state["current_wave"] = 7
    state["current_difficulty"] = 2
    player = state["players_data"][0]
    player["current_character"] = "character_bull"
    player["current_health"] = 33
    player["gold"] = 123
    player["effects"]["stat_luck"] = 42
    player["items"] = [model.new_item("item_acid"), "item_sausage"]
    player["weapons"] = [model.new_weapon("weapon_knife_2")]
    state["shop_items"][0] = [model.new_shop_offer("item_acid", wave=7, price=65)]
    Path(path).write_text(json.dumps(data), encoding="utf-8")
    return data


class GuiTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = gui.EditorApp()

    def open_run(self):
        p = Path(self.tmp.name) / "run_v3_0.json"
        make_run_file(p)
        self.app.open_file(str(p))
        return p

    def tab(self, name):
        for t in self.app.tabs:
            if t.name == name:
                return t
        raise AssertionError(f"no tab {name}; have {[t.name for t in self.app.tabs]}")


class TestOpenAndTabs(GuiTestBase):
    def test_run_file_tabs(self):
        self.open_run()
        names = [t.name for t in self.app.tabs]
        self.assertEqual(names, ["Run", "Stats", "Items", "Weapons", "Shop", "Raw JSON"])
        self.assertEqual(self.app.kind, "run")

    def test_empty_run_sample(self):
        p = Path(self.tmp.name) / "run_v3_0.json"
        p.write_text(json.dumps({"current_run_state": {"has_run_state": False}}))
        self.app.open_file(str(p))
        run = self.tab("Run")
        run._create_run()
        state = model.get_run_state(self.app.data)
        self.assertTrue(state["has_run_state"])
        self.assertEqual(state["players_data"][0]["current_character"], "character_well_rounded")

    def test_meta_file_has_unlocks_tab(self):
        p = Path(self.tmp.name) / "save_v3_0.json"
        p.write_text(json.dumps({"version": 3, "characters_unlocked": ["character_bull"],
                                 "items_unlocked": []}))
        self.app.open_file(str(p))
        names = [t.name for t in self.app.tabs]
        self.assertIn("Unlocks", names)
        self.assertEqual(self.app.kind, "meta")


class TestRunTab(GuiTestBase):
    def test_edit_wave_and_gold(self):
        self.open_run()
        run = self.tab("Run")
        state = model.get_run_state(self.app.data)
        for obj, key, var, is_bool in run._rows:
            if key == "current_wave" and obj is state:
                var.set("15")
            if key == "gold":
                var.set("9999")
        run.apply()
        self.assertEqual(state["current_wave"], 15)
        self.assertEqual(state["players_data"][0]["gold"], 9999)

    def test_change_character(self):
        self.open_run()
        run = self.tab("Run")
        player, var = run._char_rows[0]
        var.set("Well Rounded (character_well_rounded)")
        run.apply()
        self.assertEqual(player["current_character"], "character_well_rounded")


class TestGearTabs(GuiTestBase):
    def test_add_and_remove_item(self):
        self.open_run()
        items = self.tab("Items")
        player = model.get_player(model.get_run_state(self.app.data))
        self.assertEqual(len(player["items"]), 2)
        items.add_combo._textvar = None
        items.add_combo._text = "Acid (item_acid)"
        items._add()
        self.assertEqual(len(player["items"]), 3)
        items.apply()
        self.assertEqual([model.entry_id(e) for e in player["items"]],
                         ["item_acid", "item_sausage", "item_acid"])
        # remove first row
        row0 = items._rows[0]
        items._remove_row(row0["row"], row0["entry"])
        items.apply()
        self.assertEqual([model.entry_id(e) for e in player["items"]],
                         ["item_sausage", "item_acid"])

    def test_legacy_string_item_becomes_dict(self):
        self.open_run()
        items = self.tab("Items")
        items.apply()
        player = model.get_player(model.get_run_state(self.app.data))
        self.assertIsInstance(player["items"][1], dict)
        self.assertEqual(player["items"][1]["my_id"], "item_sausage")

    def test_add_weapon_with_stats_dialog(self):
        self.open_run()
        weapons = self.tab("Weapons")
        weapons.add_combo._text = "Knife III (weapon_knife_3)"
        weapons._add()
        weapons.apply()
        player = model.get_player(model.get_run_state(self.app.data))
        w = player["weapons"][-1]
        self.assertEqual(w["my_id"], "weapon_knife_3")
        self.assertEqual(w["stats"]["type"], "melee")


class TestStatsTab(GuiTestBase):
    def test_edit_and_add_stat(self):
        self.open_run()
        stats = self.tab("Stats")
        stats._reload_rows()
        for key, var, scalar, old in stats._row_vars:
            if key == "stat_luck":
                var.set("777")
        stats.apply()
        player = model.get_player(model.get_run_state(self.app.data))
        self.assertEqual(player["effects"]["stat_luck"], 777)
        stats.new_key.insert(0, "stat_armor")
        stats.new_val.insert(0, "12")
        stats._add_stat()
        self.assertEqual(player["effects"]["stat_armor"], 12)


class TestShopTab(GuiTestBase):
    def test_add_offer_and_apply(self):
        self.open_run()
        shop = self.tab("Shop")
        state = model.get_run_state(self.app.data)
        self.assertEqual(len(state["shop_items"][0]), 1)
        state["shop_items"][0].append(model.new_shop_offer("weapon_pistol_1", wave=7, price=30))
        shop.load()
        shop.apply()
        self.assertEqual(len(state["shop_items"][0]), 2)
        self.assertEqual(model.entry_id(state["shop_items"][0][1][0]), "weapon_pistol_1")
        self.assertEqual(state["shop_items"][0][1][1], 7)


class TestRawTab(GuiTestBase):
    def test_tree_populated_and_edit(self):
        self.open_run()
        raw = self.tab("Raw JSON")
        self.assertGreater(len(raw.tree._items), 10)
        # select the current_wave scalar node and edit it via patched askstring
        target = None
        for iid, node in raw.tree._items.items():
            if node["text"] == "current_wave":
                target = iid
        self.assertIsNotNone(target)
        raw.tree._sel = (target,)
        import tkinter as tk
        tk.simpledialog.askstring = lambda *a, **kw: "20"
        raw._edit()
        state = model.get_run_state(self.app.data)
        self.assertEqual(state["current_wave"], 20)

    def test_delete_node(self):
        self.open_run()
        raw = self.tab("Raw JSON")
        target = next(iid for iid, n in raw.tree._items.items() if n["text"] == "bonus_gold")
        raw.tree._sel = (target,)
        raw._delete()
        state = model.get_run_state(self.app.data)
        self.assertNotIn("bonus_gold", state)


class TestSave(GuiTestBase):
    def test_save_writes_backup_and_json(self):
        p = self.open_run()
        run = self.tab("Run")
        state = model.get_run_state(self.app.data)
        for obj, key, var, is_bool in run._rows:
            if key == "current_wave" and obj is state:
                var.set("11")
        self.app._current_tab = run
        self.app.save()
        out = json.loads(Path(p).read_text())
        self.assertEqual(out["current_run_state"]["current_wave"], 11)
        self.assertTrue(Path(str(p) + ".editor.bak").exists())
        self.assertFalse(self.app.dirty)


if __name__ == "__main__":
    unittest.main()
