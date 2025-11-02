import os
import time
import requests
from pathlib import Path
from django.conf import settings
from . import token_store as ts
from dotenv import load_dotenv



# _____Persistencia de tokens


ENV_PATH = settings.BASE_DIR.parent / ".env"
load_dotenv(ENV_PATH)

APP_ID = os.getenv("APP_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REFRESH_TOKEN_ENV = os.getenv("REFRESH_TOKEN")
BASE_URL = "https://api.mercadolibre.com"
DEFAULT_SITE = "MLC"  # Esta que es la de Chile

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)

# Cabeceras para los endpoints públicos
MIN_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json",
}

#esto es para que al refrescar el token,  para que de primera se use el del .env, luego
#estará usando el de ml_tokens.json, que es el refresh token persistido
def _get_refresh_token():
  
    rt = ts.get_persisted_refresh_token()
    if rt:
        return rt
    return REFRESH_TOKEN_ENV

#Con el refresh token se obtendrá el access_token y luego se va a persistir, por lo que automaticamente
#actualizará el refresh token si es que ML devuelve uno nuevo. Esto en sí ya nos quitará el error 403.
def _refresh_access_token():
    url = f"{BASE_URL}/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": APP_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": _get_refresh_token(),
    }
    r = requests.post(url, data=data, timeout=15)
    r.raise_for_status()
    tok = r.json()

    access_token = tok["access_token"]
    expires_in = int(tok.get("expires_in", 3600))
    refresh_token_new = tok.get("refresh_token")  

    ts.save_tokens(access_token, refresh_token_new, expires_in)
    return access_token

#esto entregará el access_token válido, y además si expiró el token, lo refrescará.
def _get_access_token():
    cached = ts.get_cached_access_token()
    if cached:
        return cached
    return _refresh_access_token()

#Estp es para headers con bearer válido, que si caduca se refresca automáticamente.
def _auth_headers():
    h = dict(MIN_HEADERS)
    h["Authorization"] = f"Bearer {_get_access_token()}"
    return h

#devuelve la url real (debug)
from requests import Request, Session
def _build_url(url, params):
    s = Session()
    req = Request("GET", url, params=params)
    prepped = s.prepare_request(req)
    return prepped.url

#son get/post para reintentar si sale error 401 o 403.
def ml_get(path, params=None, need_auth=False, retries=1):

    url = f"{BASE_URL}{path}"
    last_err = None
    for attempt in range(retries + 1):
        try:
            headers = _auth_headers() if need_auth else MIN_HEADERS
            r = requests.get(url, headers=headers, params=params, timeout=15)
            if r.status_code in (401, 403) and need_auth and attempt < retries:
                _refresh_access_token()
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last_err = e
            time.sleep(1.0 * (attempt + 1))
    if last_err:
        raise last_err

def ml_post(path, data=None, json=None, need_auth=True, retries=1):
    url = f"{BASE_URL}{path}"
    last_err = None
    for attempt in range(retries + 1):
        try:
            headers = _auth_headers() if need_auth else MIN_HEADERS
            r = requests.post(url, headers=headers, data=data, json=json, timeout=15)
            if r.status_code in (401, 403) and need_auth and attempt < retries:
                _refresh_access_token()
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last_err = e
            time.sleep(1.0 * (attempt + 1))
    if last_err:
        raise last_err
    
def get_me():

    r = ml_get("/users/me", need_auth=True, retries=1)
    return r.json()


###########################################################

#ACTUALIZACOIN DEL _FETCH: ahora mantiene la búsqueda pública con  fallback por categoría, y da
#robustez a los errores 401/403/429/503 reintentando con headers mínimos y luego con MLC. Si no hay
#resultados, intentará con domain_discovery.
def _fetch(query: str, site_id: str, limit: int, offset: int, retries: int = 1):
    params = {"q": query, "limit": limit, "offset": offset}
    url = f"/sites/{site_id}/search"
    last_err = None
    debug_url = _build_url(f"{BASE_URL}{url}", params)

    for attempt in range(retries + 1):
        try:
            # 1) sin headers explícitos
            r = requests.get(f"{BASE_URL}{url}", params=params, timeout=12)
            if r.status_code in (401, 403, 429, 503):
                # 2) con headers mínimos
                r = requests.get(f"{BASE_URL}{url}", params=params, headers=MIN_HEADERS, timeout=12)
            if r.status_code in (401, 403, 429, 503):
                last_err = requests.HTTPError(f"{r.status_code} for {r.url}")
                time.sleep(1.2 * (attempt + 1))
                continue

            r.raise_for_status()
            data = r.json() or {}
            results = data.get("results", [])
            paging = data.get("paging", {"total": 0, "limit": limit, "offset": offset})
            paging["site_used"] = site_id
            paging["fallback"] = False
            paging["debug_url"] = debug_url

            if results:
                return results, paging, None

            # Plan B: domain discovery -> category_id
            dd = requests.get(
                f"{BASE_URL}/sites/{site_id}/domain_discovery/search",
                params={"q": query},
                headers=MIN_HEADERS,
                timeout=12
            )
            if dd.status_code == 200:
                suggestions = dd.json() or []
                for sug in suggestions[:3]:
                    cat = sug.get("category_id")
                    if not cat:
                        continue
                    params_cat = {"category": cat, "q": query, "limit": limit, "offset": offset}
                    debug_url_cat = _build_url(f"{BASE_URL}{url}", params_cat)
                    r2 = requests.get(f"{BASE_URL}{url}", params=params_cat, headers=MIN_HEADERS, timeout=12)
                    if r2.status_code == 200:
                        d2 = r2.json() or {}
                        res2 = d2.get("results", [])
                        if res2:
                            paging["debug_url_category"] = debug_url_cat
                            return res2, paging, None

            return [], paging, None

        except requests.RequestException as e:
            last_err = e
            time.sleep(1.0 * (attempt + 1))

    return [], {"total": 0, "limit": limit, "offset": offset, "site_used": site_id, "fallback": False, "debug_url": debug_url}, last_err


#ACTUALIZACION de buscar_items: ahora ml_search_api funcionará normal. 
def buscar_items(query: str, site_id: str = DEFAULT_SITE, limit: int = 24, offset: int = 0):
    results, paging, err = _fetch(query, site_id, limit, offset, retries=1)
    if results:
        return results, paging

    # Fallback a MLA si no hay resultados
    if site_id != "MLA":
        results2, paging2, err2 = _fetch(query, "MLA", limit, offset, retries=1)
        if results2:
            paging2["fallback"] = True
            return results2, paging2
    if err:
        print(f"Error MercadoLibre [{paging.get('site_used')}]: {err}")

    return [], paging


