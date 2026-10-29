"""Rdzeń HP BIOS: SoftPaq ImagePal/HPIA (bez logiki Della)."""

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

PRIMARY_HOST = "https://ftp.hp.com/pub/caps-softpaq/cmit/imagepal"
FALLBACK_HOST = "https://hpia.hpcloud.hp.com"
KNOWN_OSVERS = ("24h2", "23h2", "22h2", "21h2", "20h2", "2009")

MODEL_FORMAT_HINT = (
    "Podaj SystemID (hex) albo angielską nazwę produktu z platformList (ProductName)."
)

HP_MODELS = [
    {"name": "EliteBook 640 G9", "system_ids": ["897b"]},
    {"name": "EliteBook 640 G11", "system_ids": ["8c86"]},
    {"name": "EliteBook 830 G9", "system_ids": ["896d"]},
    {"name": "EliteBook 650 G9", "system_ids": ["897c"]},
    {"name": "EliteBook 650 G10", "system_ids": ["8b8c"]},
]


def platform_list_url(host: str) -> str:
    return host.rstrip("/") + "/ref/platformList.cab"


def softpaq_cab_url(host: str, system_id: str, osver: str) -> str:
    sid = system_id.lower()
    return f"{host.rstrip('/')}/ref/{sid}/{sid}_64_10.0.{osver}.cab"


def osver_candidates(latest_supported: str) -> list:
    latest = (latest_supported or "").strip()
    known = list(KNOWN_OSVERS)
    if latest and latest not in known:
        return [latest] + known
    if latest in known:
        return known[known.index(latest) :]
    return known


def is_bios_category(text: str) -> bool:
    return re.match(r"(?i)^\s*BIOS", text or "") is not None


def parse_released_date(text: str):
    if not text or not str(text).strip():
        return None
    m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})", str(text))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _version_tuple(text: str):
    parts = []
    for p in str(text).split("."):
        if p.isdigit():
            parts.append(int(p))
        else:
            return None
    return tuple(parts) if parts else None


def compare_version_aa_bb_cc(left: str, right: str) -> int:
    lv, rv = _version_tuple(left), _version_tuple(right)
    if lv is not None and rv is not None:
        n = max(len(lv), len(rv))
        lv = lv + (0,) * (n - len(lv))
        rv = rv + (0,) * (n - len(rv))
        return (lv > rv) - (lv < rv)
    if left == right:
        return 0
    return (left > right) - (left < right)


def convert_release_type(text: str) -> str:
    return {
        "Critical": "Krytyczna",
        "Recommended": "Zalecana",
        "Routine": "Rutynowa",
    }.get(text, "nieznana")


def softpaq_https_url(url_field: str) -> str:
    trimmed = (url_field or "").strip()
    if trimmed.startswith("https://"):
        return trimmed
    if trimmed.startswith("http://"):
        return "https://" + trimmed[len("http://") :]
    while trimmed.startswith("/"):
        trimmed = trimmed[1:]
    return "https://" + trimmed


def _child_text(parent, tag: str) -> str:
    node = parent.find(tag)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def latest_bios_softpaq(root) -> dict:
    candidates = []
    for tag in ("SoftPaq", "UpdateInfo"):
        for sp in root.iter(tag):
            if not is_bios_category(_child_text(sp, "Category")):
                continue
            candidates.append(sp)
    if not candidates:
        return {
            "ok": False,
            "error": "błąd: brak pakietu BIOS",
            "version": "",
            "release_date": None,
            "release_date_text": "",
            "importance": "",
            "url": "",
        }
    parsed = []
    for sp in candidates:
        rd = parse_released_date(_child_text(sp, "DateReleased"))
        if rd is None:
            return {
                "ok": False,
                "error": "błąd: nieczytelna data wydania",
                "version": "",
                "release_date": None,
                "release_date_text": "",
                "importance": "",
                "url": "",
            }
        parsed.append(
            (
                rd,
                _child_text(sp, "Version"),
                softpaq_https_url(_child_text(sp, "Url")),
                sp,
            )
        )
    winner_date, winner_ver, winner_url, winner = parsed[0]
    for rd, ver, url, sp in parsed[1:]:
        better = False
        if rd > winner_date:
            better = True
        elif rd == winner_date:
            if compare_version_aa_bb_cc(ver, winner_ver) > 0:
                better = True
        if better:
            winner_date, winner_ver, winner_url, winner = rd, ver, url, sp
    return {
        "ok": True,
        "error": "",
        "version": winner_ver,
        "release_date": winner_date,
        "release_date_text": winner_date.isoformat(),
        "importance": convert_release_type(_child_text(winner, "ReleaseType")),
        "url": winner_url,
    }


