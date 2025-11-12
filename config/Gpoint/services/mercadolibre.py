import os
import time
import requests
from django.conf import settings
from . import token_store as ts
from dotenv import load_dotenv
from urllib.parse import quote

BASE_URL = "https://api.mercadolibre.com"
DEFAULT_SITE = "MLC"
ENV_PATH = settings.BASE_DIR.parent / ".env"
load_dotenv(ENV_PATH)

APP_ID = os.getenv("APP_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REFRESH_TOKEN_ENV = os.getenv("REFRESH_TOKEN")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)

MIN_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json",
}


# ===================== TOKENS =====================

def _get_refresh_token():
    rt = ts.get_persisted_refresh_token()
    if rt:
        return rt
    return REFRESH_TOKEN_ENV


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


def _get_access_token():
    cached = ts.get_cached_access_token()
    if cached:
        return cached
    return _refresh_access_token()


def _auth_headers():
    h = dict(MIN_HEADERS)
    h["Authorization"] = f"Bearer {_get_access_token()}"
    return h


# ===================== HELPERS HTTP =====================

def ml_get(path, params=None, need_auth=False, retries=1):
    url = f"{BASE_URL}{path}"
    last_err = None
    for attempt in range(retries + 1):
        try:
            headers = _auth_headers() if need_auth else MIN_HEADERS
            r = requests.get(url, headers=headers, params=params, timeout=12)
            # si token venció, refrescamos una vez
            if r.status_code in (401, 403) and need_auth and attempt < retries:
                _refresh_access_token()
                continue
            if r.status_code in (429, 503) and attempt < retries:
                time.sleep(1.2 * (attempt + 1))
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


# ===================== BÚSQUEDA RÁPIDA (API) =====================
# la usa /api/ml/search/ en tu views.py
def es_ecologico(item):
    palabras_clave = [
        "ecológico", "eco", "reciclado", "reciclable", "orgánico",
        "reutilizable", "sustentable", "natural", "bambú", "biodegradable",
        "sin plástico", "sin plastico", "vegano", "compostable", "amigable",
        "ecofriendly", "sostenible", "verde", "biológico"
    ]

    palabras_excluir = [
        "eléctrico", "plástico", "pilas", "batería", "descartable",
        "desechable", "no reciclable", "motor", "combustión"
    ]

    texto = " ".join([
        item.get("name", ""),
        item.get("title", ""),
        item.get("subtitle", "") or "",
        item.get("domain_id", "") or "",
        item.get("category_id", "") or "",
    ]).lower()
    if any(p in texto for p in palabras_clave):
        if not any(p in texto for p in palabras_excluir):
            return True

    # ✅ Revisión en atributos
    for attr in item.get("attributes", []):
        nombre = attr.get("name", "").lower()
        valor = str(attr.get("value_name", "")).lower()
        if any(p in valor or p in nombre for p in palabras_clave):
            if not any(bad in valor for bad in palabras_excluir):
                return True
    materiales = [
        "madera", "bambú", "acero inoxidable", "vidrio", "cartón", "papel", "algodón"
    ]
    for attr in item.get("attributes", []):
        valor = str(attr.get("value_name", "")).lower()
        if any(m in valor for m in materiales):
            return True

    return False


def buscar_items(query: str, site_id: str = DEFAULT_SITE, limit: int = 10, offset: int = 0):
    """
    Versión reducida:
    1) intenta en el sitio pedido, autenticado
    2) si falla o viene vacío y estamos en MLC, prueba MLA
    sin probar 9 variantes que te alargaban el tiempo. 
    """
    path = f"/sites/{site_id}/search"
    params = {"q": query, "limit": limit, "offset": offset}

    # 1) intento principal
    try:
        r = ml_get(path, params=params, need_auth=True, retries=1)
        data = r.json() or {}
        results = data.get("results", [])
        if results:

            results = [item for item in results if es_ecologico(item)]
            return results, {
                "total": len(results),
                "limit": limit,
                "offset": offset,
                "site_used": site_id,
                "fallback": False,
                "used_query": query,
            }
    except Exception:
        results = []

    # 2) fallback a MLA
    if site_id != "MLA":
        try:
            r2 = ml_get("/sites/MLA/search", params=params, need_auth=True, retries=1)
            d2 = r2.json() or {}
            res2 = d2.get("results", [])
            return res2, {
                "total": d2.get("paging", {}).get("total", len(res2)),
                "limit": limit,
                "offset": offset,
                "site_used": "MLA",
                "fallback": True,
                "used_query": query,
            }
        except Exception:
            pass

    # sin nada
    return [], {
        "total": 0,
        "limit": limit,
        "offset": offset,
        "site_used": site_id,
        "fallback": False,
        "used_query": query,
    }


