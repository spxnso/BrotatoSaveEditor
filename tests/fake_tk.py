"""Minimal fake tkinter for headless testing of the GUI logic.

Inject into sys.modules before importing brotato_save_editor:
    import fake_tk; fake_tk.install()
It emulates just enough of tk/ttk for the editor's load()/apply() flows.
"""
import sys
import types


class TclError(Exception):
    pass


class Var:
    def __init__(self, value=None):
        self._v = value

    def get(self):
        return self._v

    def set(self, v):
        self._v = v

    def delete(self, _a, _b=None):
        self._v = ""

    def insert(self, _a, s):
        self._v = (self._v or "") + s

    def trace_add(self, *a):
        pass


class StringVar(Var):
    def __init__(self, value=""):
        super().__init__(value)


class BooleanVar(Var):
    def __init__(self, value=False):
        super().__init__(value)


class Widget:
    def __init__(self, master=None, **kw):
        self.master = master
        self.kw = dict(kw)
        self.children = []
        if master is not None and hasattr(master, "children"):
            master.children.append(self)
        self._textvar = kw.get("textvariable")
        self._text = ""
        self.destroyed = False

    def pack(self, **kw):
        pass

    def grid(self, **kw):
        pass

    def place(self, **kw):
        pass

    def bind(self, *a):
        pass

    def bind_all(self, *a):
        pass

    def unbind_all(self, *a):
        pass

    def configure(self, **kw):
        self.kw.update(kw)

    config = configure

    def cget(self, k):
        return self.kw.get(k)

    def winfo_children(self):
        return [c for c in self.children if not getattr(c, "destroyed", False)]

    def destroy(self):
        self.destroyed = True
        if self.master is not None and self in getattr(self.master, "children", []):
            self.master.children.remove(self)
        self.children = []

    def __str__(self):
        return f"!w{id(self)}"


class Entry(Widget):
    def get(self):
        return self._textvar.get() if self._textvar is not None else self._text

    def insert(self, _i, s):
        if self._textvar is not None:
            self._textvar.insert(0, s)
        else:
            self._text += s

    def delete(self, _a, _b=None):
        if self._textvar is not None:
            self._textvar.delete(0, "end")
        else:
            self._text = ""


class Combobox(Entry):
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self._values = list(kw.get("values", []))

    def configure(self, **kw):
        super().configure(**kw)
        if "values" in kw:
            self._values = list(kw["values"])

    def current(self):
        try:
            return self._values.index(self.get())
        except ValueError:
            return -1


class Button(Widget):
    def invoke(self):
        cmd = self.kw.get("command")
        if cmd:
            cmd()


class Listbox(Widget):
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self._items = []
        self._sel = ()

    def insert(self, _pos, s):
        self._items.append(s)

    def delete(self, i):
        del self._items[i]

    def get(self, i):
        return self._items[i]

    def size(self):
        return len(self._items)

    def curselection(self):
        return self._sel


class Notebook(Widget):
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self.tabs = []
        self._sel = None

    def add(self, child, **kw):
        self.tabs.append(child)
        if self._sel is None:
            self._sel = str(child)

    def forget(self, child):
        if child in self.tabs:
            self.tabs.remove(child)

    def select(self, _tab=None):
        return self._sel


