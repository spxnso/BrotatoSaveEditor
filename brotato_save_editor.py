#!/usr/bin/env python3
"""Brotato Save Editor - a tkinter GUI to edit Brotato v3 save files.

Works on both save files the game keeps in %APPDATA%/Brotato/<steam_id>/:
  run_v3_<n>.json   - the in-progress run (items, weapons, stats, gold, wave...)
  save_v3_<n>.json  - meta/progress save (unlocks, records...)

Run with:  python3 brotato_save_editor.py
Requires only Python 3 + tkinter (standard library). Icons are bundled in
assets/icons (pulled from the official Brotato wiki, see tools/build_assets.py).
"""
from __future__ import annotations

import json
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import brotato_model as model

APP_TITLE = "Brotato Save Editor"
PLACEHOLDER_PNG = "iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAABRElEQVR4nO2aPW6DQBBGP3stmQvQ0Nm1cwHKHMCRaEG5gJXz2K2Re8q4RpGLUAdRk5ITUJEKy8KsiR1NZhfNa9mfeczuIhgmvv/cwGKm3AH8ldlQgyh6/Y84tBwO8c3rE90S4g68i06kV+Ay+KE7QM1QLFcCbQfuwLvo4pr+ppEJtDF1l7b1p9BZwOS739KXhfFkwFZEgBsR4EYEuBEBbqwXGHwje5TFYon1+gVKKRyP78jzL5J5yASCIEAc71HXNTabN/sE0jRFVVVQSsFx5lTT0O2BLPsEAHieh7L8ppqGfhOvVk84nT7IxicXcF0XRVGQjU8ukCQJmobu4x+5QBiGpOOTC+x2W9LxrX8SiwA3IsCNCHAjAtyIADdnAV0FxCT6ahjjyQBgdhZ0FaTxlVn7OprAXYXuS7hFHv7VwBasP4V+AIwPa40VX9ynAAAAAElFTkSuQmCC"


# --------------------------------------------------------------------------- helpers


class IconCache:
    """Loads and caches tk.PhotoImage icons from assets/icons."""

    def __init__(self):
        self._cache = {}
        try:
            self.placeholder = tk.PhotoImage(data=PLACEHOLDER_PNG)
        except tk.TclError:
            self.placeholder = tk.PhotoImage(width=48, height=48)
            self.placeholder.put("#3a3a42", to=(0, 0, 48, 48))
            self.placeholder.put("#96969e", to=(3, 3, 44, 44))

    def get(self, key):
        if key in self._cache:
            return self._cache[key]
        path = model.icon_path(key)
        img = None
        if path is not None:
            try:
                img = tk.PhotoImage(file=str(path))
            except tk.TclError:
                img = None
        if img is None:
            img = self.placeholder
        self._cache[key] = img
        return img


class ScrollFrame(ttk.Frame):
    """A vertically scrollable container frame."""

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg="#2b2b30")
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))

    def _on_inner(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)

    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")


def combo_values(kind, entities):
    """'Display Name (my_id)' entries for a kind of entity."""
    base = [f"{e['name']} ({e['id']})" for e in entities.values() if e["kind"] == kind]
    if kind == "weapon":
        tiered = []
        for e in entities.values():
            if e["kind"] == "weapon":
                for t in (1, 2, 3, 4):
                    tiered.append(f"{e['name']} {model.ROMAN[t]} ({e['id']}_{t})")
        base = tiered + base
    base.sort(key=str.lower)
    return base


def parse_combo(text):
    if "(" in text and text.endswith(")"):
        return text.rsplit("(", 1)[1][:-1]
    return text.strip()


# --------------------------------------------------------------------------- tabs


class BaseTab(ttk.Frame):
    def __init__(self, app, name):
        super().__init__(app.notebook)
        self.app = app
        self.name = name
        self.build()

    def build(self):
        pass

    def load(self):
        pass

    def apply(self):
        pass


