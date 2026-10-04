"""La ventana de lan-radar: la lista de aparatos a la izquierda y la ficha a la derecha.

Tkinter viene con Python, así que no hace falta instalar nada más. La búsqueda tarda unos
segundos y va en un hilo aparte para que la ventana no se congele; Tkinter no se puede
tocar desde otro hilo, así que el hilo deja el progreso y el resultado en colas y la
ventana las mira cada 100 ms.
"""

from __future__ import annotations

import json
import queue
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont

from . import __version__, demo, net
from .device import ALTA, INFO, MEDIA, NUEVO, Device
from .history import History
from .report import LEVEL_LABEL, ago, brand_text, details, display_name, headline, summary_line
from .scan import Result, scan

ICON = Path(__file__).with_name("icon.png")
ABOUT = (
    "lan-radar mira qué aparatos hay conectados a la red de tu casa y les pregunta quiénes son, "
    "como hace el móvil cuando busca la tele para mandarle un vídeo:\n\n"
    "• La tabla ARP del ordenador: la MAC de cada uno, que dice quién lo fabricó.\n"
    "• Bonjour (mDNS): el nombre que se pone cada aparato, su modelo y lo que sabe hacer.\n"
    "• UPnP (SSDP): la ficha de teles, routers y altavoces.\n"
    "• NetBIOS: el nombre de los ordenadores con Windows.\n"
    "• El DNS del router: el nombre con el que se conectó cada uno.\n"
    "• Unos pocos puertos conocidos (impresora, iPhone, Chromecast…) y el título de su página web.\n\n"
    "Solo revisa la red privada a la que está conectado este ordenador. No entra en ningún "
    "aparato ni prueba contraseñas: solo pregunta lo que cada uno cuenta a quien se lo pregunte."
)


