#!/usr/bin/env python3
"""
monitor.py — Revisa una lista de sitios web y avisa por WhatsApp (via CallMeBot)
solo cuando un sitio CAMBIA de estado (de arriba a caído, o de caído a recuperado).

Pensado para ejecutarse periódicamente desde GitHub Actions (o cualquier cron
externo al hosting que vigila). Guarda el último estado conocido de cada sitio
en state.json para no repetir el mismo aviso en cada ejecución.

Variables de entorno requeridas:
    CALLMEBOT_PHONE   Tu número de WhatsApp con código de país, sin '+' (ej: 34612345678)
    CALLMEBOT_APIKEY  La apikey que te da CallMeBot al activarte

Archivos:
    sites.json  -> lista de sitios a vigilar (editable, no es secreto)
    state.json  -> último estado conocido de cada sitio (lo mantiene el propio script)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
SITES_FILE = BASE_DIR / "sites.json"
STATE_FILE = BASE_DIR / "state.json"

REQUEST_TIMEOUT = 10       # segundos por intento
MAX_ATTEMPTS = 3           # intentos antes de declarar un sitio "caído"
RETRY_DELAY = 5            # segundos de espera entre intentos


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"Aviso: {path.name} no es JSON válido, se usa el valor por defecto.")
        return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def check_site(url: str) -> tuple[bool, str]:
    """Devuelve (esta_arriba, detalle). Reintenta antes de declarar caído."""
    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            if resp.status_code < 400:
                return True, f"HTTP {resp.status_code}"
            last_error = f"HTTP {resp.status_code}"
        except requests.exceptions.RequestException as exc:
            last_error = type(exc).__name__

        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_DELAY)

    return False, last_error


def send_whatsapp(message: str) -> None:
    phone = os.environ.get("CALLMEBOT_PHONE")
    apikey = os.environ.get("CALLMEBOT_APIKEY")

    if not phone or not apikey:
        print("Aviso: faltan CALLMEBOT_PHONE / CALLMEBOT_APIKEY, no se envía WhatsApp.")
        print(f"Mensaje que se hubiera enviado: {message}")
        return

    url = (
        "https://api.callmebot.com/whatsapp.php"
        f"?phone={phone}&text={urllib.parse.quote(message)}&apikey={apikey}"
    )
    try:
        resp = requests.get(url, timeout=15)
        print(f"CallMeBot respondió: {resp.status_code} {resp.text[:200]}")
    except requests.exceptions.RequestException as exc:
        print(f"Error enviando WhatsApp: {exc}")


def now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def main() -> int:
    sites = load_json(SITES_FILE, [])
    if not sites:
        print("sites.json está vacío o no existe. Nada que revisar.")
        return 0

    state = load_json(STATE_FILE, {})
    state_changed = False

    for site in sites:
        name = site["name"]
        url = site["url"]

        is_up, detail = check_site(url)
        current_status = "up" if is_up else "down"

        previous = state.get(name)
        previous_status = previous["status"] if previous else "up"  # primer chequeo: se asume "up"

        print(f"[{name}] {url} -> {current_status} ({detail})")

        if current_status != previous_status:
            state_changed = True
            timestamp = now_utc_str()

            if current_status == "down":
                msg = f"🔴 {name} está CAÍDO\n{url}\nDetalle: {detail}\nHora: {timestamp}"
            else:
                since = previous.get("since", "desconocido") if previous else "desconocido"
                msg = f"🟢 {name} se RECUPERÓ\n{url}\nEstuvo caído desde: {since}\nHora: {timestamp}"

            send_whatsapp(msg)

            state[name] = {"status": current_status, "since": timestamp}
        elif previous is None:
            # Primer chequeo y el sitio ya estaba arriba: solo se registra, sin avisar.
            state_changed = True
            state[name] = {"status": current_status, "since": now_utc_str()}

    if state_changed:
        save_json(STATE_FILE, state)

    return 0


if __name__ == "__main__":
    sys.exit(main())