class RunTab(BaseTab):
    """Run-level fields + per-player character/health/level/xp/gold."""

    RUN_SCALARS = [
        ("current_wave", "Wave"), ("current_difficulty", "Difficulty (0-5)"),
        ("current_zone", "Zone"), ("nb_of_waves", "Number of waves"),
        ("is_endless_run", "Endless run"), ("is_coop_run", "Co-op run"),
        ("current_background", "Background"), ("bonus_gold", "Bonus gold"),
        ("total_bonus_gold", "Total bonus gold"), ("reroll_price", "Reroll price"),
        ("last_reroll_price", "Last reroll price"), ("free_rerolls", "Free rerolls"),
        ("initial_free_rerolls", "Initial free rerolls"), ("retries", "Retries"),
        ("max_endless_wave_record_beaten", "Endless record beaten"),
        ("difficulty_unlocked", "Difficulty unlocked"),
    ]
    PLAYER_FIELDS = [("current_health", "Health"), ("current_level", "Level"),
                     ("current_xp", "XP"), ("gold", "Gold / materials"),
                     ("selected_weapon", "Selected weapon"), ("selected_item", "Selected item")]

    def build(self):
        self.body = ttk.Frame(self, padding=10)
        self.body.pack(fill="both", expand=True)
        self._rows = []
        self._char_rows = []

    def load(self):
        for w in self.body.winfo_children():
            w.destroy()
        self._rows = []
        self._char_rows = []
        state = model.get_run_state(self.app.data)
        if not isinstance(state, dict) or not state.get("has_run_state"):
            ttk.Label(self.body, text="This file has no active run (has_run_state = false).",
                      font=("", 11)).pack(pady=10)
            ttk.Button(self.body, text="Create empty run state", command=self._create_run).pack()
            return

        run_frame = ttk.LabelFrame(self.body, text="Run", padding=8)
        run_frame.pack(fill="x", pady=4)
        shown = set()
        for key, label in self.RUN_SCALARS:
            if key in state:
                self._add_scalar(run_frame, len(self._rows), state, key, label)
                shown.add(key)
        reserved = ("players_data", "shop_items", "locked_shop_items")
        other = [k for k, v in state.items()
                 if k not in shown and k not in reserved
                 and isinstance(v, (str, int, float, bool, type(None)))]
        if other:
            ttk.Label(run_frame, text="Other fields:", font=("", 9, "italic")).grid(
                row=len(self._rows), column=0, sticky="w")
            for k in sorted(other):
                self._add_scalar(run_frame, len(self._rows), state, k, k)

        players = model.get_players(state)
        for i, player in enumerate(players):
            pf = ttk.LabelFrame(self.body, text=f"Player {i + 1}", padding=8)
            pf.pack(fill="x", pady=4)
            char_row = ttk.Frame(pf)
            char_row.grid(row=0, column=0, columnspan=3, sticky="w", pady=2)
            ttk.Label(char_row, text="Character").pack(side="left")
            icon_lbl = ttk.Label(char_row, text="")
            icon_lbl.pack(side="left", padx=4)
            var = tk.StringVar(value=self._char_value(player.get("current_character")))
            combo = ttk.Combobox(char_row, textvariable=var, state="readonly", width=44,
                                 values=combo_values("character", self.app.entities))
            combo.pack(side="left")

            def _on_char(_e, v=var, lbl=icon_lbl):
                my_id = parse_combo(v.get())
                lbl.configure(image=self.app.icons.get(model.icon_key_for(my_id)))
            combo.bind("<<ComboboxSelected>>", _on_char)
            _on_char(None)
            self._char_rows.append((player, var))
            for j, (key, label) in enumerate(self.PLAYER_FIELDS, start=1):
                if key in player:
                    self._add_scalar(pf, j, player, key, label)

    def _char_value(self, my_id):
        if not my_id:
            return ""
        return f"{model.display_name(my_id, self.app.entities)} ({my_id})"

    def _add_scalar(self, parent, row, obj, key, label):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=2)
        val = obj.get(key)
        if isinstance(val, bool):
            var = tk.BooleanVar(value=val)
            ttk.Checkbutton(parent, variable=var).grid(row=row, column=1, sticky="w", padx=4)
            self._rows.append((obj, key, var, True))
            return
        var = tk.StringVar(value="" if val is None else str(val))
        ttk.Entry(parent, textvariable=var, width=40).grid(row=row, column=1, sticky="w", padx=4)
        self._rows.append((obj, key, var, False))
        if key == "current_difficulty":
            ttk.Label(parent, text=model.DANGER_NAMES.get(val, ""), foreground="#e8a33d").grid(
                row=row, column=2, sticky="w")

    def _create_run(self):
        model.ensure_run_state(self.app.data)
        self.app.mark_dirty()
        self.load()

    def apply(self):
        for obj, key, var, is_bool in self._rows:
            if is_bool:
                obj[key] = bool(var.get())
            else:
                obj[key] = model.coerce(var.get(), obj.get(key))
        for player, var in self._char_rows:
            player["current_character"] = parse_combo(var.get()) or None


