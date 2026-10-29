#!/usr/bin/env python3
"""Główne okno Tkinter — weryfikator BIOS Dell.

Logika sieciowa i plików jest w ``dell_bios_core``; wybór wierszy, kolumny
i komunikaty pobierania — w ``dell_gui_logic``. Tu tylko układ widgetów,
wątki (żeby nie blokować GUI) oraz obsługa zdarzeń myszy/klawiatury.

Edycja układu: ``outer`` = całe okno; treść przewijana w ``Canvas`` + ``inner``;
przyciski w ``_buttons_frame`` są **poza** canvasem, pakowane od dołu okna
(``side=tk.BOTTOM``), żeby przy niskim oknie zawsze były widoczne.
"""
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import dell_bios_core as core
import dell_gui_logic as gui_logic


class App(tk.Tk):
    """Okno aplikacji: tabela wyników, modele użytkownika, pobieranie BIOS."""

    def __init__(self):
        super().__init__()
        self.title("Weryfikator wersji BIOS")
        self.geometry("1100x480")
        self._busy = False
        self._rows = []  # ostatni raport sprawdzenia — źródło wierszy Treeview

        outer = ttk.Frame(self, padding=20)
        outer.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        dell_tab = ttk.Frame(self.notebook)
        self.notebook.add(dell_tab, text="Dell")

        # --- Canvas: przewijanie całej treści (głównie Treeview) przy niskim oknie ---
        self._canvas = tk.Canvas(dell_tab, highlightthickness=0)
        self._win_scroll = ttk.Scrollbar(
            dell_tab, orient=tk.VERTICAL, command=self._canvas.yview
        )
        self._canvas.configure(yscrollcommand=self._win_scroll.set)

        inner = ttk.Frame(self._canvas)
        self._inner = inner
        self._canvas_window = self._canvas.create_window(
            0, 0, anchor=tk.NW, window=inner
        )

        def _on_inner_configure(_event):
            self._sync_canvas_window()

        def _on_canvas_configure(event):
            self._canvas_width = event.width
            self._canvas_height = event.height
            self._sync_canvas_window()

        self._canvas_width = 1
        self._canvas_height = 1
        inner.bind("<Configure>", _on_inner_configure)
        self._canvas.bind("<Configure>", _on_canvas_configure)

        # --- Treeview: kolumny logiczne stałe; kolejność wyświetlania z gui-ustawienia.json ---
        tree_container = ttk.Frame(inner)
        tree_container.pack(fill=tk.BOTH, expand=True)
        self.state_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "bios-stan.json"
        )
        self.settings_path = gui_logic.gui_settings_path(self._app_dir())
        self.column_order = gui_logic.load_column_order(self.settings_path)
        self._drag_from = None  # indeks kolumny przy przeciąganiu nagłówka
        self.tree = ttk.Treeview(
            tree_container,
            columns=gui_logic.LOGICAL_COLUMNS,
            displaycolumns=self.column_order,
            show="headings",
            height=16,
        )
        for col in gui_logic.LOGICAL_COLUMNS:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=280 if col == "Link" else 140, stretch=True)
        self._tree_scroll = ttk.Scrollbar(
            tree_container, orient=tk.VERTICAL, command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=self._tree_scroll.set)
        self.tree.configure(selectmode="extended")
        gui_logic.configure_bios_age_tags(self.tree)
        self.tree.bind("<ButtonPress-1>", self._on_tree_press)
        self.tree.bind("<ButtonRelease-1>", self._on_tree_release)
        # Suwak wierszy przed Treeview — przy wysokim oknie dostaje pełną wysokość kontenera.
        self._tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # --- Przyciski pod listą (poza canvasem, na dole zakładki Dell) ---
        self._buttons_frame = ttk.Frame(dell_tab)
        hint_label = ttk.Label(
            self._buttons_frame,
            text=core.MODEL_FORMAT_HINT,
            wraplength=1000,
            justify=tk.LEFT,
        )
        hint_label.pack(fill=tk.X, pady=(0, 6))
        add_row = ttk.Frame(self._buttons_frame)
        add_row.pack(fill=tk.X, pady=(0, 6))
        self.model_entry = ttk.Entry(add_row)
        self.model_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_add = ttk.Button(add_row, text="Dodaj model", command=self.on_add_model)
        self.btn_add.pack(side=tk.LEFT, padx=(8, 0))
        self.btn_remove = ttk.Button(
            add_row, text="Usuń zaznaczony model", command=self.on_remove_model
        )
        self.btn_remove.pack(side=tk.LEFT, padx=(8, 0))
        self.btn_copy = ttk.Button(
            self._buttons_frame, text="Kopiuj link", command=self.on_copy
        )
        self.btn_copy.pack(fill=tk.X, pady=(0, 4))
        self.tree.bind("<Control-c>", self.on_copy)
        self.btn_download_dir = ttk.Button(
            self._buttons_frame,
            text="Ustaw folder pobierania",
            command=self.on_set_download_dir,
        )
        self.btn_download_dir.pack(fill=tk.X, pady=(0, 4))
        self.btn_download_selected = ttk.Button(
            self._buttons_frame,
            text="Pobierz zaznaczone elementy",
            command=self.on_download_selected,
        )
        self.btn_download_selected.pack(fill=tk.X, pady=(0, 4))
        self.btn_download = ttk.Button(
            self._buttons_frame,
            text="Pobierz wszystkie nowe wersje",
            command=self.on_download,
        )
        self.btn_download.pack(fill=tk.X, pady=(0, 4))
        self.btn = ttk.Button(
            self._buttons_frame,
            text="Sprawdź aktualizacje wersji BIOS",
            command=self.on_check,
        )
        self.btn.pack(fill=tk.X)

        self.status = tk.StringVar(value="Gotowy")
        status_label = ttk.Label(dell_tab, textvariable=self.status)

        status_label.pack(side=tk.BOTTOM, anchor=tk.W)
        self._buttons_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        self._win_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Kółko myszy: przewija okno, chyba że Treeview ma jeszcze własne wiersze do przewinięcia.
        wheel_widgets = (
            self._canvas,
            inner,
            self._buttons_frame,
            self.tree,
            self._tree_scroll,
            hint_label,
            self.model_entry,
            self.btn_add,
            self.btn_remove,
            self.btn_copy,
            self.btn_download_dir,
            self.btn_download_selected,
            self.btn_download,
            self.btn,
            status_label,
        )
        for widget in wheel_widgets:
            for seq in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
                widget.bind(seq, self._scroll_window)

        from hp_gui_tab import HpTab

        hp_tab_frame = ttk.Frame(self.notebook)
        self.notebook.add(hp_tab_frame, text="HP")
        self.hp_tab = HpTab(hp_tab_frame, self._app_dir(), self.after)

    def _sync_canvas_window(self):
        """Dopasowuje ramkę w Canvas do szerokości okna i co najmniej wysokości canvasu.

        Bez ustawienia ``height`` na create_window przy wysokim oknie zostaje szara
        pustka pod Treeview — stąd ``max(canvas_h, req_h)``.
        """
        width = max(1, int(self._canvas_width))
        canvas_h = max(1, int(self._canvas_height))
        self._inner.update_idletasks()
        req_h = max(1, self._inner.winfo_reqheight())
        height = max(canvas_h, req_h)
        self._canvas.itemconfigure(self._canvas_window, width=width, height=height)
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _scroll_window(self, event):
        """Przewijanie pionowe canvasu (Linux Button-4/5, Windows/Mac MouseWheel)."""
        if getattr(event, "num", None) == 4:
            direction = -1
        elif getattr(event, "num", None) == 5:
            direction = 1
        elif getattr(event, "delta", 0) > 0:
            direction = -1
        else:
            direction = 1

        widget = event.widget
        if widget in (self.tree, self._tree_scroll):
            top, bottom = self.tree.yview()
            if bottom - top < 0.999:
                return
        self._canvas.yview_scroll(direction, "units")
        return "break"

    def _heading_index(self, col_id: str):
        return gui_logic.display_column_index(col_id, len(self.column_order))

    def _on_tree_press(self, event):
        """Rozpoczęcie przeciągania kolumny — tylko gdy kliknięto nagłówek."""
        self._drag_from = None
        if self.tree.identify_region(event.x, event.y) != "heading":
            return
        self._drag_from = self._heading_index(self.tree.identify_column(event.x))
        if self._drag_from is not None:
            self.tree.grab_set()

    def _on_tree_release(self, event):
        """Upuszczenie kolumny: x wskazuje docelową kolumnę (także nad wierszami). Zapis do gui-ustawienia.json."""
        source = self._drag_from
        self._drag_from = None
        if source is None:
            return
        try:
            self.tree.grab_release()
        except tk.TclError:
            pass
        if event.x < 0 or event.x >= self.tree.winfo_width():
            return
        target = self._heading_index(self.tree.identify_column(event.x))
        if target is None:
            return
        order = gui_logic.move_column(
            self.column_order, self.column_order[source], self.column_order[target]
        )
        if order == self.column_order:
            return
        self.column_order = order
        self.tree.configure(displaycolumns=self.column_order)
        gui_logic.save_column_order(self.settings_path, self.column_order)

    def on_copy(self, event=None):
        indices = gui_logic.selected_indices_in_order(
            self.tree.get_children(), self.tree.selection()
        )
        index = indices[0] if indices else None
        result = gui_logic.link_from_selection(self._rows, index)
        if result["ok"]:
            self.clipboard_clear()
            self.clipboard_append(result["link"])
            self.update()
        self.status.set(result["message"])
        return "break"

    def _set_busy(self, busy: bool) -> None:
        """Blokuje akcje w trakcie sieci (sprawdzenie, dodawanie modelu, pobieranie)."""
        self._busy = busy
        state = ["disabled"] if busy else ["!disabled"]
        self.btn.state(state)
        self.btn_download_selected.state(state)
        self.btn_download.state(state)
        self.btn_add.state(state)
        self.btn_remove.state(state)

    def _app_dir(self) -> str:
        return os.path.dirname(self.state_path)

    def _models_for_check(self):
        """Lista modeli do ``run_live_check``: wbudowane + użytkownika minus ``excluded``."""
        path = core.user_models_path(self._app_dir())
        loaded = core.read_user_models(path)
        if loaded["corrupt"]:
            return None
        return core.models_for_check(
            core.DELL_MODELS, loaded["models"], loaded["excluded"]
        )

    def on_check(self):
        if self._busy:
            return
        models = self._models_for_check()
        if models is None:
            message = "Nie można odczytać modele-uzytkownika.json. Plik nie został zmieniony."
            self.status.set(message)
            messagebox.showerror("Model", message)
            return
        self._set_busy(True)
        self.status.set("Pobieranie…")
        threading.Thread(target=self._worker, args=(models,), daemon=True).start()

    def _worker(self, models):
        """Wątek: pobiera katalogi Dell i buduje raport; wynik wraca w wątku GUI przez ``after``."""
        try:
            report = core.run_live_check(self.state_path, models)
        except Exception as exc:
            report = {"exit_code": 1, "fatal_message": str(exc), "rows": []}
        self.after(0, lambda: self._apply(report))

    def on_add_model(self):
        if self._busy:
            return
        query = self.model_entry.get()
        if not core.normalize_model_query(query):
            message = "Pusta nazwa modelu. " + core.MODEL_FORMAT_HINT
            self.status.set(message)
            messagebox.showerror("Model", message)
            return
        path = core.user_models_path(self._app_dir())
        loaded = core.read_user_models(path)
        if loaded["corrupt"]:
            message = "Nie można odczytać modele-uzytkownika.json. Plik nie został zmieniony."
            self.status.set(message)
            messagebox.showerror("Model", message)
            return
        self._set_busy(True)
        self.status.set("Szukanie modelu w katalogu Dell…")
        threading.Thread(
            target=self._add_worker,
            args=(query, loaded["models"], loaded["excluded"]),
            daemon=True,
        ).start()

    def _add_worker(self, query, existing, excluded=None):
        if excluded is None:
            excluded = []
        try:
            found = core.lookup_model_live(query)
        except Exception as exc:
            found = {"ok": False, "error": str(exc), "name": "", "system_ids": []}
        self.after(0, lambda: self._add_done(found, existing, excluded))

    def _add_done(self, found, existing, excluded=None):
        if excluded is None:
            excluded = []
        if not found["ok"]:
            self._set_busy(False)
            self.status.set(found["error"])
            messagebox.showerror("Model", found["error"])
            return
        current = core.models_for_check(core.DELL_MODELS, existing, excluded)
        if core.model_already_listed(found["name"], current):
            self._set_busy(False)
            message = "Ten model jest już na liście."
            self.status.set(message)
            messagebox.showinfo("Model", message)
            return
        updated_excluded = [name for name in excluded if name != found["name"]]
        if any(m["name"] == found["name"] for m in core.DELL_MODELS):
            updated = list(existing)
        else:
            updated = list(existing) + [
                {"name": found["name"], "system_ids": found["system_ids"]}
            ]
        try:
            core.save_user_models(
                core.user_models_path(self._app_dir()), updated, updated_excluded
            )
        except Exception as exc:
            self._set_busy(False)
            message = str(exc)
            self.status.set(message)
            messagebox.showerror("Model", message)
            return
        models = core.models_for_check(core.DELL_MODELS, updated, updated_excluded)
        self.status.set("Pobieranie…")
        threading.Thread(target=self._worker, args=(models,), daemon=True).start()

    def _apply(self, report):
        self._set_busy(False)
        if report["fatal_message"]:
            self.status.set(report["fatal_message"])
            messagebox.showerror("Błąd", report["fatal_message"])
            return
        self._rows = [dict(row) for row in report["rows"]]
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in self._rows:
            tag = gui_logic.release_age_tag(row.get("Data wydania"))
            if tag:
                self.tree.insert(
                    "", tk.END, values=gui_logic.row_values(row), tags=(tag,)
                )
            else:
                self.tree.insert("", tk.END, values=gui_logic.row_values(row))
        if report["exit_code"] == 0:
            self.status.set("Gotowe — wszystkie modele odczytane.")
        else:
            self.status.set("Zakończono z błędami niektórych modeli.")

    def on_remove_model(self):
        """Usuwa zaznaczone modele z listy sprawdzenia (excluded lub wpis w modele-uzytkownika.json)."""
        if self._busy:
            return
        sel = self.tree.selection()
        if not sel:
            self.status.set("Zaznacz model do usunięcia.")
            return
        children = self.tree.get_children()
        selected = set(sel)
        names = []
        seen = set()
        for index, item in enumerate(children):
            if item not in selected or index >= len(self._rows):
                continue
            name = self._rows[index].get("Model")
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        if not names:
            self.status.set("Zaznacz model do usunięcia.")
            return
        path = core.user_models_path(self._app_dir())
        loaded = core.read_user_models(path)
        if loaded["corrupt"]:
            message = "Nie można odczytać modele-uzytkownika.json. Plik nie został zmieniony."
            self.status.set(message)
            messagebox.showerror("Model", message)
            return
        models, excluded = core.remove_listed_models(
            core.DELL_MODELS, loaded["models"], loaded["excluded"], names
        )
        try:
            core.save_user_models(path, models, excluded)
        except Exception as exc:
            message = str(exc)
            self.status.set(message)
            messagebox.showerror("Model", message)
            return
        removed = set(names)
        kept = []
        for index, row in enumerate(self._rows):
            if row.get("Model") in removed:
                if index < len(children):
                    self.tree.delete(children[index])
            else:
                kept.append(row)
        self._rows = kept
        self.status.set("Usunięto model z listy sprawdzenia.")

    def on_set_download_dir(self):
        """Dialog folderu. Anulowanie nic nie zapisuje i nie zmienia paska stanu."""
        app_dir = self._app_dir()
        current = gui_logic.load_download_dir(self.settings_path, app_dir)
        initial = gui_logic.askdirectory_initial(current, app_dir)
        chosen = filedialog.askdirectory(initialdir=initial)
        saved = gui_logic.chosen_download_dir(chosen)
        if saved is None:
            return
        gui_logic.save_download_dir(self.settings_path, saved)
        self.status.set(gui_logic.download_folder_status(saved))

    def on_download_selected(self):
        """Pobiera pliki dla zaznaczonych wierszy (dowolna kolumna Zmiana, nie tylko „nowa wersja”)."""
        if self._busy:
            return
        result = gui_logic.rows_for_selected_download(
            self._rows, self.tree.get_children(), self.tree.selection()
        )
        if not result["ok"]:
            self.status.set(result["message"])
            return
        dest = gui_logic.load_download_dir(self.settings_path, self._app_dir())
        blocked = gui_logic.download_dir_block(dest)
        if blocked is not None:
            self.status.set(blocked)
            return
        self._set_busy(True)
        self.status.set("Pobieranie plików BIOS…")
        rows = [dict(row) for row in result["rows"]]
        threading.Thread(
            target=self._download_worker,
            args=(rows, False, dest),
            daemon=True,
        ).start()

    def on_download(self):
        """Pobiera tylko wiersze ze Zmiana zaczynającą się od „nowa wersja” (``only_new_versions=True``)."""
        if self._busy:
            return
        if not self._rows:
            self.status.set(gui_logic.download_status_message(False, 0, 0, 0))
            return
        dest = gui_logic.load_download_dir(self.settings_path, self._app_dir())
        blocked = gui_logic.download_dir_block(dest)
        if blocked is not None:
            self.status.set(blocked)
            return
        self._set_busy(True)
        self.status.set("Pobieranie plików BIOS…")
        rows = [dict(row) for row in self._rows]
        threading.Thread(
            target=self._download_worker,
            args=(rows, True, dest),
            daemon=True,
        ).start()

    def _download_worker(self, rows, only_new_versions=True, dest=None):
        """Wątek pobierania: plan w ``core.plan_bios_downloads``, pliki do ``dest``."""
        if dest is None:
            dest = os.path.join(os.path.dirname(self.state_path), "pobrane-bios")
        message = None
        done = False
        try:
            plan = core.plan_bios_downloads(
                rows, only_new_versions=only_new_versions
            )
            fetched = core.download_planned_files(
                plan["planned"], dest, core.download_bytes
            )
            error_count = len(plan["rejected"]) + len(fetched["errors"])
            planned_count = len(plan["planned"]) + len(plan["rejected"])
            message = gui_logic.download_status_message(
                True,
                planned_count,
                len(fetched["saved"]),
                error_count,
                only_new_versions=only_new_versions,
                dest_dir=dest,
            )
            done = True
        except Exception as exc:
            message = gui_logic.download_error_status(str(exc), dest)
        finally:
            self.after(0, lambda: self._download_settle(done, message))

    def _download_settle(self, done, message):
        if done:
            self._download_done(message)
            return
        self._set_busy(False)
        self.status.set(message)

    def _download_done(self, message):
        self._set_busy(False)
        self.status.set(message)


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
