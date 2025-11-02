from pathlib import Path
import json
import threading
import time

# Archivo json donde persistimos tokens para no depender del .env
# Queda en la raíz del proyecto.

from django.conf import settings
TOKEN_FILE = settings.BASE_DIR.parent / "ml_tokens.json"

_lock = threading.Lock()

def load_tokens():
    if not TOKEN_FILE.exists():
        return {"access_token": None, "refresh_token": None, "expires_at": 0}
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        data.setdefault("access_token", None)
        data.setdefault("refresh_token", None)
        data.setdefault("expires_at", 0)
        return data
    except Exception:
        return {"access_token": None, "refresh_token": None, "expires_at": 0}

#Guarda tokens y si hay un refresh nuevo, lo persiste.
def save_tokens(access_token: str, refresh_token: str | None, expires_in: int):

    with _lock:
        now = time.time()
        payload = load_tokens()
        payload["access_token"] = access_token
        if refresh_token:  # a veces ML devuelve uno nuevo
            payload["refresh_token"] = refresh_token
        # margen de 60s para refrescar antes
        payload["expires_at"] = now + int(expires_in) - 60
        TOKEN_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def get_persisted_refresh_token():
    return load_tokens().get("refresh_token")

def get_cached_access_token():
    data = load_tokens()
    if data.get("access_token") and time.time() < data.get("expires_at", 0):
        return data["access_token"]
    return None

#actualiza solo el access_token (sin tocar refresh)
def cache_access_token(access_token: str, expires_in: int):

    data = load_tokens()
    save_tokens(access_token, data.get("refresh_token"), expires_in)