class StatsTab(BaseTab):
    """Editable view of a player's effects dict (the stat block)."""

    def build(self):
        top = ttk.Frame(self, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="Player:").pack(side="left")
        self.player_var = tk.StringVar(value="Player 1")
        self.player_combo = ttk.Combobox(top, textvariable=self.player_var, state="readonly", width=10)
        self.player_combo.pack(side="left", padx=4)
        self.player_combo.bind("<<ComboboxSelected>>", lambda _e: self._reload_rows())
        ttk.Label(top, text="  Filter:").pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_a: self._reload_rows())
        ttk.Entry(top, textvariable=self.filter_var, width=24).pack(side="left", padx=4)
        self.count_lbl = ttk.Label(top, text="")
        self.count_lbl.pack(side="left", padx=8)
        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=6, pady=4)
        addf = ttk.Frame(self, padding=6)
        addf.pack(fill="x")
        ttk.Label(addf, text="Add stat:").pack(side="left")
        self.new_key = ttk.Entry(addf, width=28)
        self.new_key.pack(side="left", padx=4)
        self.new_val = ttk.Entry(addf, width=12)
        self.new_val.pack(side="left", padx=4)
        ttk.Button(addf, text="Add", command=self._add_stat).pack(side="left")
        self._row_vars = []

    def _player_index(self):
        idx = self.player_combo.current()
        if idx < 0:
            idx = 0
        return idx

    def _player(self):
        state = model.get_run_state(self.app.data)
        players = model.get_players(state)
        if not players:
            return None
        return players[min(self._player_index(), len(players) - 1)]

    def load(self):
        state = model.get_run_state(self.app.data)
        players = model.get_players(state)
        self.player_combo.configure(values=[f"Player {i + 1}" for i in range(max(1, len(players)))])
        self._reload_rows()

    def _reload_rows(self):
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        self._row_vars = []
        player = self._player()
        if player is None:
            ttk.Label(self.scroll.inner, text="No active run / player in this file.").pack(pady=8)
            return
        effects = player.get("effects")
        if not isinstance(effects, dict):
            ttk.Label(self.scroll.inner, text="This player has no effects/stat block.").pack(pady=8)
            return
        filt = self.filter_var.get().strip().lower()
        manifest = model.load_icon_manifest()
        keys = sorted(effects, key=lambda k: (not k.startswith("stat_"), k))
        n = 0
        for key in keys:
            if filt and filt not in key.lower():
                continue
            val = effects[key]
            row = ttk.Frame(self.scroll.inner)
            row.pack(fill="x", pady=1)
            if key in manifest:
                ttk.Label(row, image=self.app.icons.get(key)).pack(side="left", padx=2)
            else:
                ttk.Label(row, text="", width=6).pack(side="left")
            ttk.Label(row, text=key, width=34, anchor="w").pack(side="left", padx=2)
            scalar = isinstance(val, (str, int, float, bool, type(None)))
            text = json.dumps(val) if not scalar else ("" if val is None else str(val))
            var = tk.StringVar(value=text)
            ttk.Entry(row, textvariable=var, width=44, state="normal" if scalar else "readonly").pack(side="left", padx=2)
            ttk.Button(row, text="✕", width=2, command=lambda k=key: self._del_stat(k)).pack(side="left")
            self._row_vars.append((key, var, scalar, val))
            n += 1
        self.count_lbl.configure(text=f"{n} stats")

    def _del_stat(self, key):
        player = self._player()
        if player and isinstance(player.get("effects"), dict):
            player["effects"].pop(key, None)
            self.app.mark_dirty()
        self._reload_rows()

    def _add_stat(self):
        player = self._player()
        key = self.new_key.get().strip()
        if not player or not key:
            return
        effects = player.setdefault("effects", {})
        effects[key] = model.coerce(self.new_val.get() or "0", 0)
        self.new_key.delete(0, "end")
        self.new_val.delete(0, "end")
        self.app.mark_dirty()
        self._reload_rows()

    def apply(self):
        player = self._player()
        if not player or not isinstance(player.get("effects"), dict):
            return
        effects = player["effects"]
        for key, var, scalar, old in self._row_vars:
            if key in effects and scalar:
                effects[key] = model.coerce(var.get(), old)


