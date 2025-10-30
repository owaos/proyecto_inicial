import os
from dotenv import load_dotenv
load_dotenv()
import time
import requests

APP_ID = os.getenv("APP_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")
REDIRECT_URI = os.getenv("REDIRECT_URI")

BASE_URL = "https://api.mercadolibre.com"
DEFAULT_SITE = "MLC"  # Chile
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
    "Origin": "https://www.mercadolibre.cl",
    "Referer": "https://www.mercadolibre.cl/",
    "Connection": "keep-alive",
}
#######    Access token y refresh token     ##############################
_ACCESS_TOKEN = None
_EXPIRES_AT = 0.0

def _refresh_access_token():
    """Intercambia REFRESH_TOKEN por ACCESS_TOKEN y lo cachea con expiración."""
    global _ACCESS_TOKEN, _EXPIRES_AT
    url = f"{BASE_URL}/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": APP_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        }
    r = requests.post(url, data=data, timeout=15)
    r.raise_for_status()
    tok = r.json()
    _ACCESS_TOKEN = tok["access_token"]
    _EXPIRES_AT = time.time() + int(tok.get("expires_in", 3600)) - 60  # margen
    return _ACCESS_TOKEN

def _get_access_token():
    """Devuelve un token válido, refrescando si caducó."""
    if not _ACCESS_TOKEN or time.time() >= _EXPIRES_AT:
        return _refresh_access_token()
    return _ACCESS_TOKEN

def _auth_headers():
    """Combina tus HEADERS actuales con Authorization: Bearer ..."""
    h = dict(HEADERS)
    h["Authorization"] = f"Bearer {_get_access_token()}"
    return h

###########################################################

def _fetch(query: str, site_id: str, limit: int, offset: int, retries: int = 1):
    params = {"q": query, "limit": limit, "offset": offset}
    url = f"{BASE_URL}/sites/{site_id}/search"
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=_auth_headers(), timeout=12) #CAMBIADO (un poco):
            #le agrega un token de autorizacion a cada request
            
            if r.status_code in (401, 403, 429, 503):
                if r.status_code in (401, 403):
                    try:
                        _refresh_access_token()
                        print("Token de acceso actualizado automáticamente.")
                    except Exception as e:
                        print(f"Error al refrescar el token: {e}")

                last_err = requests.HTTPError(f"{r.status_code} for {r.url}")
                time.sleep(1.2 * (attempt + 1))
                continue

            r.raise_for_status()
            data = r.json()
            results = data.get("results", [])
            paging = data.get("paging", {"total": 0, "limit": limit, "offset": offset})
            paging["site_used"] = site_id
            paging["fallback"] = False
            return results, paging, None
        except requests.RequestException as e:
            last_err = e
            time.sleep(1.0 * (attempt + 1))
    return [], {"total": 0, "limit": limit, "offset": offset, "site_used": site_id, "fallback": False}, last_err

def buscar_items(query: str, site_id: str = DEFAULT_SITE, limit: int = 24, offset: int = 0):
    
    results, paging, err = _fetch(query, site_id, limit, offset, retries=1)
    if results:
        return results, paging


    if paging.get("site_used") == "MLC":
        results2, paging2, err2 = _fetch(query, "MLA", limit, offset, retries=1)
        if results2:
            paging2["fallback"] = True
            return results2, paging2

    
    if err:
        print(f"Error MercadoLibre [{paging.get('site_used')}]: {err}")
    return [], paging

def get_me() -> dict:
    #Prueba real de OAuth: devuelve información del usuario del token
    url = f"{BASE_URL}/users/me"
    r = requests.get(url, headers=_auth_headers(), timeout=10)
    r.raise_for_status()
    return r.json()


