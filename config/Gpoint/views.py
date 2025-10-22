from django.shortcuts import render
from .services.mercadolibre import buscar_items

def home(request):
    # Si el usuario no busca nada, usamos "mouse" como valor por defecto
    q = request.GET.get("q", "").strip() or "mouse"

    try:
        results, paging = buscar_items(q, limit=24, offset=int(request.GET.get("offset", 0) or 0))
        error = None
    except Exception as e:
        results, paging, error = [], {"total": 0, "limit": 24, "offset": 0}, str(e)

    return render(
        request,
        "home.html",
        {
            "q": q,
            "results": results,
            "paging": paging,
            "error": error,
        },
    )
