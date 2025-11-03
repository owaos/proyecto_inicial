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

def _public_headers_for(site_id: str):
    if site_id == "MLC":
        origin = "https://www.mercadolibre.cl"
    elif site_id == "MLA":
        origin = "https://www.mercadolibre.com.ar"
    else:
        origin = "https://www.mercadolibre.com"

    return {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-CL, es;q=0.9, en;q=0.8",
        "Origin": origin,
        "Referer": origin + "/",
        "Connection": "keep-alive",
    }

def _auth_headers_for(site_id: str):
    h = _public_headers_for(site_id).copy()
    h["Authorization"] = f"Bearer {_get_access_token()}"
    return h

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
            if r.status_code in (429, 503) and attempt < retries:
                time.sleep(2.0 * (attempt + 1))
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
            if r.status_code in (429, 503) and attempt < retries:
                time.sleep(2.0 * (attempt + 1))
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
    """
    Estrategia robusta:
      1) AUTENTICADO en /sites/{site}/search
         - si 401/403 -> refresh y reintenta 1 vez
      2) Si 200 pero results == [] -> prueba PÚBLICO 1 vez (con headers de navegador)
      3) DOMAIN DISCOVERY -> categoría (consulta categoría AUTENTICADA)
      4) Si sigue vacío y no es MLA -> fallback a MLA AUTENTICADO
    """
    params = {"q": query, "limit": limit, "offset": offset}
    path = f"/sites/{site_id}/search"
    debug_url = _build_url(f"{BASE_URL}{path}", params)
    last_err = None

    for attempt in range(retries + 1):
        try:
            # 1) Intento AUTENTICADO primero
            try:
                r = ml_get(path, params=params, need_auth=True, retries=0)
            except requests.RequestException as e:
                r = None
                last_err = e

            if (r is not None and r.status_code in (401, 403)) and attempt < retries:
                _refresh_access_token()
                r = ml_get(path, params=params, need_auth=True, retries=0)

            if r is not None and r.status_code in (429, 503) and attempt < retries:
                time.sleep(2.0 * (attempt + 1))
                continue

            # Si no hubo respuesta autenticada (error de red), intentar PÚBLICO
            if r is None:
                r = requests.get(
                    f"{BASE_URL}{path}",
                    params=params,
                    headers=MIN_HEADERS,
                    timeout=12,
                )

            # Procesa respuesta
            r.raise_for_status()
            data = r.json() or {}
            results = data.get("results", [])
            paging = data.get("paging", {"total": 0, "limit": limit, "offset": offset})
            paging.update({"site_used": site_id, "debug_url": debug_url, "fallback": False})

            # 2) Si 200 pero vacío, probar PÚBLICO 1 vez (headers navegador)
            if not results:
                r_pub = requests.get(
                    f"{BASE_URL}{path}",
                    params=params,
                    headers=MIN_HEADERS,
                    timeout=12,
                )
                if r_pub.status_code in (429, 503) and attempt < retries:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if r_pub.status_code == 200:
                    d_pub = r_pub.json() or {}
                    res_pub = d_pub.get("results", [])
                    if res_pub:
                        return res_pub, paging, None

            # 3) Fallback por categoría (DOMAIN DISCOVERY) AUTENTICADO
            dd = requests.get(
                f"{BASE_URL}/sites/{site_id}/domain_discovery/search",
                params={"q": query},
                headers=MIN_HEADERS,
                timeout=10,
            )
            if dd.status_code == 200:
                for sug in (dd.json() or [])[:3]:
                    cat = sug.get("category_id")
                    if not cat:
                        continue
                    params_cat = {"category": cat, "q": query, "limit": limit, "offset": offset}
                    r2 = ml_get(path, params=params_cat, need_auth=True, retries=0)
                    if r2.status_code in (401, 403) and attempt < retries:
                        _refresh_access_token()
                        r2 = ml_get(path, params=params_cat, need_auth=True, retries=0)
                    if r2.status_code == 200:
                        d2 = r2.json() or {}
                        res2 = d2.get("results", [])
                        if res2:
                            pag2 = d2.get("paging", {"total": 0, "limit": limit, "offset": offset})
                            pag2.update({
                                "site_used": site_id,
                                "debug_url": _build_url(f"{BASE_URL}{path}", params_cat),
                                "fallback": True
                            })
                            return res2, pag2, None

            # 4) Fallback a MLA AUTENTICADO
            if site_id != "MLA":
                res_mla, pag_mla, _ = _fetch(query, "MLA", limit, offset, retries=0)
                if res_mla:
                    pag_mla["fallback"] = True
                    return res_mla, pag_mla, None

            # Sin resultados
            return [], paging, None

        except requests.RequestException as e:
            last_err = e
            time.sleep(1.0 * (attempt + 1))

    return [], {
        "total": 0, "limit": limit, "offset": offset,
        "site_used": site_id, "debug_url": debug_url, "fallback": False
    }, last_err