class Treeview(Widget):
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self._items = {}
        self._n = 0
        self._sel = ()

    def insert(self, parent, _pos, **kw):
        self._n += 1
        iid = f"i{self._n}"
        self._items[iid] = {"text": kw.get("text", ""), "values": list(kw.get("values", ())),
                            "parent": parent, "children": [], "open": kw.get("open", False)}
        if parent:
            self._items[parent]["children"].append(iid)
        return iid

    def delete(self, *iids):
        for iid in iids:
            node = self._items.pop(iid, None)
            if node and node["parent"] in self._items:
                self._items[node["parent"]]["children"].remove(iid)
            if node:
                self.delete(*node["children"])

    def get_children(self, iid=""):
        return tuple(self._items[iid]["children"]) if iid else tuple(
            i for i, n in self._items.items() if not n["parent"])

    def item(self, iid, option=None, **kw):
        node = self._items[iid]
        if kw:
            node.update(kw)
        if option is not None:
            if option == "text":
                return node["text"]
            if option == "values":
                return list(node["values"])
            return node.get(option)
        return {"text": node["text"], "values": list(node["values"]), "open": node["open"]}

    def set(self, iid, col, val):
        node = self._items[iid]
        if col == "value":
            node["values"] = [val]
        elif col == "#0":
            node["text"] = val

    def parent(self, iid):
        return self._items[iid]["parent"]

    def selection(self):
        return self._sel

    def heading(self, *a, **kw):
        pass

    def column(self, *a, **kw):
        pass

    def yview(self, *a):
        pass


class Canvas(Widget):
    def create_window(self, *a, **kw):
        return 1

    def bbox(self, *a):
        return (0, 0, 200, 200)

    def itemconfigure(self, *a, **kw):
        pass

    def yview_scroll(self, *a):
        pass

    def yview(self, *a):
        pass


class Scrollbar(Widget):
    def set(self, *a):
        pass


class PhotoImage:
    def __init__(self, file=None, data=None, **kw):
        self.file = file
        self.data = data


class Menu(Widget):
    def add_command(self, **kw):
        pass

    def add_cascade(self, **kw):
        pass

    def add_separator(self, **kw):
        pass


class Style:
    def __init__(self, root=None):
        pass

    def theme_use(self, name):
        pass

    def configure(self, *a, **kw):
        pass

    def map(self, *a, **kw):
        pass


class Tk(Widget):
    def __init__(self, **kw):
        super().__init__(None, **kw)

    def title(self, t=None):
        self._title = t

    def geometry(self, g):
        pass

    def minsize(self, *a):
        pass

    def iconphoto(self, *a):
        pass

    def config(self, **kw):
        self.kw.update(kw)

    def menu(self, m):
        pass

    def mainloop(self):
        pass


class Toplevel(Widget):
    def title(self, t=None):
        self._title = t

    def transient(self, *a):
        pass


# submodules with simple functions
filedialog = types.ModuleType("tkinter.filedialog")
filedialog.askopenfilename = lambda **kw: None
filedialog.asksaveasfilename = lambda **kw: None

messagebox = types.ModuleType("tkinter.messagebox")
messagebox.showerror = lambda *a, **kw: None
messagebox.showinfo = lambda *a, **kw: None

simpledialog = types.ModuleType("tkinter.simpledialog")
simpledialog.askstring = lambda *a, **kw: None


def install():
    tk = types.ModuleType("tkinter")
    tk.Tk = Tk
    tk.Toplevel = Toplevel
    tk.Menu = Menu
    tk.Canvas = Canvas
    tk.Label = Widget
    tk.Listbox = Listbox
    tk.Entry = Entry
    tk.StringVar = StringVar
    tk.BooleanVar = BooleanVar
    tk.PhotoImage = PhotoImage
    tk.TclError = TclError
    tk.filedialog = filedialog
    tk.messagebox = messagebox
    tk.simpledialog = simpledialog

    ttk = types.ModuleType("tkinter.ttk")
    ttk.Frame = Widget
    ttk.Label = Widget
    ttk.Button = Button
    ttk.Entry = Entry
    ttk.Combobox = Combobox
    ttk.Checkbutton = Widget
    ttk.LabelFrame = Widget
    ttk.Notebook = Notebook
    ttk.Treeview = Treeview
    ttk.Scrollbar = Scrollbar
    ttk.Style = Style
    tk.ttk = ttk

    sys.modules["tkinter"] = tk
    sys.modules["tkinter.ttk"] = ttk
    sys.modules["tkinter.filedialog"] = filedialog
    sys.modules["tkinter.messagebox"] = messagebox
    sys.modules["tkinter.simpledialog"] = simpledialog
    return tk
