"""Logika GUI bez Tkinter — testowalna osobno od ``sprawdz_bios_dell_gui``.

Kolejność kolumn, folder pobierania, wybór wierszy do pobrania i teksty statusu.
Zmiana nazw kolumn w tabeli: edytuj ``LOGICAL_COLUMNS`` i dopasuj nagłówki w Treeview.
"""

import json
import os
from datetime import date

import hp_bios_core as hp_core

# Stała kolejność kluczy w słowniku wiersza (Treeview ``columns=``); displaycolumns może być inna.
LOGICAL_COLUMNS = (
    "Model",
    "Wersja BIOS",
    "Data wydania",
    "Zmiana",
    "Poprzednia weryfikacja",
    "Ważność",
    "Link",
)


def normalize_column_order(saved, known=None) -> list:
    """Scala zapisaną kolejność z listą znanych kolumn — brakujące dopina na końcu."""
    known_list = list(LOGICAL_COLUMNS if known is None else known)
    if not isinstance(saved, list):
        return known_list
    result = []
    for name in saved:
        if isinstance(name, str) and name in known_list and name not in result:
            result.append(name)
    for name in known_list:
        if name not in result:
            result.append(name)
    return result


def display_column_index(col_id, count: int):
    """Mapuje identyfikator Treeview ``#1``…``#n`` na indeks w ``displaycolumns`` (0-based)."""
    if not col_id or not col_id.startswith("#"):
        return None
    try:
        number = int(col_id[1:])
    except ValueError:
        return None
    if number < 1 or number > count:
        return None
    return number - 1


def move_column(order, source: str, target: str) -> list:
    """Przesuwa kolumnę ``source`` przed ``target`` w liście kolejności wyświetlania."""
    order = list(order)
    if source not in order or target not in order or source == target:
        return order
    order.remove(source)
    order.insert(order.index(target), source)
    return order


def gui_settings_path(app_dir: str) -> str:
    return os.path.join(app_dir, "gui-ustawienia.json")


def _read_settings(path: str):
    """Obiekt JSON albo None, gdy pliku nie ma, odczyt padnie, JSON jest zły albo nie jest obiektem."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _write_settings(path: str, column_order, download_dir: str) -> None:
    """Zapisuje dokładnie ``column_order`` i ``download_dir`` w UTF-8."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "column_order": list(column_order),
                "download_dir": download_dir,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.write("\n")


def default_download_dir(app_dir: str) -> str:
    """``{katalog programu}/pobrane-bios``."""
    return os.path.join(app_dir, "pobrane-bios")


def _usable_download_dir(value):
    """Tekst po ``strip()`` niepusty wraca bez zmian. Inaczej None."""
    if isinstance(value, str) and value.strip():
        return value
    return None


def _column_order_for_merge(data) -> list:
    """Surowa lista z pliku. Brak listy → domyślna kolejność odczytu bez klucza."""
    if isinstance(data, dict) and isinstance(data.get("column_order"), list):
        return list(data["column_order"])
    return list(LOGICAL_COLUMNS)


def _download_dir_for_merge(data, app_dir: str) -> str:
    """Użyteczny tekst bez ``abspath``. Inaczej katalog domyślny."""
    if isinstance(data, dict):
        kept = _usable_download_dir(data.get("download_dir"))
        if kept is not None:
            return kept
    return default_download_dir(app_dir)


def load_column_order(path: str) -> list:
    """Czyta ``column_order`` z JSON; uszkodzony plik → domyślna ``LOGICAL_COLUMNS``."""
    data = _read_settings(path)
    if data is None:
        return list(LOGICAL_COLUMNS)
    return normalize_column_order(data.get("column_order"))


def load_download_dir(path: str, app_dir: str) -> str:
    """Tekst ``download_dir`` albo katalog domyślny. Pliku nie zapisuje."""
    return _download_dir_for_merge(_read_settings(path), app_dir)


def row_values(row: dict, columns=None) -> tuple:
    """Wartości wiersza Treeview w kolejności logicznych kolumn."""
    cols = LOGICAL_COLUMNS if columns is None else columns
    return tuple(row[c] for c in cols)


BIOS_AGE_FRESH = "bios_swiezy"
BIOS_AGE_MID = "bios_sredni"
BIOS_AGE_OLD = "bios_stary"
BIOS_AGE_COLORS = {
    BIOS_AGE_FRESH: "#d8f3dc",
    BIOS_AGE_MID: "#ffe8cc",
    BIOS_AGE_OLD: "#ffd6d6",
}
BIOS_AGE_FOREGROUND = "#1a1a1a"
_FRESH_MAX_DAYS = 14
_MID_MAX_DAYS = 60