def buscar_items(query: str, site_id: str = DEFAULT_SITE, limit: int = 24, offset: int = 0): 
    err = None
    paging = {"total": 0, "limit": limit, "offset": offset, "site_used": site_id, "debug_url": None, "fallback": False}
    variants = [
        query,
        f"{query} reutilizable",
        f"{query} ecologica",
        f"{query} reciclada",
        "reutilizable",
        "botella reutilizable" if query.lower() != "botella" else "bottle",
        "tijeras recicladas" if query.lower() == "tijeras" else "eco",
        "bottle",
        "reusable",
    ]

    tried = set()

    # 1) Primero intenta en el site pedido
    for q2 in variants:
        key = (site_id, q2)
        if key in tried: 
            continue
        tried.add(key)
        results, paging, _ = _fetch(q2, site_id, limit, offset, retries=1)
        if results:
            paging["site_used"] = site_id
            paging["fallback"] = site_id != DEFAULT_SITE or (q2 != query)
            paging["used_query"] = q2
            return results, paging

    # 2) Luego intenta en MLA y MLC (ambos), con todas las variantes
    for site in ["MLA", "MLC"]:
        for q2 in variants:
            key = (site, q2)
            if key in tried: 
                continue
            tried.add(key)
            results, paging, _ = _fetch(q2, site, limit, offset, retries=1)
            if results:
                paging["site_used"] = site
                paging["fallback"] = True
                paging["used_query"] = q2
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

import requests

def _search_public(site_id: str, query: str, limit: int, offset: int):
    """
    Llama al endpoint público /sites/{site}/search SIN Authorization.
    Devuelve (results, paging). No levanta excepción: si falla, retorna ([], {}).
    """
    try:
        url = f"{BASE_URL}/sites/{site_id}/search"
        params = {"q": query, "limit": limit, "offset": offset}
        # headers “navegador”, pero sin Authorization
        h = _public_headers_for(site_id) if " _public_headers_for" in globals() else MIN_HEADERS
        r = requests.get(url, params=params, headers=h, timeout=12)
        if r.status_code != 200:
            return [], {"status": r.status_code}
        data = r.json() or {}
        return data.get("results", []), data.get("paging", {"total": 0, "limit": limit, "offset": offset})
    except Exception:
        return [], {"total": 0, "limit": limit, "offset": offset}

def _enrich_items_with_auth(items: list, site_id: str):
    """
    Usa tus TOKENS (Authorization Bearer) para enriquecer cada item con /items/{id}.
    Si /items/{id} falla, deja el item como venía.
    """
    enriched = []
    for it in items:
        iid = it.get("id")
        if not iid:
            enriched.append(it); continue
        try:
            # llamada autenticada por item
            r = ml_get(f"/items/{iid}", need_auth=True, retries=1)
            if r.status_code == 200:
                d = r.json() or {}
                # fusionamos algunos campos útiles
                it["title"] = d.get("title") or it.get("title")
                it["price"] = d.get("price") or it.get("price")
                it["secure_thumbnail"] = d.get("secure_thumbnail") or it.get("secure_thumbnail") or it.get("thumbnail")
                it["thumbnail"] = it.get("secure_thumbnail") or it.get("thumbnail")
                it["permalink"] = d.get("permalink") or it.get("permalink")
        except Exception:
            pass
        enriched.append(it)
    return enriched

def buscar_items_backend(query: str, limit: int = 24, offset: int = 0, site_id: str = DEFAULT_SITE):
    """
    1) Busca PÚBLICO en MLC (backend, sin exponer tokens)
    2) Si vacío, busca PÚBLICO en MLA (fallback)
    3) Enriquecer SIEMPRE con llamadas autenticadas /items/{id} (usa tus tokens)
    4) Devuelve (results, paging) para renderizar en la vista
    """
    results, paging = _search_public(site_id, query, limit, offset)
    used_site = site_id

    if not results and site_id != "MLA":
        results, paging = _search_public("MLA", query, limit, offset)
        used_site = "MLA"

    # enriquecimiento con token (cumplimos “usar tokens” sin exponerlos)
    if results:
        results = _enrich_items_with_auth(results, used_site)

    paging = paging or {"total": 0, "limit": limit, "offset": offset}
    paging.update({"site_used": used_site, "fallback": used_site != site_id, "used_query": query})
    return results, paging

