from django.urls import path

from . import views

urlpatterns = [
    path("api/v1/siniestros", views.siniestros),
    path("api/v1/siniestros/<uuid:id>", views.siniestro_detalle),
    path("api/v1/siniestros/<uuid:id>/estado", views.siniestro_estado),
    path("api/v1/siniestros/<uuid:id>/historial", views.siniestro_historial),
    path("api/v1/siniestros/asegurado/<uuid:id>", views.siniestros_por_asegurado),
]
