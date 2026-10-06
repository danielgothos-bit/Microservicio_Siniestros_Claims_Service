import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from comun.clientes import ServicioNoDisponible, get_json
from comun.eventos import publicar

from .models import Siniestro
from .serializers import EstadoSerializer, HistorialSerializer, SiniestroSerializer
from .servicios import TransicionInvalida, cambiar_estado, datos_evento, registrar_historial

logger = logging.getLogger(__name__)


def error(code, message, http_status):
    return Response({"code": code, "message": message}, status=http_status)


def validar_cobertura(id_poliza, incident_date):
    """
    Validación síncrona contra el Policy Service: ¿la póliza tenía cobertura vigente
    en la fecha del incidente? (secciones 4.3 y 5.9). Retorna (cobertura, respuesta_error).
    """
    try:
        cobertura = get_json("POLICY", f"/api/v1/polizas/{id_poliza}/cobertura",
                             params={"fecha": incident_date.date().isoformat()})
    except ServicioNoDisponible as exc:
        if "no está configurada" in str(exc):
            logger.warning("validación de cobertura omitida (modo aislado)")
            return {}, None
        return None, error("SERVICE_UNAVAILABLE", "El servicio de Pólizas no está disponible.",
                           status.HTTP_503_SERVICE_UNAVAILABLE)

    if cobertura is None:
        return None, error("POLICY_NOT_FOUND", "La póliza no existe.", status.HTTP_422_UNPROCESSABLE_ENTITY)
    if not cobertura.get("vigente"):
        return None, error("NO_COVERAGE", "La póliza no tenía cobertura vigente en la fecha del incidente.",
                           status.HTTP_422_UNPROCESSABLE_ENTITY)
    return cobertura, None


@api_view(["GET", "POST"])
def siniestros(request):
    if request.method == "GET":
        qs = Siniestro.objects.prefetch_related("documentos").order_by("-reported_at")
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return Response(SiniestroSerializer(qs, many=True).data)

    serializer = SiniestroSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    datos = serializer.validated_data

    cobertura, respuesta_error = validar_cobertura(datos["id_poliza"], datos["incident_date"])
    if respuesta_error:
        return respuesta_error

    id_asegurado = cobertura.get("id_asegurado") or datos.get("id_asegurado")
    if not id_asegurado:
        return error("VALIDATION_ERROR", "id_asegurado es obligatorio.", status.HTTP_400_BAD_REQUEST)
    if datos.get("id_asegurado") and str(datos["id_asegurado"]) != str(id_asegurado):
        return error("POLICYHOLDER_MISMATCH", "La póliza no pertenece a ese asegurado.",
                     status.HTTP_422_UNPROCESSABLE_ENTITY)

    with transaction.atomic():
        siniestro = serializer.save(id_asegurado=id_asegurado)
        registrar_historial(siniestro, None, Siniestro.ABIERTO)
        publicar("claim.opened", datos_evento(
            siniestro,
            product_type=cobertura.get("product_type"),
            premium=cobertura.get("premium"),
            policy_effective_date=cobertura.get("effective_date"),
        ))

    return Response(SiniestroSerializer(siniestro).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def siniestro_detalle(request, id):
    siniestro = get_object_or_404(Siniestro, id_siniestro=id)
    return Response(SiniestroSerializer(siniestro).data)


@api_view(["PUT"])
def siniestro_estado(request, id):
    siniestro = get_object_or_404(Siniestro, id_siniestro=id)
    serializer = EstadoSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    datos = serializer.validated_data

    if "estimated_amount" in datos:
        siniestro.estimated_amount = datos["estimated_amount"]

    try:
        cambiar_estado(siniestro, datos["status"], datos.get("changed_by"))
    except TransicionInvalida as exc:
        return error("INVALID_TRANSITION", str(exc), status.HTTP_409_CONFLICT)

    return Response(SiniestroSerializer(siniestro).data)


@api_view(["GET"])
def siniestros_por_asegurado(request, id):
    qs = Siniestro.objects.filter(id_asegurado=id).prefetch_related("documentos").order_by("-reported_at")
    return Response(SiniestroSerializer(qs, many=True).data)


@api_view(["GET"])
def siniestro_historial(request, id):
    siniestro = get_object_or_404(Siniestro, id_siniestro=id)
    return Response({
        "id_siniestro": siniestro.id_siniestro,
        "status": siniestro.status,
        "historial": HistorialSerializer(siniestro.historial.all(), many=True).data,
    })
