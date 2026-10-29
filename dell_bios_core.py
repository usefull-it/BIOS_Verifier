"""Logika weryfikacji BIOS Dell — katalog CAB, stan JSON, modele użytkownika, pobieranie.

Źródło danych: ``CatalogIndexPC.cab`` i per-model CAB z downloads.dell.com (XML OpenManage).
Wbudowane modele: ``DELL_MODELS``; rozszerzenia: ``modele-uzytkownika.json``; ukrycie: ``excluded``.
Stan ostatniego sprawdzenia: ``bios-stan.json`` obok skryptu.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Optional

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def change_label(current_version: str, previous_version: str) -> str:
    if not previous_version:
        return "pierwsza kontrola"
    if current_version == previous_version:
        return "bez zmian"
    return f"nowa wersja (poprzednio {previous_version})"


def parse_release_date(text: str):
    if not text or not str(text).strip():
        return None
    m = re.match(r"^\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})\s*$", text)
    if not m:
        return None
    month = _MONTHS.get(m.group(1).lower())
    if month is None:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(2)))
    except ValueError:
        return None


def convert_importance(text: str) -> str:
    return {
        "Urgent": "Krytyczna",
        "Recommended": "Zalecana",
        "Optional": "Opcjonalna",
    }.get(text, "nieznana")


def download_url(relative_path: str) -> str:
    trimmed = relative_path.strip()
    while trimmed.startswith("/"):
        trimmed = trimmed[1:]
    return "https://downloads.dell.com/" + trimmed


def _version_tuple(text: str):
    parts = []
    for p in text.split("."):
        if p.isdigit():
            parts.append(int(p))
        else:
            return None
    return tuple(parts) if parts else None


def compare_version_text(left: str, right: str) -> int:
    lv, rv = _version_tuple(left), _version_tuple(right)
    if lv is not None and rv is not None:
        return (lv > rv) - (lv < rv)
    if left == right:
        return 0
    return (left > right) - (left < right)


NS = "openmanage/cm/dm"  # namespace elementów XML w katalogach Dell

DELL_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# Domyślna lista sprawdzanych modeli; dopisywanie przez GUI trafia do modele-uzytkownika.json.
DELL_MODELS = [
    {"name": "Dell Latitude 5401", "system_ids": ["0918"]},
    {"name": "Dell Latitude 5420", "system_ids": ["0A20", "0A40"]},
    {"name": "Dell Latitude 5430", "system_ids": ["0B04", "0B05"]},
    {"name": "Dell Latitude 5440", "system_ids": ["0C00", "0C01", "0D0B"]},
    {"name": "Dell Latitude 5520", "system_ids": ["0A21", "0A41"]},
    {"name": "Dell Precision 3561", "system_ids": ["0A68"]},
    {"name": "Dell Precision 5560", "system_ids": ["0A62"]},
]


def resolve_cabextract(explicit_path: Optional[str] = None) -> str:
    """Ścieżka do ``cabextract`` w PATH (wymagany do rozpakowania katalogów .cab)."""
    path = explicit_path or shutil.which("cabextract")
    if not path or not os.path.isfile(path):
        raise RuntimeError(
            "Brak programu cabextract, wymaganego do rozpakowania katalogu CAB."
        )
    return path


def expand_cab_to_xml(cab_path: str, dest_dir: str, cabextract_path: str):
    os.makedirs(dest_dir, exist_ok=True)
    proc = subprocess.run(
        [cabextract_path, "-d", dest_dir, cab_path],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError("Nie udało się rozpakować katalogu Dell.")
    xml_files = list(Path(dest_dir).rglob("*.xml"))
    if not xml_files:
        raise RuntimeError("Nie udało się rozpakować katalogu Dell.")
    try:
        return ET.parse(xml_files[0]).getroot()
    except ET.ParseError:
        raise RuntimeError("Katalog Dell ma nieczytelny XML.") from None


def download_bytes(url: str, dest_path: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": DELL_USER_AGENT})
    with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as out:
        out.write(resp.read())


def fetch_index_root(temp_root: str, cabextract_path: str):
    """Pobiera główny indeks PC i zwraca korzeń XML (mapa model → ścieżka CAB platformy)."""
    cab = os.path.join(temp_root, "CatalogIndexPC.cab")
    try:
        download_bytes(download_url("catalog/CatalogIndexPC.cab"), cab)
    except Exception:
        raise RuntimeError(
            "Nie udało się pobrać katalogu Dell: CatalogIndexPC.cab"
        ) from None
    return expand_cab_to_xml(cab, os.path.join(temp_root, "index"), cabextract_path)


def lookup_model_live(query: str) -> dict:
    """Szuka modelu w żywym indeksie (GUI „Dodaj model”); temp katalog usuwany w ``finally``."""
    try:
        cabextract = resolve_cabextract()
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc), "name": "", "system_ids": []}
    temp_root = os.path.join(
        tempfile.gettempdir(), "DellBiosVerifier", uuid.uuid4().hex
    )
    os.makedirs(temp_root, exist_ok=True)
    try:
        try:
            index = fetch_index_root(temp_root, cabextract)
        except RuntimeError as exc:
            return {"ok": False, "error": str(exc), "name": "", "system_ids": []}
        return resolve_model_query(index, query)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def run_live_check(state_path: str, models=None) -> dict:
    """Pełne sprawdzenie w sieci: indeks + CAB per model, aktualizacja bios-stan.json, wiersze raportu."""
    if models is None:
        models = DELL_MODELS
    state = ensure_bios_state(state_path)
    if state["corrupt"]:
        return {
            "exit_code": 1,
            "fatal_message": (
                "Nie można odczytać bios-stan.json. Plik nie został zmieniony."
            ),
            "rows": [],
        }
    cabextract = resolve_cabextract()
    temp_root = os.path.join(
        tempfile.gettempdir(), "DellBiosVerifier", uuid.uuid4().hex
    )
    os.makedirs(temp_root, exist_ok=True)

    def load_index():
        return fetch_index_root(temp_root, cabextract)

    def load_platform(rel_path: str):
        leaf = os.path.basename(rel_path)
        cab = os.path.join(temp_root, leaf)
        try:
            download_bytes(download_url(rel_path), cab)
        except Exception:
            raise RuntimeError("błąd: nie pobrano katalogu modelu") from None
        try:
            return expand_cab_to_xml(
                cab, os.path.join(temp_root, leaf + "-xml"), cabextract
            )
        except RuntimeError as exc:
            msg = str(exc)
            if msg in (
                "Katalog Dell ma nieczytelny XML.",
                "Nie udało się rozpakować katalogu Dell.",
            ):
                raise RuntimeError("błąd: nieczytelny katalog modelu") from None
            raise

    try:
        return build_report(state_path, models, load_index, load_platform)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def _display_text(parent, child_local: str) -> str:
    child = parent.find(f"{{{NS}}}{child_local}")
    if child is None:
        return ""
    en = child.find(f"{{{NS}}}Display[@lang='en']")
    node = en if en is not None else child.find(f"{{{NS}}}Display")
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _empty_package(error: str) -> dict:
    return {
        "ok": False,
        "error": error,
        "dell_version": "",
        "release_date": None,
        "release_date_text": "",
        "importance": "",
        "url": "",
        "path": "",
        "system_id": "",
    }


def latest_bios_package(root) -> dict:
    """Najnowszy pakiet BIOS w XML platformy (data wydania, potem numer wersji Dell)."""
    candidates = []
    for sc in root.iter(f"{{{NS}}}SoftwareComponent"):
        if _display_text(sc, "Category") != "BIOS":
            continue
        if _display_text(sc, "ComponentType") != "BIOS":
            continue
        candidates.append(sc)

    if not candidates:
        return _empty_package("błąd: brak pakietu BIOS")

    parsed = []
    for sc in candidates:
        rd = parse_release_date(sc.get("releaseDate") or "")
        if rd is None:
            return _empty_package("błąd: nieczytelna data wydania")
        parsed.append((rd, sc.get("dellVersion") or "", sc.get("path") or "", sc))

    winner_date, winner_ver, winner_path, winner = parsed[0]
    for rd, ver, path, sc in parsed[1:]:
        better = False
        if rd > winner_date:
            better = True
        elif rd == winner_date:
            cmp = compare_version_text(ver, winner_ver)
            if cmp > 0:
                better = True
            elif cmp == 0 and path > winner_path:
                better = True
        if better:
            winner_date, winner_ver, winner_path, winner = rd, ver, path, sc

    return {
        "ok": True,
        "error": "",
        "dell_version": winner_ver,
        "release_date": winner_date,
        "release_date_text": winner_date.isoformat(),
        "importance": convert_importance(_display_text(winner, "Criticality")),
        "url": download_url(winner_path),
        "path": winner_path,
        "system_id": "",
    }


def system_catalog_path(index_root, system_id: str):
    """Względna ścieżka CAB platformy dla ``systemID`` z indeksu głównego."""
    parent = {c: p for p in index_root.iter() for c in p}
    for model in index_root.iter(f"{{{NS}}}Model"):
        if model.get("systemID") != system_id:
            continue
        node = model
        while node is not None:
            if node.tag == f"{{{NS}}}GroupManifest":
                info = node.find(f"{{{NS}}}ManifestInformation")
                if info is None:
                    return None
                path = (info.get("path") or "").strip()
                return path or None
            node = parent.get(node)
        return None
    return None


def format_combined_version(packages) -> str:
    versions = {p["dell_version"] for p in packages}
    if len(versions) == 1:
        return next(iter(versions))
    ordered = sorted(packages, key=lambda p: p["system_id"])
    return "; ".join(f"{p['system_id']}: {p['dell_version']}" for p in ordered)


def winning_bios_package(packages):
    best = None
    for candidate in packages:
        if best is None:
            best = candidate
            continue
        better = False
        if candidate["release_date"] > best["release_date"]:
            better = True
        elif candidate["release_date"] == best["release_date"]:
            cmp = compare_version_text(
                candidate["dell_version"], best["dell_version"]
            )
            if cmp > 0:
                better = True
            elif cmp == 0 and candidate["path"] > best["path"]:
                better = True
        if better:
            best = candidate
    return best


def _model_bios_error(error: str) -> dict:
    return {
        "ok": False,
        "error": error,
        "version": "",
        "release_date_text": "",
        "importance": "",
        "url": "",
    }


def model_bios_result(name, system_ids, index_root, load_platform_xml):
    """Wynik dla jednego modelu; wiele systemID → ``format_combined_version`` w polu wersji."""
    if not system_ids:
        return _model_bios_error("błąd: brak modelu w katalogu")

    catalog_paths = {}
    for system_id in system_ids:
        path = system_catalog_path(index_root, system_id)
        if not path:
            return _model_bios_error("błąd: brak modelu w katalogu")
        catalog_paths[system_id] = path

    packages = []
    for system_id in system_ids:
        try:
            platform_xml = load_platform_xml(catalog_paths[system_id])
        except Exception as e:
            msg = str(e)
            if msg == "błąd: nieczytelny katalog modelu":
                return _model_bios_error(msg)
            if msg == "błąd: nie pobrano katalogu modelu":
                return _model_bios_error(msg)
            return _model_bios_error("błąd: nie pobrano katalogu modelu")

        package = latest_bios_package(platform_xml)
        if not package["ok"]:
            return _model_bios_error(package["error"])
        package["system_id"] = system_id
        packages.append(package)

    winner = winning_bios_package(packages)
    return {
        "ok": True,
        "error": "",
        "version": format_combined_version(packages),
        "release_date_text": winner["release_date_text"],
        "importance": winner["importance"],
        "url": winner["url"],
    }


def read_bios_state(path: str) -> dict:
    if not os.path.isfile(path):
        return {"exists": False, "corrupt": False, "models": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"exists": True, "corrupt": True, "models": None}
    if not isinstance(data, dict) or "models" not in data:
        return {"exists": True, "corrupt": True, "models": None}
    models = data["models"]
    if models is None:
        return {"exists": True, "corrupt": False, "models": {}}
    if isinstance(models, list) or not isinstance(models, dict):
        return {"exists": True, "corrupt": True, "models": None}
    return {"exists": True, "corrupt": False, "models": models}


def save_bios_state(path: str, models: dict) -> None:
    payload = {"models": {}}
    for key, entry in models.items():
        payload["models"][key] = {
            "version": str(entry.get("version", "")),
            "releaseDate": str(entry.get("releaseDate", "")),
            "importance": str(entry.get("importance", "")),
            "url": str(entry.get("url", "")),
            "checkedAt": str(entry.get("checkedAt", "") or ""),
        }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def ensure_bios_state(path: str) -> dict:
    state = read_bios_state(path)
    if state["corrupt"]:
        return state
    if not state["exists"]:
        save_bios_state(path, {})
        return {"exists": True, "corrupt": False, "models": {}}
    return state


def build_report(state_path, models, load_index_xml, load_platform_xml, today=None) -> dict:
    """Buduje wiersze tabeli GUI i zapisuje stan po udanych odczytach (``today`` tylko w testach)."""
    if today is None:
        today = date.today()
    state = ensure_bios_state(state_path)
    if state["corrupt"]:
        return {
            "exit_code": 1,
            "fatal_message": "Nie można odczytać bios-stan.json. Plik nie został zmieniony.",
            "rows": [],
        }
    try:
        index_xml = load_index_xml()
    except Exception as exc:
        return {"exit_code": 1, "fatal_message": str(exc), "rows": []}

    rows = []
    updated = dict(state["models"])
    any_success = False
    any_error = False
    for model in models:
        prev_version = ""
        prev_checked = ""
        if model["name"] in state["models"]:
            prev_entry = state["models"][model["name"]]
            prev_version = str(prev_entry.get("version", "") or "")
            prev_checked = str(prev_entry.get("checkedAt", "") or "")
        result = model_bios_result(
            model["name"], model["system_ids"], index_xml, load_platform_xml
        )
        if result["ok"]:
            rows.append(
                {
                    "Model": model["name"],
                    "Wersja BIOS": result["version"],
                    "Data wydania": result["release_date_text"],
                    "Zmiana": change_label(result["version"], prev_version),
                    "Poprzednia weryfikacja": prev_checked,
                    "Ważność": result["importance"],
                    "Link": result["url"],
                }
            )
            updated[model["name"]] = {
                "version": result["version"],
                "releaseDate": result["release_date_text"],
                "importance": result["importance"],
                "url": result["url"],
                "checkedAt": today.isoformat(),
            }
            any_success = True
        else:
            any_error = True
            rows.append(
                {
                    "Model": model["name"],
                    "Wersja BIOS": "",
                    "Data wydania": "",
                    "Zmiana": result["error"],
                    "Poprzednia weryfikacja": prev_checked,
                    "Ważność": "",
                    "Link": "",
                }
            )
    if any_success:
        save_bios_state(state_path, updated)
    return {
        "exit_code": 1 if any_error else 0,
        "fatal_message": "",
        "rows": rows,
    }


def _dell_bios_filename(url: str):
    if not isinstance(url, str) or not url.startswith("https://downloads.dell.com/"):
        return None
    name = url.split("?", 1)[0].rstrip("/").split("/")[-1]
    if name in (".", ".."):
        return None
    if re.fullmatch(r"[A-Za-z0-9._-]+", name) is None:
        return None
    return name


def plan_bios_downloads(rows, only_new_versions=True) -> dict:
    """Plan pobrania: ``only_new_versions=True`` tylko wiersze „nowa wersja”; False = każdy wiersz z URL Dell."""
    planned = []
    rejected = []
    for row in rows:
        if only_new_versions and not str(row.get("Zmiana", "")).startswith("nowa wersja"):
            continue
        model = str(row.get("Model") or "")
        filename = _dell_bios_filename(str(row.get("Link") or ""))
        if filename is None:
            rejected.append(model)
            continue
        planned.append(
            {"model": model, "url": str(row.get("Link")), "filename": filename}
        )
    return {"planned": planned, "rejected": rejected}


def download_planned_files(planned, dest_dir, fetch) -> dict:
    os.makedirs(dest_dir, exist_ok=True)
    saved = []
    errors = []
    for item in planned:
        dest = os.path.join(dest_dir, item["filename"])
        try:
            fetch(item["url"], dest)
        except Exception:
            errors.append(item["filename"])
            continue
        saved.append(dest)
    return {"saved": saved, "errors": errors}


MODEL_FORMAT_HINT = (
    "Podaj angielską nazwę z pola Display katalogu Dell, bez obowiązkowego słowa Dell na początku. "
    "Przykład: Latitude 7450. Wielkość liter nie ma znaczenia. "
    "Aplikacja dopasuje całą nazwę i zbierze wszystkie numery systemID o tym display name."
)


def normalize_model_query(text: str) -> str:
    collapsed = " ".join(str(text).strip().split())
    if collapsed.casefold().startswith("dell "):
        collapsed = collapsed[5:].strip()
    return collapsed.casefold()


def _model_display(model_el) -> str:
    en = model_el.find(f"{{{NS}}}Display[@lang='en']")
    node = en if en is not None else model_el.find(f"{{{NS}}}Display")
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _canonical_model_name(display: str) -> str:
    collapsed = " ".join(display.strip().split())
    if collapsed.casefold().startswith("dell "):
        collapsed = collapsed[5:].strip()
    return "Dell " + collapsed


def compose_model_display(brand_display: str, model_display: str) -> str:
    """Skleja markę z katalogu (Brand) i numer modelu (Display), np. Latitude + 5410 → Latitude 5410."""
    brand = " ".join(str(brand_display).strip().split())
    model = " ".join(str(model_display).strip().split())
    if not model:
        return ""
    brand_key = brand.casefold()
    model_key = model.casefold()
    if brand and model_key != brand_key and not model_key.startswith(brand_key + " "):
        return f"{brand} {model}"
    return model


def resolve_model_query(index_root, query: str) -> dict:
    """Dopasowanie po znormalizowanej nazwie Display+Brand; zbiera wszystkie systemID tej nazwy."""
    key = normalize_model_query(query)
    if not key:
        return {
            "ok": False,
            "error": "Pusta nazwa modelu. " + MODEL_FORMAT_HINT,
            "name": "",
            "system_ids": [],
        }
    parents = {child: parent for parent in index_root.iter() for child in parent}
    brand_tag = f"{{{NS}}}Brand"
    group_tag = f"{{{NS}}}GroupManifest"
    found = []
    for model in index_root.iter(f"{{{NS}}}Model"):
        display = _model_display(model)
        brand = ""
        node = model
        while node in parents:
            node = parents[node]
            if node.tag == brand_tag:
                brand = _model_display(node)
                break
            if node.tag == group_tag:
                break
        composed = compose_model_display(brand, display)
        if not composed or normalize_model_query(composed) != key:
            continue
        sid = (model.get("systemID") or "").strip()
        if sid:
            found.append((sid, composed))
    if not found:
        shown = " ".join(str(query).strip().split())
        return {
            "ok": False,
            "error": f"Nie znaleziono modelu „{shown}”. " + MODEL_FORMAT_HINT,
            "name": "",
            "system_ids": [],
        }
    return {
        "ok": True,
        "error": "",
        "name": _canonical_model_name(found[0][1]),
        "system_ids": sorted({sid for sid, _ in found}),
    }


def user_models_path(app_dir: str) -> str:
    return os.path.join(app_dir, "modele-uzytkownika.json")


def _valid_user_model(entry) -> bool:
    if not isinstance(entry, dict):
        return False
    name = entry.get("name")
    ids = entry.get("system_ids")
    if not isinstance(name, str) or not name.strip():
        return False
    if not isinstance(ids, list) or not ids:
        return False
    return all(isinstance(i, str) and i.strip() for i in ids)


def _corrupt_user_models() -> dict:
    return {"exists": True, "corrupt": True, "models": None, "excluded": None}


def _excluded_names(value):
    if not isinstance(value, list):
        return None
    names = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return None
        names.append(item.strip())
    return names


def read_user_models(path: str) -> dict:
    if not os.path.isfile(path):
        return {"exists": False, "corrupt": False, "models": [], "excluded": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _corrupt_user_models()
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        return _corrupt_user_models()
    models = []
    for entry in data["models"]:
        if not _valid_user_model(entry):
            return _corrupt_user_models()
        models.append(
            {
                "name": entry["name"].strip(),
                "system_ids": [i.strip() for i in entry["system_ids"]],
            }
        )
    if "excluded" not in data:
        excluded = []
    else:
        excluded = _excluded_names(data["excluded"])
        if excluded is None:
            return _corrupt_user_models()
    return {"exists": True, "corrupt": False, "models": models, "excluded": excluded}


def save_user_models(path: str, models: list, excluded=None) -> None:
    if excluded is None:
        excluded = []
    payload = {
        "models": [
            {
                "name": m["name"],
                "system_ids": list(m["system_ids"]),
            }
            for m in models
        ],
        "excluded": list(excluded),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def model_already_listed(name: str, models: list) -> bool:
    return any(m["name"] == name for m in models)


def models_for_check(builtin, user_models, excluded) -> list:
    """Lista modeli do sprawdzenia: scalenie wbudowanych i użytkownika minus ``excluded``."""
    hidden = set(excluded)
    return [m for m in merge_model_lists(builtin, user_models) if m["name"] not in hidden]


def remove_listed_models(builtin, user_models, excluded, names):
    """Usunięcie z GUI: wpis użytkownika znika z listy; wbudowany trafia do ``excluded``."""
    drop = set(names)
    kept = [m for m in user_models if m["name"] not in drop]
    builtin_names = {m["name"] for m in builtin}
    updated = list(excluded)
    present = set(updated)
    for name in names:
        if name in builtin_names and name not in present:
            updated.append(name)
            present.add(name)
    return kept, updated


def merge_model_lists(builtin, extra) -> list:
    merged = [
        {"name": m["name"], "system_ids": list(m["system_ids"])} for m in builtin
    ]
    names = {m["name"] for m in merged}
    for m in extra:
        if m["name"] in names:
            continue
        names.add(m["name"])
        merged.append({"name": m["name"], "system_ids": list(m["system_ids"])})
    return merged
