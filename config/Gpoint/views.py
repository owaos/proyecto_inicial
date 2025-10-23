from django.shortcuts import render,redirect
from .services.mercadolibre import buscar_items
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
def productos(request):
    query = request.GET.get('busqueda', '').strip().lower()
    if not ("producto" in query):
        return redirect('/search/?busqueda=' + query)
    if "producto" in query:    
        productos = [
            {
                "nombre": "Guatero de semillas natural",
                "descripcion": "Guatero relleno de semillas y hierbas aromáticas, ideal para aliviar dolores musculares o relajarse.",
                "precio": 8990,
                "imagen": "Gpoint/images/guatero.webp"
            },
            {
                "nombre": "Bolsa de tela reutilizable",
                "descripcion": "Bolsa de algodón resistente, ideal para compras ecológicas y reemplazar las bolsas plásticas.",
                "precio": 4990,
                "imagen": "Gpoint/images/bolsa_tela.jpg"
            },
            {
                "nombre": "Botella de agua reutilizable",
                "descripcion": "Botella de acero inoxidable con tapa hermética, libre de BPA, mantiene la temperatura por horas.",
                "precio": 12990,
                "imagen": "Gpoint/images/botella.webp"
            },
            {
                "nombre": "Cepillo de bambú natural",
                "descripcion": "Cepillo de dientes ecológico, hecho de bambú 100% biodegradable con cerdas suaves.",
                "precio": 2990,
                "imagen": "Gpoint/images/cepillo.png"
            },
            {
                "nombre": "Bombillas metálicas reutilizables",
                "descripcion": "Set de 4 bombillas de acero inoxidable con cepillo de limpieza y estuche de tela.",
                "precio": 5990,
                "imagen": "Gpoint/images/bombillas.webp"
            },
        ]

    return render(request, 'search.html', {'productos': productos, 'query': query})