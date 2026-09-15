#!/usr/bin/env python3
"""
monitor.py — Revisa una lista de sitios web y avisa por WhatsApp (via CallMeBot)
solo cuando un sitio CAMBIA de estado (de arriba a caído, o de caído a recuperado).

Pensado para ejecutarse periódicamente desde GitHub Actions (o cualquier cron
externo al hosting que vigila). Guarda el último estado conocido de cada sitio
en state.json para no repetir el mismo aviso en cada ejecución.

Variables de entorno (una de las dos opciones):
    CALLMEBOT_RECIPIENTS  JSON con varios destinatarios, ej:
                          [{"phone": "34612345678", "apikey": "111111"},
                           {"phone": "584241574102", "apikey": "222222"}]
    CALLMEBOT_PHONE / CALLMEBOT_APIKEY  Forma simple para un solo número.
    Cada número debe activarse por su cuenta con CallMeBot antes de poder
    recibir mensajes (no se puede reutilizar un apikey para otro teléfono).

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

# Algunos hostings/firewalls bloquean el User-Agent por defecto de requests
# (python-requests/x.x) por parecer tráfico de bot. Con uno de navegador normal
# se reduce el riesgo de falsos positivos de "caído".
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
}


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
            resp = requests.get(
                url, timeout=REQUEST_TIMEOUT, allow_redirects=True, headers=HEADERS
            )
            if resp.status_code < 400:
                return True, f"HTTP {resp.status_code}"
            last_error = f"HTTP {resp.status_code}"
        except requests.exceptions.RequestException as exc:
            # Detalle completo (no solo el nombre de la excepción) para poder
            # distinguir un bloqueo del hosting de una caída real.
            last_error = f"{type(exc).__name__}: {str(exc)[:200]}"

        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_DELAY)

    return False, last_error


def get_recipients() -> list[dict]:
    """
    Devuelve la lista de destinatarios como [{"phone": "...", "apikey": "..."}, ...].

    Se puede configurar de dos formas (con CALLMEBOT_RECIPIENTS tiene prioridad):
    - CALLMEBOT_RECIPIENTS: JSON con la lista completa, para varios números.
      Ejemplo: [{"phone": "34612345678", "apikey": "111111"}, {"phone": "584241574102", "apikey": "222222"}]
    - CALLMEBOT_PHONE + CALLMEBOT_APIKEY: un solo número (forma simple original).
    """
    raw = os.environ.get("CALLMEBOT_RECIPIENTS")
    if raw:
        try:
            recipients = json.loads(raw)
            if isinstance(recipients, list) and recipients:
                return recipients
            print("Aviso: CALLMEBOT_RECIPIENTS no es una lista JSON válida y no vacía.")
        except json.JSONDecodeError as exc:
            print(f"Aviso: CALLMEBOT_RECIPIENTS no es JSON válido ({exc}).")

    phone = os.environ.get("CALLMEBOT_PHONE")
    apikey = os.environ.get("CALLMEBOT_APIKEY")
    if phone and apikey:
        return [{"phone": phone, "apikey": apikey}]

    return []


def send_whatsapp(message: str) -> None:
    recipients = get_recipients()

    if not recipients:
        print("Aviso: no hay destinatarios configurados (CALLMEBOT_RECIPIENTS o CALLMEBOT_PHONE/APIKEY).")
        print(f"Mensaje que se hubiera enviado: {message}")
        return

    for recipient in recipients:
        phone = recipient.get("phone")
        apikey = recipient.get("apikey")
        if not phone or not apikey:
            print(f"Aviso: destinatario incompleto, se salta: {recipient}")
            continue

        url = (
            "https://api.callmebot.com/whatsapp.php"
            f"?phone={phone}&text={urllib.parse.quote(message)}&apikey={apikey}"
        )
        try:
            resp = requests.get(url, timeout=15)
            print(f"CallMeBot ({phone}) respondió: {resp.status_code} {resp.text[:200]}")
        except requests.exceptions.RequestException as exc:
            print(f"Error enviando WhatsApp a {phone}: {exc}")


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