class GearTab(BaseTab):
    """Items or weapons list editor. kind is 'item' or 'weapon'."""

    def __init__(self, app, name, kind):
        self.kind = kind
        super().__init__(app, name)

    def build(self):
        top = ttk.Frame(self, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="Player:").pack(side="left")
        self.player_var = tk.StringVar(value="Player 1")
        self.player_combo = ttk.Combobox(top, textvariable=self.player_var, state="readonly", width=10)
        self.player_combo.pack(side="left", padx=4)
        self.player_combo.bind("<<ComboboxSelected>>", lambda _e: self._reload())
        ttk.Label(top, text="  Add:").pack(side="left", padx=(12, 0))
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_a: self._fill_combo())
        ttk.Entry(top, textvariable=self.filter_var, width=20).pack(side="left", padx=4)
        self.add_combo = ttk.Combobox(top, state="readonly", width=46)
        self.add_combo.pack(side="left", padx=4)
        self._fill_combo()
        ttk.Button(top, text="Add", command=self._add).pack(side="left")
        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=6, pady=4)
        self._rows = []

    def _fill_combo(self):
        filt = self.filter_var.get().strip().lower()
        vals = combo_values(self.kind, self.app.entities)
        if filt:
            vals = [v for v in vals if filt in v.lower()]
        self.add_combo.configure(values=vals)

    def _player(self):
        state = model.get_run_state(self.app.data)
        players = model.get_players(state)
        if not players:
            return None
        idx = self.player_combo.current()
        if idx < 0:
            idx = 0
        return players[min(idx, len(players) - 1)]

    def _list_key(self):
        return "items" if self.kind == "item" else "weapons"

    def load(self):
        state = model.get_run_state(self.app.data)
        players = model.get_players(state)
        self.player_combo.configure(values=[f"Player {i + 1}" for i in range(max(1, len(players)))])
        self._reload()

    def _reload(self):
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        self._rows = []
        player = self._player()
        if player is None:
            ttk.Label(self.scroll.inner, text="No active run / player in this file.").pack(pady=8)
            return
        entries = player.get(self._list_key())
        if not isinstance(entries, list):
            ttk.Label(self.scroll.inner, text=f"No '{self._list_key()}' list found on the player.").pack(pady=8)
            return
        for entry in list(entries):
            self._add_row(entry)

    def _add_row(self, entry):
        my_id = model.entry_id(entry)
        row = ttk.Frame(self.scroll.inner)
        row.pack(fill="x", pady=1)
        icon_lbl = ttk.Label(row, image=self.app.icons.get(model.icon_key_for(my_id)))
        icon_lbl.pack(side="left", padx=2)
        name_lbl = ttk.Label(row, text=model.display_name(my_id, self.app.entities), width=22, anchor="w")
        name_lbl.pack(side="left", padx=2)
        id_var = tk.StringVar(value=my_id)
        id_entry = ttk.Entry(row, textvariable=id_var, width=30)
        id_entry.pack(side="left", padx=2)

        def _upd(_e=None, v=id_var, lbl=icon_lbl, nl=name_lbl):
            mid = v.get().strip()
            lbl.configure(image=self.app.icons.get(model.icon_key_for(mid)))
            nl.configure(text=model.display_name(mid, self.app.entities))
        id_entry.bind("<KeyRelease>", _upd)
        id_entry.bind("<FocusOut>", _upd)

        d = entry if isinstance(entry, dict) else {}
        tier_var = tk.StringVar(value=str(d.get("tier", "")))
        ttk.Label(row, text="tier").pack(side="left")
        ttk.Entry(row, textvariable=tier_var, width=4).pack(side="left", padx=2)
        value_var = tk.StringVar(value=str(d.get("value", "")))
        ttk.Label(row, text="value").pack(side="left")
        ttk.Entry(row, textvariable=value_var, width=7).pack(side="left", padx=2)
        locked_var = tk.BooleanVar(value=bool(d.get("is_locked", False)))
        ttk.Checkbutton(row, text="locked", variable=locked_var).pack(side="left", padx=2)
        if self.kind == "weapon":
            ttk.Button(row, text="stats…", command=lambda e=entry: self._edit_weapon_stats(e)).pack(side="left", padx=2)
        ttk.Button(row, text="✕", width=2,
                   command=lambda r=row, e=entry: self._remove_row(r, e)).pack(side="left")
        self._rows.append({"row": row, "entry": entry, "id": id_var,
                           "tier": tier_var, "value": value_var, "locked": locked_var})

    def _remove_row(self, row, entry):
        row.destroy()
        self._rows = [r for r in self._rows if r["entry"] is not entry]
        self.app.mark_dirty()

    def _add(self):
        player = self._player()
        if player is None:
            return
        my_id = parse_combo(self.add_combo.get())
        if not my_id:
            return
        entry = (model.new_weapon(my_id, self.app.entities) if self.kind == "weapon"
                 else model.new_item(my_id, self.app.entities))
        player.setdefault(self._list_key(), []).append(entry)
        self.app.mark_dirty()
        self._add_row(entry)

    def _edit_weapon_stats(self, entry):
        if isinstance(entry, dict):
            StatsDialog(self, entry.setdefault("stats", {}), title=f"Weapon stats — {model.entry_id(entry)}")

    def apply(self):
        player = self._player()
        if player is None:
            return
        new_list = []
        for r in self._rows:
            my_id = r["id"].get().strip()
            if not my_id:
                continue
            entry = r["entry"]
            if not isinstance(entry, dict):
                entry = (model.new_weapon(my_id, self.app.entities) if self.kind == "weapon"
                         else model.new_item(my_id, self.app.entities))
            model.set_entry_id(entry, my_id)
            if r["tier"].get().strip():
                entry["tier"] = r["tier"].get().strip()
            if r["value"].get().strip():
                entry["value"] = r["value"].get().strip()
            entry["is_locked"] = bool(r["locked"].get())
            new_list.append(entry)
        player[self._list_key()] = new_list