def buscar_items_por_categoria(query: str, site_id: str = DEFAULT_SITE, limit: int = 24, offset: int = 0):
    """
    Busca productos SIN usar /sites/{site}/search (que devuelve 403 en tu backend),
    usando solo endpoints que ya confirmamos 200 OK con token:
      1) domain_discovery -> category_id
      2) highlights/{site}/category/{cat} -> lista de product_id
      3) products/{product_id} -> name, pictures, permalink
      4) products/{product_id}/items?site_id=... -> listings con price
    Devuelve una lista de objetos con: title, price, image_url, permalink.
    """
    import requests

    def _safe_json(r):
        try:
            return r.json()
        except Exception:
            return {}

    # 1) Categoría para la query
    dd = requests.get(
        f"{BASE_URL}/sites/{site_id}/domain_discovery/search",
        params={"q": query}, headers=_auth_headers(), timeout=12
    )
    ddj = _safe_json(dd)
    if not isinstance(ddj, list) or not ddj:
        return [], {"total": 0, "limit": limit, "offset": offset, "site_used": site_id, "fallback": False, "used_query": query}

    category_id = (ddj[0] or {}).get("category_id")
    if not category_id:
        return [], {"total": 0, "limit": limit, "offset": offset, "site_used": site_id, "fallback": False, "used_query": query}

    # 2) Highlights (product_id) de esa categoría
    hi = requests.get(
        f"{BASE_URL}/highlights/{site_id}/category/{category_id}",
        headers=_auth_headers(), timeout=12
    )
    hij = _safe_json(hi)
    content = hij.get("content") if isinstance(hij, dict) else None
    if not isinstance(content, list) or not content:
        return [], {"total": 0, "limit": limit, "offset": offset, "site_used": site_id, "fallback": False, "used_query": query}

    product_ids = [c.get("id") for c in content if isinstance(c, dict) and c.get("id")]
    if not product_ids:
        return [], {"total": 0, "limit": limit, "offset": offset, "site_used": site_id, "fallback": False, "used_query": query}

    # 3) Para cada product_id, obtener name/pictures/permalink
    items_out = []
    for pid in product_ids[:limit]:
        # product details
        rp = requests.get(f"{BASE_URL}/products/{pid}", headers=_auth_headers(), timeout=12)
        pj = _safe_json(rp) if rp.status_code == 200 else {}
        title = pj.get("name") or pj.get("id") or ""
        pictures = pj.get("pictures") or []

        # Imagen principal: de productos (secure_url/url)
        img = None
        if isinstance(pictures, list) and pictures:
            img = pictures[0].get("secure_url") or pictures[0].get("url")

        # 4) listings para precio (primer listing) y posible fallback de thumbnail
        rlist = requests.get(
            f"{BASE_URL}/products/{pid}/items",
            params={"site_id": site_id}, headers=_auth_headers(), timeout=12
        )
        lj = _safe_json(rlist) if rlist.status_code == 200 else {}
        results = lj.get("results") or []
        price = None
        listing_id = None
        if isinstance(results, list) and results:
            price = results[0].get("price")
            listing_id = results[0].get("item_id")

        base_site = "https://www.mercadolibre.cl" if site_id == "MLC" else "https://www.mercadolibre.com.ar"

        if listing_id:
            # Formato correcto para avisos: https://www.mercadolibre.cl/MLC-123456789
            if "-" not in listing_id:
                site_prefix = listing_id[:3]
                num_part = listing_id[3:]
                permalink = f"{base_site}/{site_prefix}-{num_part}"
            else:
                permalink = f"{base_site}/{listing_id}"
        else:
            # Fallbacks cuando no tenemos listing_id
            permalink = pj.get("permalink") or ""
            if not permalink:
                permalink = f"{base_site}/p/{pid}"
            if not permalink and title:
                from urllib.parse import quote
                permalink = f"{base_site}/search?as_word={quote(title)}"

        # Normalizar http->https
        if isinstance(permalink, str) and permalink.startswith("http://"):
            permalink = "https://" + permalink[len("http://"):]

        # Fallback de imagen: si no hay picture del producto, usamos el thumbnail del listing
        # (puede fallar /items/{id} en algunos casos; si da 403, simplemente no pisamos la imagen)
        if not img and listing_id:
            ri = requests.get(f"{BASE_URL}/items/{listing_id}", headers=_auth_headers(), timeout=12)
            if ri.status_code == 200:
                ii = _safe_json(ri)
                img = ii.get("secure_thumbnail") or ii.get("thumbnail")

        # Normalizar a https si corresponde
        if isinstance(img, str) and img.startswith("http://"):
            img = "https://" + img[len("http://"):]

        items_out.append({
            "title": title,
            "price": price,
            "secure_thumbnail": img,
            "thumbnail": img,
            "permalink": permalink,
        })


    paging = {"total": len(items_out), "limit": limit, "offset": offset, "site_used": site_id, "fallback": False, "used_query": query}
    return items_out, paging
