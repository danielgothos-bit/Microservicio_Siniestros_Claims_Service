"""Lógica de negocio del flujo de un siniestro (cambios de estado + eventos)."""
from django.db import transaction

from comun.eventos import publicar

from .models import ClaimStatusHistory, Siniestro


class TransicionInvalida(Exception):
    pass


def datos_evento(siniestro, **extra):
    return {
        "id_siniestro": siniestro.id_siniestro,
        "id_poliza": siniestro.id_poliza,
        "id_asegurado": siniestro.id_asegurado,
        "status": siniestro.status,
        "estimated_amount": siniestro.estimated_amount,
        "incident_date": siniestro.incident_date,
        "reported_at": siniestro.reported_at,
        **extra,
    }


def registrar_historial(siniestro, previo, nuevo, changed_by=None):
    ClaimStatusHistory.objects.create(
        siniestro=siniestro, previous_status=previo, new_status=nuevo, changed_by=changed_by
    )


@transaction.atomic
def cambiar_estado(siniestro, nuevo, changed_by=None, forzar=False):
    """Cambia el estado validando la transición, guarda la auditoría y publica el evento."""
    previo = siniestro.status
    if not forzar and nuevo not in Siniestro.TRANSICIONES[previo]:
        raise TransicionInvalida(f"No se puede pasar de '{previo}' a '{nuevo}'.")

    siniestro.status = nuevo
    siniestro.save(update_fields=["status", "estimated_amount"])
    registrar_historial(siniestro, previo, nuevo, changed_by)

    if nuevo == Siniestro.DOCUMENTACION_PENDIENTE:
        publicar("claim.documentation_requested", datos_evento(siniestro))
    elif nuevo == Siniestro.APROBADO:
        publicar("claim.approved", datos_evento(siniestro, amount=siniestro.estimated_amount))
    elif nuevo == Siniestro.RECHAZADO:
        publicar("claim.rejected", datos_evento(siniestro))

    return siniestro