class StatsDialog(tk.Toplevel):
    """Generic key->value dialog for a dict (used for weapon stats)."""

    def __init__(self, parent, target, title="Edit"):
        super().__init__(parent)
        self.title(title)
        self.target = target
        self.transient(parent)
        self._rows = []
        scroll = ScrollFrame(self)
        scroll.pack(fill="both", expand=True, padx=8, pady=8)
        for key in sorted(target, key=str):
            val = target[key]
            row = ttk.Frame(scroll.inner)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=str(key), width=36, anchor="w").pack(side="left", padx=2)
            scalar = isinstance(val, (str, int, float, bool, type(None)))
            var = tk.StringVar(value="" if val is None else str(val))
            ttk.Entry(row, textvariable=var, width=48, state="normal" if scalar else "readonly").pack(side="left", padx=2)
            self._rows.append((key, var, scalar, val))
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=8, pady=6)
        ttk.Button(btns, text="OK", command=self._ok).pack(side="right", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")

    def _ok(self):
        for key, var, scalar, old in self._rows:
            if scalar:
                self.target[key] = model.coerce(var.get(), old)
        self.destroy()


class ShopTab(BaseTab):
    """Edit shop_items (4 player slots of offers) and locked_shop_items."""

    def build(self):
        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=8, pady=8)
        self._slot_rows = []
        self._locked_rows = []

    def load(self):
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        self._slot_rows = []
        self._locked_rows = []
        state = model.get_run_state(self.app.data)
        if not isinstance(state, dict) or not state.get("has_run_state"):
            ttk.Label(self.scroll.inner, text="No active run in this file.").pack(pady=8)
            return
        shop = state.get("shop_items")
        if isinstance(shop, list):
            for i, slot in enumerate(shop):
                self._build_slot(self.scroll.inner, f"Shop — player slot {i + 1}", slot, self._slot_rows)
        locked = state.get("locked_shop_items")
        if isinstance(locked, list) and any(locked):
            for i, slot in enumerate(locked):
                if slot:
                    self._build_slot(self.scroll.inner, f"Locked shop items — slot {i + 1}", slot, self._locked_rows)

    def _build_slot(self, parent, title, slot, store):
        if not isinstance(slot, list):
            slot = []
        frame = ttk.LabelFrame(parent, text=title, padding=6)
        frame.pack(fill="x", pady=4)
        for offer in list(slot):
            self._add_offer_row(frame, offer, store)
        addf = ttk.Frame(frame)
        addf.pack(fill="x", pady=2)
        combo = ttk.Combobox(addf, state="readonly", width=46,
                             values=combo_values("item", self.app.entities) + combo_values("weapon", self.app.entities))
        combo.pack(side="left", padx=2)
        price = ttk.Entry(addf, width=6)
        price.insert(0, "0")
        price.pack(side="left", padx=2)
        state = model.get_run_state(self.app.data)
        wave = ttk.Entry(addf, width=4)
        wave.insert(0, str(state.get("current_wave", 1) if isinstance(state, dict) else 1))
        wave.pack(side="left", padx=2)

        def _add(c=combo, p=price, w=wave, s=slot, f=frame):
            my_id = parse_combo(c.get())
            if not my_id:
                return
            try:
                wv = int(w.get() or 1)
                pr = int(p.get() or 0)
            except ValueError:
                return
            offer = model.new_shop_offer(my_id, wave=wv, price=pr, entities=self.app.entities)
            s.append(offer)
            self._add_offer_row(f, offer, store)
            self.app.mark_dirty()
        ttk.Button(addf, text="Add offer", command=_add).pack(side="left", padx=2)

    def _add_offer_row(self, parent, offer, store):
        d = offer[0] if isinstance(offer, list) and offer and isinstance(offer[0], dict) else {}
        my_id = model.entry_id(offer[0]) if isinstance(offer, list) and offer else ""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=1)
        ttk.Label(row, image=self.app.icons.get(model.icon_key_for(my_id))).pack(side="left", padx=2)
        id_var = tk.StringVar(value=my_id)
        ttk.Entry(row, textvariable=id_var, width=30).pack(side="left", padx=2)
        value_var = tk.StringVar(value=str(d.get("value", "")))
        ttk.Label(row, text="price").pack(side="left")
        ttk.Entry(row, textvariable=value_var, width=6).pack(side="left", padx=2)
        wave_var = tk.StringVar(value=str(offer[1]) if isinstance(offer, list) and len(offer) > 1 else "1")
        ttk.Label(row, text="wave").pack(side="left")
        ttk.Entry(row, textvariable=wave_var, width=4).pack(side="left", padx=2)
        locked_var = tk.BooleanVar(value=bool(d.get("is_locked", False)))
        ttk.Checkbutton(row, text="locked", variable=locked_var).pack(side="left", padx=2)
        ttk.Button(row, text="✕", width=2, command=lambda r=row, o=offer, s=store: self._rm(r, o, s)).pack(side="left")
        store.append({"row": row, "offer": offer, "id": id_var,
                      "value": value_var, "wave": wave_var, "locked": locked_var})

    def _rm(self, row, offer, store):
        row.destroy()
        store[:] = [r for r in store if r["offer"] is not offer]
        self.app.mark_dirty()

    def apply(self):
        state = model.get_run_state(self.app.data)
        if not isinstance(state, dict):
            return
        for key, store in (("shop_items", self._slot_rows), ("locked_shop_items", self._locked_rows)):
            slots = state.get(key)
            if not isinstance(slots, list):
                continue
            for slot in slots:
                if not isinstance(slot, list):
                    continue
                kept = [r for r in store if isinstance(r["offer"], list) and r["offer"] in slot]
                slot[:] = [self._offer_from_row(r) for r in kept]

    def _offer_from_row(self, r):
        offer = r["offer"]
        d = offer[0] if isinstance(offer, list) and offer and isinstance(offer[0], dict) else None
        my_id = r["id"].get().strip()
        if d is None:
            d = model.new_item(my_id, self.app.entities)
            offer = [d, 1]
        model.set_entry_id(d, my_id)
        d["value"] = r["value"].get().strip() or "0"
        d["is_locked"] = bool(r["locked"].get())
        try:
            offer[1] = int(r["wave"].get())
        except (ValueError, IndexError):
            pass
        return offer