def change_label(current_version: str, previous_version: str) -> str:
    if not previous_version:
        return "pierwsza kontrola"
    if current_version == previous_version:
        return "bez zmian"
    return f"nowa wersja (poprzednio {previous_version})"


def hp_state_path(app_dir: str) -> str:
    return os.path.join(app_dir, "bios-stan-hp.json")


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


def user_models_path(app_dir: str) -> str:
    return os.path.join(app_dir, "modele-uzytkownika-hp.json")


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
    hidden = set(excluded)
    return [m for m in merge_model_lists(builtin, user_models) if m["name"] not in hidden]


def remove_listed_models(builtin, user_models, excluded, names):
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


def _platform_system_id(platform_el) -> str:
    for tag in ("SystemID", "SystemId"):
        text = _child_text(platform_el, tag)
        if text:
            return text.lower()
    return ""


def _platform_product_name(platform_el) -> str:
    return _child_text(platform_el, "ProductName")


def _platform_latest_os(platform_el) -> str:
    direct = _child_text(platform_el, "LatestSupportedOs")
    if direct:
        return direct
    for node in platform_el.iter("LatestSupportedOs"):
        if node.text and node.text.strip():
            return node.text.strip()
    return ""


def platform_index(root) -> dict:
    out = {}
    for platform in root.iter("Platform"):
        sid = _platform_system_id(platform)
        if not sid:
            continue
        out[sid] = {
            "name": _canonical_platform_name(_platform_product_name(platform)),
            "product_name": _platform_product_name(platform),
            "latest_supported_os": _platform_latest_os(platform),
            "system_ids": [sid],
        }
    return out


def _canonical_platform_name(product_name: str) -> str:
    text = " ".join(product_name.split())
    if text.casefold().startswith("hp "):
        text = text[3:].strip()
    return text


def resolve_platform_query(root, query: str) -> dict:
    collapsed = " ".join(str(query).strip().split())
    if not collapsed:
        return {
            "ok": False,
            "error": "Pusta nazwa lub SystemID.",
            "name": "",
            "system_ids": [],
            "latest_supported_os": "",
        }
    index = platform_index(root)
    key = collapsed.casefold()
    if re.fullmatch(r"[0-9a-fA-F]+", collapsed):
        sid = collapsed.lower()
        if sid in index:
            entry = index[sid]
            return {
                "ok": True,
                "error": "",
                "name": entry["name"],
                "system_ids": list(entry["system_ids"]),
                "latest_supported_os": entry["latest_supported_os"],
            }
        return {
            "ok": False,
            "error": "Nie znaleziono SystemID w platformList.",
            "name": "",
            "system_ids": [],
            "latest_supported_os": "",
        }
    for entry in index.values():
        if entry["name"].casefold() == key or entry["product_name"].casefold() == key:
            return {
                "ok": True,
                "error": "",
                "name": entry["name"],
                "system_ids": list(entry["system_ids"]),
                "latest_supported_os": entry["latest_supported_os"],
            }
        if key in entry["name"].casefold() or key in entry["product_name"].casefold():
            return {
                "ok": True,
                "error": "",
                "name": entry["name"],
                "system_ids": list(entry["system_ids"]),
                "latest_supported_os": entry["latest_supported_os"],
            }
    return {
        "ok": False,
        "error": "Nie znaleziono modelu w platformList.",
        "name": "",
        "system_ids": [],
        "latest_supported_os": "",
    }