# ===================== BÚSQUEDA POR CATEGORÍA (la que usa tu template) =====================
# la usa views.productos → search.html

BASE_URL = "https://api.mercadolibre.com"




# asumo que ya tienes esto en el archivo:
# def _auth_headers(): ...
# def _paging_empty(...): ...


BASE_URL = "https://api.mercadolibre.com"

def buscar_items_por_categoria(query: str, site_id: str = "MLC", limit: int = 24, offset: int = 0):
    """
    Muestra SOLO productos que efectivamente tienen un item publicado en ML.
    Usa solo los endpoints que vimos que te dan 200:
      - /sites/{site}/domain_discovery/search
      - /highlights/{site}/category/{cat}
      - /products/{id}
      - /products/{id}/items?site_id=...
    NO usa /sites/{site}/search porque a tu servidor le da 403.
    """
    headers = _auth_headers()  # ya comprobamos que esto funciona con /users/me

    # 1) descubrir categoría desde el texto del usuario
    try:
        dd = requests.get(
            f"{BASE_URL}/sites/{site_id}/domain_discovery/search",
            params={"q": query},
            headers=headers,
            timeout=10,
        )
        ddj = dd.json() if dd.status_code == 200 else []
    except Exception:
        ddj = []

    if not ddj:
        return [], _paging_empty(site_id, query, limit, offset)

    category_id = ddj[0].get("category_id")
    if not category_id:
        return [], _paging_empty(site_id, query, limit, offset)

    # 2) pedir los destacados de esa categoría
    hi = requests.get(
        f"{BASE_URL}/highlights/{site_id}/category/{category_id}",
        headers=headers,
        timeout=10,
    )
    if hi.status_code != 200:
        return [], _paging_empty(site_id, query, limit, offset)

    hij = hi.json() or {}
    content = hij.get("content") or []
    if not content:
        return [], _paging_empty(site_id, query, limit, offset)

    # para Chile
    articulo_base = "https://articulo.mercadolibre.cl"
    if site_id == "MLA":
        articulo_base = "https://articulo.mercadolibre.com.ar"

    items_out = []

    # recortamos los ids según el limit/offset
    highlighted_ids = [c.get("id") for c in content if c.get("id")]
    slice_ids = highlighted_ids[offset: offset + limit]

    for pid in slice_ids:
        # 3a) detalle del producto de catálogo
        rp = requests.get(
            f"{BASE_URL}/products/{pid}",
            headers=headers,
            timeout=10,
        )
        if rp.status_code != 200:
            # si un producto falla, seguimos al siguiente
            continue

        pj = rp.json() or {}
        title = pj.get("name") or query
        pictures = pj.get("pictures") or []
        img = None
        if pictures:
            img = pictures[0].get("secure_url") or pictures[0].get("url")

        # 3b) ver si hay items reales para este producto
        ritems = requests.get(
            f"{BASE_URL}/products/{pid}/items",
            params={"site_id": site_id},
            headers=headers,
            timeout=10,
        )
        if ritems.status_code != 200:
            # no pudimos ver los items → no lo mostramos, pasamos al siguiente
            continue

        items_json = ritems.json() or {}
        real_items = items_json.get("results") or []
        if not real_items:
            # catálogo sin publicaciones actuales → lo saltamos
            continue

        first = real_items[0]
        price = first.get("price")
        permalink = first.get("permalink")

        # A VECES NO VIENE permalink → lo armamos con item_id
        if not permalink:
            item_id = first.get("item_id")
            if item_id and item_id.startswith(site_id):
                # ej: MLC1588038756 → https://articulo.mercadolibre.cl/MLC-1588038756
                num = item_id[len(site_id):]
                permalink = f"{articulo_base}/{site_id}-{num}"
            else:
                # último fallback: mandar a listado
                permalink = f"https://listado.mercadolibre.cl/{quote(title)}"

        # normalizar
        if permalink.startswith("http://"):
            permalink = "https://" + permalink[len("http://"):]
        if not es_ecologico(pj):
            continue
        items_out.append({
            "title": title,
            "price": price,
            "secure_thumbnail": img,
            "thumbnail": img,
            "permalink": permalink,
        })

    paging = {
        "total": len(items_out),
        "limit": limit,
        "offset": offset,
        "site_used": site_id,
        "fallback": False,
        "used_query": query,
    }
    return items_out, paging


def _paging_empty(site_id, query, limit, offset):
    return {
        "total": 0,
        "limit": limit,
        "offset": offset,
        "site_used": site_id,
        "fallback": False,
        "used_query": query,
    }


def _paging_empty(site_id, query, limit, offset):
    return {
        "total": 0,
        "limit": limit,
        "offset": offset,
        "site_used": site_id,
        "fallback": False,
        "used_query": query,
    }