class MetaTab(BaseTab):
    """Unlock lists of a save_v3 meta save."""

    def build(self):
        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=8, pady=8)
        self._lists = {}

    def load(self):
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        self._lists = {}
        data = self.app.data
        for key, label in model.META_LIST_KEYS.items():
            if key in data and isinstance(data[key], list):
                self._build_list(self.scroll.inner, data, key, label)

    def _build_list(self, parent, data, key, label):
        frame = ttk.LabelFrame(parent, text=f"{label} ({key})", padding=6)
        frame.pack(fill="x", pady=4)
        lb = tk.Listbox(frame, height=5, width=70)
        lb.pack(side="left", fill="x", expand=True)
        for my_id in data[key]:
            lb.insert("end", f"{model.display_name(my_id, self.app.entities)} ({my_id})")
        bar = ttk.Frame(frame)
        bar.pack(side="left", fill="y", padx=4)
        kind = {"characters_unlocked": "character", "weapons_unlocked": "weapon",
                "items_unlocked": "item"}.get(key)
        combo = ttk.Combobox(bar, state="readonly", width=32,
                             values=combo_values(kind, self.app.entities) if kind else [])
        combo.pack(pady=2)
        raw = ttk.Entry(bar, width=32)
        raw.pack(pady=2)

        def _add():
            my_id = parse_combo(combo.get()) or raw.get().strip()
            if my_id and model.meta_add_unlock(data, key, my_id):
                lb.insert("end", f"{model.display_name(my_id, self.app.entities)} ({my_id})")
                self.app.mark_dirty()
        ttk.Button(bar, text="Add", command=_add).pack(pady=2)

        def _rm():
            for sel in reversed(lb.curselection()):
                lb.delete(sel)
            data[key] = [parse_combo(lb.get(i)) for i in range(lb.size())]
            self.app.mark_dirty()
        ttk.Button(bar, text="Remove selected", command=_rm).pack(pady=2)
        self._lists[key] = (data, lb)

    def apply(self):
        for key, (data, lb) in self._lists.items():
            data[key] = [parse_combo(lb.get(i)) for i in range(lb.size())]