class App:
    def __init__(self, root: tk.Tk, scan_on_start: bool = True):
        self.root = root
        self.jobs: queue.Queue = queue.Queue()
        self.progress_updates: queue.Queue = queue.Queue()
        self.busy = False
        self.result: Result | None = None
        self.history: History | None = None  # None con la casa de ejemplo: sus nombres no se guardan
        self.networks = net.local_networks()
        self.services = tk.BooleanVar(value=True)
        self.items: dict[str, Device | dict] = {}  # fila de la tabla → aparato (o uno que ya no está)

        root.title("lan-radar · ¿Quién está en mi wifi?")
        root.geometry("1040x660")
        root.minsize(760, 460)
        if ICON.exists():
            root.iconphoto(True, tk.PhotoImage(file=str(ICON)))
        self.build()
        root.after(100, self.poll)
        if scan_on_start and self.networks:
            root.after(200, self.search)
        elif not self.networks:
            self.summary.config(
                text="Este ordenador no está conectado a ninguna red privada (¿wifi apagado?). "
                "Puedes ver cómo funciona con Archivo > Ver una casa de ejemplo."
            )

    # La ventana

    def build(self) -> None:
        root = self.root
        style = ttk.Style(root)
        if style.theme_use() == "default" and "clam" in style.theme_names():
            style.theme_use("clam")
        base = tkfont.nametofont("TkDefaultFont")
        self.bold = base.copy()
        self.bold.configure(weight="bold")
        self.big = base.copy()
        self.big.configure(size=base.cget("size") + 4, weight="bold")
        line = base.metrics("linespace")
        style.configure("Treeview", rowheight=line + 8)
        style.configure("Accent.TButton", font=self.bold)

        menu = tk.Menu(root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Buscar otra vez", command=self.search, accelerator="F5")
        file_menu.add_command(label="Ver una casa de ejemplo", command=self.open_demo)
        file_menu.add_command(label="Exportar…", command=self.export, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=root.destroy)
        menu.add_cascade(label="Archivo", menu=file_menu)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(
            label="Qué mira lan-radar", command=lambda: messagebox.showinfo("Qué mira lan-radar", ABOUT, parent=root)
        )
        help_menu.add_command(label="Acerca de lan-radar", command=self.about)
        menu.add_cascade(label="Ayuda", menu=help_menu)
        root.config(menu=menu)
        root.bind_all("<F5>", lambda _: self.search())
        root.bind_all("<Control-r>", lambda _: self.search())
        root.bind_all("<Control-s>", lambda _: self.export())

        top = ttk.Frame(root, padding=(14, 12, 14, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Red:").pack(side="left")
        self.network_box = ttk.Combobox(top, state="readonly", width=34, values=[n.label() for n in self.networks])
        if self.networks:
            self.network_box.current(0)
        self.network_box.pack(side="left", padx=(6, 12))
        ttk.Checkbutton(top, text="Mirar también puertos y páginas web", variable=self.services).pack(side="left")
        self.search_button = ttk.Button(top, text="Buscar", command=self.search, style="Accent.TButton")
        self.search_button.pack(side="right")

        self.summary = ttk.Label(root, padding=(14, 2, 14, 8), justify="left", wraplength=1000)
        self.summary.pack(fill="x")
        root.bind("<Configure>", lambda e: e.widget is root and self.summary.config(wraplength=max(300, e.width - 40)))

        panes = ttk.PanedWindow(root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=14)
        left = ttk.Frame(panes)
        self.tree = ttk.Treeview(left, columns=("ip", "kind", "brand"), selectmode="browse")
        for column, title, width in (
            ("#0", "Aparato", 250),
            ("ip", "IP", 120),
            ("kind", "Tipo", 190),
            ("brand", "Marca", 120),
        ):
            self.tree.heading(column, text=title, anchor="w")
            self.tree.column(column, width=width, stretch=column in ("#0", "kind"))
        self.tree.tag_configure("new", foreground="#067647", font=self.bold)
        self.tree.tag_configure("alert", foreground="#b42318")
        self.tree.tag_configure("group", font=self.bold)
        self.tree.tag_configure("gone", foreground="#6b7280")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.show_selected())
        self.tree.bind("<Double-1>", lambda _: self.rename())
        panes.add(left, weight=3)

        right = ttk.Frame(panes)
        self.detail = tk.Text(
            right,
            wrap="word",
            relief="flat",
            padx=12,
            pady=10,
            width=46,
            font=base,
            background=root.cget("background") if sys.platform == "darwin" else "#ffffff",
        )
        self.detail.tag_configure("title", font=self.big, spacing3=2)
        self.detail.tag_configure("subtitle", foreground="#4b5563", spacing3=10)
        self.detail.tag_configure("label", foreground="#6b7280")
        self.detail.tag_configure("value", lmargin1=0, lmargin2=16)
        self.detail.tag_configure(ALTA, foreground="#b42318", font=self.bold, spacing1=4)
        self.detail.tag_configure(MEDIA, foreground="#b54708", font=self.bold, spacing1=4)
        self.detail.tag_configure(INFO, foreground="#4b5563", spacing1=4)
        self.detail.tag_configure(NUEVO, foreground="#067647", font=self.bold, spacing1=4)
        detail_scroll = ttk.Scrollbar(right, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set, state="disabled")
        self.detail.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")
        panes.add(right, weight=2)

        bottom = ttk.Frame(root, padding=(14, 10, 14, 12))
        bottom.pack(fill="x")
        self.progress = ttk.Progressbar(bottom, mode="determinate", length=160, maximum=1.0)
        self.status_label = ttk.Label(bottom, foreground="#4b5563")
        self.status_label.pack(side="left")
        self.export_button = ttk.Button(bottom, text="Exportar…", command=self.export)
        self.export_button.pack(side="right")
        self.rename_button = ttk.Button(bottom, text="Ponerle nombre…", command=self.rename)
        self.rename_button.pack(side="right", padx=(0, 8))
        self.update_buttons()

    def update_buttons(self) -> None:
        self.search_button.state(["disabled"] if self.busy or not self.networks else ["!disabled"])
        has_result = self.result is not None and not self.busy
        self.export_button.state(["!disabled"] if has_result else ["disabled"])
        selected = self.selected()
        self.rename_button.state(["!disabled"] if has_result and isinstance(selected, Device) else ["disabled"])

    # Lo encontrado

    def show_result(self, result: Result) -> None:
        self.result = result
        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        alerts = sum(1 for d in result.devices for n in d.notes if n["level"] == ALTA)
        new = sum(1 for d in result.devices if d.is_new)
        text = f"{headline(result)}\n{summary_line(result)}."
        extras = []
        if new:
            extras.append(f"{new} nuevo{'s' if new > 1 else ''} desde la última vez (en verde)")
        elif result.first_scan:
            extras.append("Es la primera vez que miro esta red: desde la próxima te diré qué aparatos son nuevos")
        if alerts:
            extras.append(f"{alerts} aviso{'s' if alerts > 1 else ''} importante{'s' if alerts > 1 else ''} (en rojo)")
        if extras:
            text += "\n" + ". ".join(extras) + "."
        self.summary.config(text=text)
        for device in result.devices:
            tags = ("new",) if device.is_new else ("alert",) if any(n["level"] == ALTA for n in device.notes) else ()
            item = self.tree.insert(
                "",
                "end",
                text=display_name(device),
                values=(device.ip, device.kind_label(), brand_text(device)),
                tags=tags,
            )
            self.items[item] = device
        if result.missing:
            group = self.tree.insert(
                "",
                "end",
                text=f"Otras veces estaban, ahora no ({len(result.missing)})",
                open=False,
                tags=("group", "gone"),
            )
            for entry in result.missing:
                item = self.tree.insert(
                    group,
                    "end",
                    text=entry.get("name", "?"),
                    tags=("gone",),
                    values=(entry.get("ip", ""), entry.get("kind", ""), entry.get("brand", "")),
                )
                self.items[item] = entry
        first = self.tree.get_children()
        if first:
            self.tree.selection_set(first[0])
            self.tree.focus(first[0])
        self.show_selected()
        self.update_buttons()

    def selected(self):
        selection = self.tree.selection()
        return self.items.get(selection[0]) if selection else None

    def show_selected(self) -> None:
        item = self.selected()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if isinstance(item, Device):
            self.detail.insert("end", display_name(item) + "\n", "title")
            self.detail.insert("end", f"{item.kind_label()} · {item.ip}\n", "subtitle")
            for note in item.notes:
                self.detail.insert("end", f"{LEVEL_LABEL[note['level']]}: {note['text']}\n", note["level"])
            if item.notes:
                self.detail.insert("end", "\n")
            for label, value in details(item):
                self.detail.insert("end", f"{label}\n", "label")
                self.detail.insert("end", f"{value}\n", "value")
        elif isinstance(item, dict):
            self.detail.insert("end", item.get("name", "?") + "\n", "title")
            self.detail.insert("end", "Ahora no está conectado\n", "subtitle")
            for label, key in (("Tipo", "kind"), ("Última IP", "ip"), ("MAC", "mac"), ("Marca", "brand")):
                if item.get(key):
                    self.detail.insert("end", f"{label}\n", "label")
                    self.detail.insert("end", f"{item[key]}\n", "value")
            self.detail.insert("end", "Visto por última vez\n", "label")
            self.detail.insert("end", f"{ago(item.get('last_seen', ''))}\n", "value")
        self.detail.configure(state="disabled")
        self.update_buttons()

    # Lo que hacen los botones

    def search(self) -> None:
        if self.busy or not self.networks:
            return
        local = self.networks[max(0, self.network_box.current())]
        local = net.choose_target(net.default_target(local), [local])
        services = self.services.get()
        self.history = History()
        history = self.history

        def report(text, fraction):
            self.progress_updates.put((text, fraction))

        self.in_background(
            lambda: scan(local, services=services, progress=report, history=history),
            self.show_result,
            f"Buscando aparatos en {local.network}…",
        )

    def open_demo(self) -> None:
        if self.busy:
            return
        self.history = None
        self.in_background(
            lambda: (time.sleep(0.4), demo.result())[1], self.show_result, "Cargando la casa de ejemplo…"
        )

    def rename(self, name: str | None = None) -> None:
        device = self.selected()
        if not isinstance(device, Device) or self.busy or self.result is None:
            return
        if name is None:
            name = simpledialog.askstring(
                "Ponerle nombre",
                f"¿Cómo quieres llamar a {display_name(device)} ({device.ip})?\n"
                "Se acordará la próxima vez. Déjalo vacío para quitarle el nombre.",
                initialvalue=device.nickname or device.name(),
                parent=self.root,
            )
            if name is None:
                return
        device.nickname = name.strip()
        if self.history is not None:
            self.history.rename(self.result.network_key, device.key(), device.nickname)
            self.history.save()
        item = self.tree.selection()[0]
        self.tree.item(item, text=display_name(device))
        self.show_selected()

    def export(self, path: str | None = None) -> None:
        if self.result is None or self.busy:
            return
        if path is None:
            path = filedialog.asksaveasfilename(
                parent=self.root,
                title="Guardar la lista",
                defaultextension=".json",
                initialfile=f"lan-radar-{self.result.started[:10]}.json",
                filetypes=[("JSON", "*.json"), ("Texto", "*.txt")],
            )
            if not path:
                return
        if path.endswith(".txt"):
            text = self.as_text()
        else:
            text = json.dumps(self.result.to_dict(), ensure_ascii=False, indent=2) + "\n"
        Path(path).write_text(text, encoding="utf-8")
        self.status_label.config(text=f"Guardado en {path}")

    def as_text(self) -> str:
        assert self.result is not None
        lines = [headline(self.result), summary_line(self.result), ""]
        for device in self.result.devices:
            lines.append(f"{device.ip}  {display_name(device)}" + ("  (nuevo)" if device.is_new else ""))
            lines += [f"    {label}: {value}" for label, value in details(device)]
            lines += [f"    {LEVEL_LABEL[n['level']]}: {n['text']}" for n in device.notes]
            lines.append("")
        return "\n".join(lines)

    def about(self) -> None:
        messagebox.showinfo(
            "Acerca de lan-radar",
            f"lan-radar {__version__}\n\n¿Quién está en mi wifi? Los aparatos de la red de casa, con todo lo que "
            "cuentan de sí mismos.\n\nhttps://github.com/espi0207/lan-radar",
            parent=self.root,
        )

    # Trabajo en segundo plano

    def in_background(self, work, done, message: str) -> None:
        self.busy = True
        self.status_label.config(text=message)
        self.progress.configure(value=0)
        self.progress.pack(side="left", before=self.status_label, padx=(0, 10))
        self.update_buttons()

        def worker():
            try:
                self.jobs.put((done, work(), None))
            except Exception as exc:  # que un error no deje la ventana esperando para siempre
                self.jobs.put((done, None, exc))

        threading.Thread(target=worker, daemon=True).start()

    def poll(self) -> None:
        try:
            while True:
                text, fraction = self.progress_updates.get_nowait()
                self.status_label.config(text=text)
                self.progress.configure(value=fraction)
        except queue.Empty:
            pass
        try:
            while True:
                done, result, error = self.jobs.get_nowait()
                self.busy = False
                self.progress.pack_forget()
                if error:
                    self.status_label.config(text="")
                    messagebox.showerror("lan-radar", f"Algo ha fallado: {error}", parent=self.root)
                    self.update_buttons()
                else:
                    self.status_label.config(text="")
                    done(result)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


def self_check() -> int:
    """Para la CI: abre la ventana con la casa de ejemplo (sin tocar la red), le pone nombre
    a un aparato y la exporta, sin que nadie toque nada. Así se sabe que el programa
    instalado funciona de verdad (con Tkinter y todo), no solo que se ha creado."""
    root = tk.Tk()
    app = App(root, scan_on_start=False)
    outcome = {"code": 1}
    steps = iter(["demo", "check"])

    def next_step():
        if app.busy:
            root.after(100, next_step)
            return
        step = next(steps)
        if step == "demo":
            app.open_demo()
            root.after(300, next_step)
            return
        try:
            devices = [i for i in app.items.values() if isinstance(i, Device)]
            new = next(item for item, d in app.items.items() if isinstance(d, Device) and d.is_new)
            app.tree.selection_set(new)
            app.show_selected()
            shown = app.detail.get("1.0", "end")
            app.rename("Prueba")
            renamed = app.tree.item(new, "text") == "Prueba"
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "lista.json"
                app.export(str(out))
                exported = json.loads(out.read_text(encoding="utf-8"))
            ok = (
                len(devices) == len(demo.devices())
                and "Nuevo" in shown
                and renamed
                and len(exported["devices"]) == len(devices)
            )
            outcome["code"] = 0 if ok else 1
        finally:
            root.destroy()

    root.after(500, next_step)
    root.after(60_000, root.destroy)  # por si algo se queda colgado
    root.mainloop()
    return outcome["code"]


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if sys.platform == "win32":
        try:  # sin esto, en pantallas con zoom Windows estira la ventana y se ve borrosa
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    if "--comprobar" in args:
        sys.exit(self_check())
    root = tk.Tk()
    app = App(root, scan_on_start="--demo" not in args)
    if "--demo" in args:
        app.open_demo()
    root.mainloop()


if __name__ == "__main__":
    main()