def build_report(state_path, models, load_platform_list, load_softpaq_xml, today=None) -> dict:
    if today is None:
        today = date.today()
    state = ensure_bios_state(state_path)
    if state["corrupt"]:
        return {
            "exit_code": 1,
            "fatal_message": "Nie można odczytać bios-stan-hp.json. Plik nie został zmieniony.",
            "rows": [],
        }
    try:
        platforms = load_platform_list()
    except Exception as exc:
        return {"exit_code": 1, "fatal_message": str(exc), "rows": []}
    index = platform_index(platforms)
    rows = []
    updated = dict(state["models"])
    any_success = False
    any_error = False
    for model in models:
        name = model["name"]
        sid = model["system_ids"][0]
        prev_version = ""
        prev_checked = ""
        if name in state["models"]:
            prev_entry = state["models"][name]
            prev_version = str(prev_entry.get("version", "") or "")
            prev_checked = str(prev_entry.get("checkedAt", "") or "")
        latest_os = index.get(sid.lower(), {}).get("latest_supported_os", "")
        try:
            softpaq_root = load_softpaq_xml(sid, latest_os)
            result = latest_bios_softpaq(softpaq_root)
        except Exception as exc:
            result = {
                "ok": False,
                "error": str(exc),
                "version": "",
                "release_date_text": "",
                "importance": "",
                "url": "",
            }
        if result["ok"]:
            rows.append(
                {
                    "Model": name,
                    "Wersja BIOS": result["version"],
                    "Data wydania": result["release_date_text"],
                    "Zmiana": change_label(result["version"], prev_version),
                    "Poprzednia weryfikacja": prev_checked,
                    "Ważność": result["importance"],
                    "Link": result["url"],
                }
            )
            updated[name] = {
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
                    "Model": name,
                    "Wersja BIOS": "",
                    "Data wydania": "",
                    "Zmiana": result.get("error") or "błąd",
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


def _hp_bios_filename(url: str):
    if not isinstance(url, str) or not url.startswith("https://"):
        return None
    name = url.split("?", 1)[0].rstrip("/").split("/")[-1]
    if name in (".", ".."):
        return None
    if re.fullmatch(r"[A-Za-z0-9._-]+", name) is None:
        return None
    return name


def plan_bios_downloads(rows, only_new_versions=True) -> dict:
    planned = []
    rejected = []
    for row in rows:
        if only_new_versions and not str(row.get("Zmiana", "")).startswith(
            "nowa wersja"
        ):
            continue
        model = str(row.get("Model") or "")
        filename = _hp_bios_filename(str(row.get("Link") or ""))
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


def resolve_cabextract(explicit_path=None) -> str:
    path = explicit_path or shutil.which("cabextract")
    if not path or not os.path.isfile(path):
        raise RuntimeError(
            "Brak programu cabextract, wymaganego do rozpakowania katalogu SoftPaq HP."
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
        raise RuntimeError("Nie udało się rozpakować katalogu SoftPaq HP.")
    xml_files = list(Path(dest_dir).rglob("*.xml"))
    if not xml_files:
        raise RuntimeError("Nie udało się rozpakować katalogu SoftPaq HP.")
    try:
        return ET.parse(xml_files[0]).getroot()
    except ET.ParseError:
        raise RuntimeError("Katalog SoftPaq HP ma nieczytelny XML.") from None


def fetch_xml_cab_with_fallback(urls, http_get, expand_cab_bytes):
    last_error = None
    for url in urls:
        try:
            data = http_get(url)
            return expand_cab_bytes(data, url)
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"Nie udało się pobrać katalogu HP: {last_error}")


def fetch_softpaq_xml_for_sid(
    system_id, latest_supported_os, http_get, expand_cab_bytes
):
    errors = []
    for osver in osver_candidates(latest_supported_os):
        urls = [
            softpaq_cab_url(PRIMARY_HOST, system_id, osver),
            softpaq_cab_url(FALLBACK_HOST, system_id, osver),
        ]
        try:
            return fetch_xml_cab_with_fallback(urls, http_get, expand_cab_bytes)
        except Exception as exc:
            errors.append(str(exc))
            continue
    raise RuntimeError(
        "Nie udało się pobrać SoftPaq CAB dla "
        f"{system_id}: " + "; ".join(errors)
    )


def _default_http_get(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; HP-BIOS-Verifier/1.0)"
            )
        },
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def run_live_check(state_path: str, models=None) -> dict:
    state = ensure_bios_state(state_path)
    if state["corrupt"]:
        return {
            "exit_code": 1,
            "fatal_message": (
                "Nie można odczytać bios-stan-hp.json. Plik nie został zmieniony."
            ),
            "rows": [],
        }
    try:
        cabextract = resolve_cabextract()
    except RuntimeError as exc:
        return {"exit_code": 1, "fatal_message": str(exc), "rows": []}
    if models is None:
        app_dir = os.path.dirname(state_path)
        loaded = read_user_models(user_models_path(app_dir))
        if loaded["corrupt"]:
            return {
                "exit_code": 1,
                "fatal_message": (
                    "Nie można odczytać modele-uzytkownika-hp.json. "
                    "Plik nie został zmieniony."
                ),
                "rows": [],
            }
        models = models_for_check(HP_MODELS, loaded["models"], loaded["excluded"])
    temp_root = os.path.join(
        tempfile.gettempdir(), "HpBiosVerifier", uuid.uuid4().hex
    )
    os.makedirs(temp_root, exist_ok=True)

    def expand_cab_bytes(data, label):
        cab_path = os.path.join(temp_root, uuid.uuid4().hex + ".cab")
        with open(cab_path, "wb") as handle:
            handle.write(data)
        return expand_cab_to_xml(
            cab_path, os.path.join(temp_root, uuid.uuid4().hex), cabextract
        )

    def load_platform_list():
        return fetch_xml_cab_with_fallback(
            [
                platform_list_url(PRIMARY_HOST),
                platform_list_url(FALLBACK_HOST),
            ],
            http_get=_default_http_get,
            expand_cab_bytes=expand_cab_bytes,
        )

    def load_softpaq_xml(system_id, latest_supported_os):
        return fetch_softpaq_xml_for_sid(
            system_id,
            latest_supported_os,
            http_get=_default_http_get,
            expand_cab_bytes=expand_cab_bytes,
        )

    try:
        return build_report(state_path, models, load_platform_list, load_softpaq_xml)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def lookup_model_live(query: str) -> dict:
    empty = {
        "ok": False,
        "error": "",
        "name": "",
        "system_ids": [],
        "latest_supported_os": "",
    }
    try:
        cabextract = resolve_cabextract()
    except RuntimeError as exc:
        empty["error"] = str(exc)
        return empty
    temp_root = os.path.join(
        tempfile.gettempdir(), "HpBiosVerifier", uuid.uuid4().hex
    )
    os.makedirs(temp_root, exist_ok=True)

    def expand_cab_bytes(data, label):
        cab_path = os.path.join(temp_root, uuid.uuid4().hex + ".cab")
        with open(cab_path, "wb") as handle:
            handle.write(data)
        return expand_cab_to_xml(
            cab_path, os.path.join(temp_root, uuid.uuid4().hex), cabextract
        )

    try:
        root = fetch_xml_cab_with_fallback(
            [
                platform_list_url(PRIMARY_HOST),
                platform_list_url(FALLBACK_HOST),
            ],
            http_get=_default_http_get,
            expand_cab_bytes=expand_cab_bytes,
        )
        return resolve_platform_query(root, query)
    except Exception as exc:
        empty["error"] = str(exc)
        return empty
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