def release_age_tag(release, today=None):
    """Tag wieku daty wydania (ISO) albo None, gdy daty nie da się odczytać."""
    if today is None:
        today = date.today()
    text = "" if release is None else str(release)
    parsed = hp_core.parse_released_date(text)
    if parsed is None:
        return None
    days = (today - parsed).days
    if days <= _FRESH_MAX_DAYS:
        return BIOS_AGE_FRESH
    if days <= _MID_MAX_DAYS:
        return BIOS_AGE_MID
    return BIOS_AGE_OLD


def configure_bios_age_tags(tree):
    """Jasne tło wiersza i ciemny tekst."""
    for tag, background in BIOS_AGE_COLORS.items():
        tree.tag_configure(tag, background=background, foreground=BIOS_AGE_FOREGROUND)


SELECT_ROWS_MESSAGE = "Zaznacz wiersze, które chcesz pobrać."


def selected_indices_in_order(child_ids, selected_ids) -> list:
    """Indeksy zaznaczonych wierszy w kolejności wyświetlania (nie kolejności kliknięć)."""
    selected = set(selected_ids)
    return [i for i, iid in enumerate(child_ids) if iid in selected]


def rows_for_selected_download(rows, child_ids, selected_ids) -> dict:
    """Przygotowuje podzbiór ``rows`` do pobrania; bez zaznaczenia zwraca komunikat błędu."""
    if not rows:
        return {"ok": False, "rows": [], "message": download_status_message(False, 0, 0, 0)}
    indices = selected_indices_in_order(child_ids, selected_ids)
    if not indices:
        return {"ok": False, "rows": [], "message": SELECT_ROWS_MESSAGE}
    return {"ok": True, "rows": [rows[i] for i in indices], "message": ""}


def link_from_selection(rows, selected_index) -> dict:
    """Link z pierwszego zaznaczonego wiersza (indeks w ``rows``, nie iid Treeview)."""
    if selected_index is None or selected_index < 0 or selected_index >= len(rows):
        return {
            "ok": False,
            "link": "",
            "message": "Zaznacz wiersz, którego link chcesz skopiować.",
        }
    link = rows[selected_index].get("Link") or ""
    if not link:
        return {
            "ok": False,
            "link": "",
            "message": "Zaznaczony wiersz nie ma linku.",
        }
    return {"ok": True, "link": link, "message": "Skopiowano link."}


def download_status_message(
    had_rows: bool,
    planned_count: int,
    saved_count: int,
    error_count: int,
    only_new_versions: bool = True,
    dest_dir: str = "pobrane-bios",
) -> str:
    """Tekst paska statusu po pobieraniu.

    ``only_new_versions`` zmienia komunikat przy pustym planie.
    ``dest_dir`` jest wstawiany tylko przy pełnym sukcesie (zero błędów).
    """
    if not had_rows:
        return "Najpierw sprawdź wersje BIOS."
    if planned_count == 0 and error_count == 0:
        if only_new_versions:
            return "Brak nowych wersji do pobrania."
        return "Brak plików do pobrania."
    noun = "plik" if saved_count == 1 else "plików"
    if error_count == 0:
        return f"Pobrano {saved_count} {noun} do {dest_dir}."
    return f"Pobrano {saved_count} {noun}, błędy: {error_count}."


def download_folder_status(path: str) -> str:
    return f"Folder pobierania: {path}"


def download_dir_block(path: str):
    """Komunikat, gdy ścieżka jest istniejącym plikiem. Brak katalogu nie blokuje."""
    if os.path.isfile(path):
        return f"To nie jest folder: {path}"
    return None


def download_error_status(exc_text: str, path: str) -> str:
    return f"Błąd pobierania: {exc_text} — {path}"


def askdirectory_initial(download_dir: str, app_dir: str) -> str:
    """Katalog startowy dialogu: bieżący folder, gdy jest katalogiem, inaczej katalog programu."""
    if os.path.isdir(download_dir):
        return download_dir
    return app_dir


def chosen_download_dir(dialog_result):
    """None przy anulowaniu. Inaczej ścieżka bezwzględna, bez tworzenia katalogu."""
    if not dialog_result:
        return None
    return os.path.abspath(dialog_result)


def save_column_order(path: str, order) -> None:
    """Zapisuje nową kolejność kolumn i zachowuje użyteczny ``download_dir``."""
    data = _read_settings(path)
    _write_settings(
        path,
        list(order),
        _download_dir_for_merge(data, os.path.dirname(path)),
    )


def save_download_dir(path: str, chosen: str) -> None:
    """Zapisuje ``os.path.abspath(chosen)`` i zachowuje surową listę kolumn."""
    data = _read_settings(path)
    _write_settings(path, _column_order_for_merge(data), os.path.abspath(chosen))
