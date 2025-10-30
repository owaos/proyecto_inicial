import time
import requests

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

def _fetch(query: str, site_id: str, limit: int, offset: int, retries: int = 1):
    params = {"q": query, "limit": limit, "offset": offset}
    url = f"{BASE_URL}/sites/{site_id}/search"
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=12)
            
            if r.status_code in (401, 403, 429, 503):
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
