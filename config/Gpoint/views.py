from django.shortcuts import render,redirect
#from .services.mercadolibre import buscar_items

from django.http import JsonResponse, HttpResponseServerError
import Gpoint.services.mercadolibre as ml_service



#
# def home(request):
#     # Si el usuario no busca nada, usamos "mouse" como valor por defecto
#     q = request.GET.get("q", "").strip() or "mouse"

#     try:
#         results, paging = buscar_items(q, limit=24, offset=int(request.GET.get("offset", 0) or 0))
#         error = None
#     except Exception as e:
#         results, paging, error = [], {"total": 0, "limit": 24, "offset": 0}, str(e)

#     return render(
#         request,
#         "home.html",
#         {     
#             "q": q,
#             "results": results,
#             "paging": paging,
#             "error": error,
#         },
#     )

def home(request):
    return render(request, 'home.html')
def search(request):
    return render(request, 'search.html')
# views.py
def productos(request):
    q = request.GET.get('busqueda', '').strip()
    # Sin base local y sin ML: solo mostramos la página con la barra visible y, si no hay resultados, el mensaje.
    return render(request, 'search.html', {'productos': [], 'query': q})


def ml_health(request):
    """
    GET /ml/health/ -> { ok: true, user_id, site_id }
    Comprueba que el token es válido y que podemos consultar /users/me.
    """
    try:
        me = ml_service.get_me()
        return JsonResponse({"ok": True, "user_id": me.get("id"), "site_id": me.get("site_id")})
    except Exception as e:
        return HttpResponseServerError(f"ML health failed: {e}")

def ml_search_api(request):
    """
    GET /api/ml/search/?q=mouse&offset=0
    Devuelve JSON con paging y results (usa buscar_items).
    """
    q = request.GET.get("q", "").strip() or "mouse"
    offset = int(request.GET.get("offset", 0) or 0)
    try:
        results, paging = ml_service.buscar_items(q, limit=24, offset=offset)
        return JsonResponse({"ok": True, "q": q, "paging": paging, "results": results})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)
    
def eco_tips(request):
    consejos = [
        {
            "titulo": "Reduce el uso de plástico",
            "descripcion": "Lleva siempre tu botella reutilizable y bolsas de tela para las compras. Evita los productos con envases innecesarios."
        },
        {
            "titulo": "Ahorra energía en casa",
            "descripcion": "Apaga las luces que no uses, desconecta aparatos en desuso y opta por bombillas LED de bajo consumo."
        },
        {
            "titulo": "Recicla correctamente",
            "descripcion": "Clasifica tus residuos y aprende qué materiales pueden reciclarse. Mantén limpios los envases antes de reciclarlos."
        },
        {
            "titulo": "Prefiere el transporte sustentable",
            "descripcion": "Camina, usa bicicleta o transporte público siempre que sea posible. Así reduces emisiones de CO₂."
        },
        {
            "titulo": "Consume productos locales",
            "descripcion": "Compra a productores de tu zona para reducir la huella de carbono del transporte y apoyar la economía local."
        }
    ]
    return render(request, 'eco_tips.html', {'consejos': consejos})