class RawTab(BaseTab):
    """Raw JSON tree editor (fallback for anything the other tabs don't cover)."""

    def build(self):
        bar = ttk.Frame(self, padding=4)
        bar.pack(fill="x")
        for text, cmd in (("Refresh", self.load), ("Edit value", self._edit),
                          ("Add child", self._add_child), ("Delete node", self._delete),
                          ("Expand all", lambda: self._expand(True)),
                          ("Collapse all", lambda: self._expand(False))):
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=2)
        self.tree = ttk.Treeview(self, columns=("value",), show="tree headings")
        self.tree.heading("#0", text="Key")
        self.tree.heading("value", text="Value")
        self.tree.column("#0", width=380)
        self.tree.column("value", width=520)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _e: self._edit())
        self._nodes = {}  # iid -> (parent container, key in parent)
        self._objs = {}   # iid -> the object itself

    def load(self):
        self.tree.delete(*self.tree.get_children())
        self._nodes = {}
        self._objs = {}
        self._populate(self.app.data, "", "<root>", None, None)

    def _populate(self, obj, parent_iid, label, container, ckey):
        if isinstance(obj, dict):
            iid = self.tree.insert(parent_iid, "end", text=label, values=("object",), open=True)
            self._nodes[iid] = (container, ckey)
            self._objs[iid] = obj
            for k, v in obj.items():
                self._populate(v, iid, str(k), obj, k)
        elif isinstance(obj, list):
            iid = self.tree.insert(parent_iid, "end", text=label, values=(f"list[{len(obj)}]",), open=True)
            self._nodes[iid] = (container, ckey)
            self._objs[iid] = obj
            for i, v in enumerate(obj):
                self._populate(v, iid, f"[{i}]", obj, i)
        else:
            iid = self.tree.insert(parent_iid, "end", text=label,
                                   values=("" if obj is None else str(obj),))
            self._nodes[iid] = (container, ckey)
            self._objs[iid] = obj

    def _selected(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def _edit(self):
        iid = self._selected()
        if not iid:
            return
        container, ckey = self._nodes.get(iid, (None, None))
        if container is None or not isinstance(container, (dict, list)):
            return
        cur = container[ckey]
        if isinstance(cur, (dict, list)):
            return
        label = self.tree.item(iid, "text")
        ans = simpledialog.askstring("Edit value", f"{label} =",
                                     initialvalue="" if cur is None else str(cur), parent=self)
        if ans is None:
            return
        new = model.coerce(ans, cur)
        container[ckey] = new
        self.tree.set(iid, "value", "" if new is None else str(new))
        self.app.mark_dirty()

    def _add_child(self):
        iid = self._selected() or ""
        obj = self._objs.get(iid) if iid else None
        if iid and not isinstance(obj, (dict, list)):
            # a scalar is selected: add to its parent object instead
            obj = self._objs.get(self.tree.parent(iid))
        if obj is None:
            obj = self.app.data
        container = obj
        if not isinstance(container, (dict, list)):
            messagebox.showinfo("Add child", "Select an object or list node first.", parent=self)
            return
        key = simpledialog.askstring("Add child", "Key (for lists use an index, empty = append):", parent=self)
        if key is None:
            return
        val = simpledialog.askstring("Add child", "Value (JSON):", initialvalue="0", parent=self)
        if val is None:
            return
        parsed = model.coerce(val, 0)
        if isinstance(container, dict):
            container[key] = parsed
        else:
            if key.strip().lstrip("-").isdigit():
                container.insert(int(key), parsed)
            else:
                container.append(parsed)
        self.app.mark_dirty()
        self.load()

    def _delete(self):
        iid = self._selected()
        if not iid:
            return
        container, ckey = self._nodes.get(iid, (None, None))
        if container is None or not isinstance(container, (dict, list)):
            return
        if isinstance(container, dict):
            container.pop(ckey, None)
        else:
            try:
                del container[ckey]
            except (IndexError, TypeError):
                pass
        self.app.mark_dirty()
        self.load()

    def _expand(self, open_all):
        def rec(iid):
            self.tree.item(iid, open=open_all)
            for c in self.tree.get_children(iid):
                rec(c)
        for c in self.tree.get_children(""):
            rec(c)

    def apply(self):
        pass  # raw edits are applied immediately


# --------------------------------------------------------------------------- app


class EditorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1150x720")
        self.minsize(900, 560)
        self.entities = model.load_entities()
        self.icons = IconCache()
        app_icon = self.icons.get("app_icon")
        if app_icon is not self.icons.placeholder:
            try:
                self.iconphoto(True, app_icon)
            except tk.TclError:
                pass

        self._style()
        self.path = None
        self.data = None
        self.kind = "unknown"
        self.dirty = False
        self.tabs = []
        self._current_tab = None

        self._menu()
        self._toolbar()
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=6, pady=4)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.status_var = tk.StringVar(
            value="Open a Brotato save file (run_v3_*.json or save_v3_*.json) to begin.")
        ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w", padding=4).pack(
            fill="x", side="bottom")
        self._build_tabs()

    def _style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        bg, fg, accent = "#2b2b30", "#e8e8e8", "#e8a33d"
        style.configure(".", background=bg, foreground=fg, fieldbackground="#3a3a42")
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TLabelframe", background=bg, foreground=fg)
        style.configure("TLabelframe.Label", background=bg, foreground=accent)
        style.configure("TButton", background="#3a3a42", foreground=fg)
        style.configure("TEntry", fieldbackground="#3a3a42", foreground=fg)
        style.configure("TNotebook", background=bg)
        style.configure("TNotebook.Tab", background="#3a3a42", foreground=fg)
        style.map("TNotebook.Tab", background=[("selected", bg)], foreground=[("selected", accent)])
        style.configure("Treeview", background="#232328", fieldbackground="#232328", foreground=fg)
        style.configure("TCheckbutton", background=bg, foreground=fg)
        self.configure(bg=bg)

    def _menu(self):
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Open…", accelerator="Ctrl+O", command=self.open_dialog)
        filemenu.add_command(label="Open Brotato save folder…", command=self.open_brotato_dir)
        filemenu.add_command(label="Save", accelerator="Ctrl+S", command=self.save)
        filemenu.add_command(label="Save as…", command=self.save_as)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=filemenu)
        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="About", command=self._about)
        menubar.add_cascade(label="Help", menu=helpmenu)
        self.config(menu=menubar)
        self.bind("<Control-o>", lambda _e: self.open_dialog())
        self.bind("<Control-s>", lambda _e: self.save())

    def _toolbar(self):
        bar = ttk.Frame(self, padding=4)
        bar.pack(fill="x", padx=6, pady=2)
        ttk.Button(bar, text="Open…", command=self.open_dialog).pack(side="left", padx=2)
        ttk.Button(bar, text="Save", command=self.save).pack(side="left", padx=2)
        ttk.Button(bar, text="Open Brotato folder…", command=self.open_brotato_dir).pack(side="left", padx=2)
        self.path_var = tk.StringVar(value="(no file loaded)")
        ttk.Label(bar, textvariable=self.path_var, foreground="#e8a33d").pack(side="left", padx=12)

    def _about(self):
        messagebox.showinfo(
            "About " + APP_TITLE,
            APP_TITLE + "\n\nEdit Brotato v3 save files (run_v3_*.json / save_v3_*.json).\n\n"
            "Save location: %APPDATA%/Brotato/<steam_id>/ (Windows), or the Proton prefix "
            "AppData/Roaming/Brotato/<steam_id>/ (Linux/Steam Deck).\n\n"
            "Close the game before saving — it rewrites the files when it exits.\n"
            "A .editor.bak backup is written next to the file on every save.\n\n"
            "Icons: official Brotato wiki (brotato.wiki.spellsandguns.com).",
            parent=self)

    def _build_tabs(self):
        for t in self.tabs:
            self.notebook.forget(t)
        self.tabs = []
        if self.data is None:
            tab = ttk.Frame(self.notebook)
            ttk.Label(tab, text="No save file loaded. Use File > Open…", font=("", 12)).pack(pady=40)
            self.notebook.add(tab, text="—")
            self.tabs = [tab]
            self._current_tab = None
            return
        builders = [("Run", lambda: RunTab(self, "Run")),
                    ("Stats", lambda: StatsTab(self, "Stats")),
                    ("Items", lambda: GearTab(self, "Items", "item")),
                    ("Weapons", lambda: GearTab(self, "Weapons", "weapon")),
                    ("Shop", lambda: ShopTab(self, "Shop"))]
        if self.kind == "meta" or any(k in self.data for k in model.META_LIST_KEYS):
            builders.append(("Unlocks", lambda: MetaTab(self, "Unlocks")))
        builders.append(("Raw JSON", lambda: RawTab(self, "Raw JSON")))
        for name, make in builders:
            tab = make()
            self.notebook.add(tab, text=name)
            self.tabs.append(tab)
        for t in self.tabs:
            t.load()
        self._current_tab = self.tabs[0]

    def _on_tab_changed(self, _e):
        selected = self.notebook.select()
        for t in self.tabs:
            if str(t) == selected and t is not self._current_tab:
                if self._current_tab is not None:
                    try:
                        self._current_tab.apply()
                    except Exception as exc:
                        messagebox.showerror("Could not apply changes", str(exc), parent=self)
                self._current_tab = t
                t.load()

    def mark_dirty(self):
        self.dirty = True
        self._update_title()

    def _update_title(self):
        self.title(APP_TITLE + (f" — {self.path}" if self.path else "") + (" *" if self.dirty else ""))

    def status(self, msg):
        self.status_var.set(msg)

    def open_dialog(self):
        path = filedialog.askopenfilename(
            title="Open Brotato save file", initialdir=self._default_dir(),
            filetypes=[("Brotato saves", "*.json"), ("All files", "*.*")])
        if path:
            self.open_file(path)

    def _default_dir(self):
        if self.path:
            return str(Path(self.path).parent)
        for cand in self._brotato_dirs():
            if cand.is_dir():
                return str(cand)
        return str(Path.home())

    def _brotato_dirs(self):
        home = Path.home()
        cands = []
        appdata = os.environ.get("APPDATA")
        if appdata:
            cands.append(Path(appdata) / "Brotato")
        for steam in (home / ".local/share/Steam", home / ".steam/steam", home / ".steam/root"):
            if steam.is_dir():
                cands += list(steam.glob("steamapps/compatdata/1942280/pfx/drive_c/users/*/AppData/Roaming/Brotato"))
        return cands

    def open_brotato_dir(self):
        dirs = [d for d in self._brotato_dirs() if d.is_dir()]
        if not dirs:
            messagebox.showinfo(
                "Brotato folder not found",
                "Could not find a Brotato save folder automatically. "
                "Use File > Open… and pick run_v3_*.json / save_v3_*.json manually.", parent=self)
            return
        path = filedialog.askopenfilename(
            title=f"Open save from {dirs[0]}", initialdir=str(dirs[0]),
            filetypes=[("Brotato saves", "*.json"), ("All files", "*.*")])
        if path:
            self.open_file(path)

    def open_file(self, path):
        try:
            data, kind = model.load_save(path)
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Could not open file", str(exc), parent=self)
            return
        if not isinstance(data, dict):
            messagebox.showerror("Unsupported file", "The root of this file is not a JSON object.", parent=self)
            return
        self.path = path
        self.data = data
        self.kind = kind
        self.dirty = False
        self.path_var.set(path)
        self._update_title()
        self._build_tabs()
        state = model.get_run_state(data)
        if kind == "run" and isinstance(state, dict) and not state.get("has_run_state"):
            self.status("Run file loaded — no active run stored (has_run_state=false). See the Run tab to create one.")
        elif kind == "run":
            self.status("Run file loaded.")
        elif kind == "meta":
            self.status("Meta/progress save loaded.")
        else:
            self.status("JSON file loaded (unknown type) — use the Raw JSON tab.")

    def _apply_current(self):
        if self._current_tab is not None:
            self._current_tab.apply()

    def save(self):
        if not self.path or self.data is None:
            messagebox.showinfo("Nothing to save", "Open a save file first.", parent=self)
            return
        try:
            self._apply_current()
        except Exception as exc:
            messagebox.showerror("Could not apply changes", str(exc), parent=self)
            return
        try:
            bak = model.save_save(self.path, self.data, backup=True)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
            return
        self.dirty = False
        self._update_title()
        self.status(f"Saved {self.path} (backup: {bak.name})")

    def save_as(self):
        if self.data is None:
            messagebox.showinfo("Nothing to save", "Open a save file first.", parent=self)
            return
        try:
            self._apply_current()
        except Exception as exc:
            messagebox.showerror("Could not apply changes", str(exc), parent=self)
            return
        path = filedialog.asksaveasfilename(
            title="Save as", initialdir=self._default_dir(), defaultextension=".json",
            filetypes=[("Brotato saves", "*.json"), ("All files", "*.*")])
        if not path:
            return
        self.path = path
        self.path_var.set(path)
        self.dirty = False
        self._update_title()
        self.save()


def main():
    app = EditorApp()
    if len(sys.argv) > 1:
        app.open_file(sys.argv[1])
    app.mainloop()


if __name__ == "__main__":
    main()
