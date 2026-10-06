"""
Eventos que consume el microservicio de Siniestros (coreografía del patrón Saga, sección 6.3).

inspection.scheduled -> el siniestro pasa a "en_peritaje"
inspection.completed -> se evalúa el resultado y se aprueba la indemnización (publica claim.approved)
payment.completed    -> el siniestro pasa a "pagado"
payment.failed       -> compensación: queda "aprobado, pendiente de pago" (se registra en el historial)
document.uploaded    -> se guarda la referencia al documento
"""
import logging
import os

from .models import ClaimDocumentsRef, Siniestro
from .servicios import cambiar_estado, registrar_historial

logger = logging.getLogger(__name__)


def _siniestro(data):
    id_siniestro = data.get("id_siniestro") or data.get("referencia_id")
    siniestro = Siniestro.objects.filter(id_siniestro=id_siniestro).first() if id_siniestro else None
    if siniestro is None:
        logger.warning("evento para un siniestro inexistente", extra={"id_siniestro": id_siniestro})
    return siniestro


def on_inspection_scheduled(data):
    siniestro = _siniestro(data)
    if siniestro and siniestro.status in (Siniestro.ABIERTO, Siniestro.DOCUMENTACION_PENDIENTE):
        cambiar_estado(siniestro, Siniestro.EN_PERITAJE)


def on_inspection_completed(data):
    siniestro = _siniestro(data)
    if siniestro is None:
        return
    if siniestro.status == Siniestro.ABIERTO:
        cambiar_estado(siniestro, Siniestro.EN_PERITAJE)

    # Evaluación del resultado del peritaje: si está habilitada la aprobación automática,
    # se aprueba la indemnización por el monto estimado (paso 10 del diagrama de secuencia).
    if siniestro.status == Siniestro.EN_PERITAJE and os.getenv("AUTO_APROBAR_TRAS_PERITAJE", "1") == "1":
        cambiar_estado(siniestro, Siniestro.APROBADO)


def _es_indemnizacion(data):
    return data.get("tipo") == "indemnizacion"


def on_payment_completed(data):
    if not _es_indemnizacion(data):
        return
    siniestro = _siniestro(data)
    if siniestro and siniestro.status == Siniestro.APROBADO:
        cambiar_estado(siniestro, Siniestro.PAGADO, forzar=True)


def on_payment_failed(data):
    """Acción compensatoria del Saga: el siniestro queda aprobado, pendiente de pago."""
    if not _es_indemnizacion(data):
        return
    siniestro = _siniestro(data)
    if siniestro is None:
        return
    previo = siniestro.status
    if previo != Siniestro.APROBADO:
        siniestro.status = Siniestro.APROBADO
        siniestro.save(update_fields=["status"])
    registrar_historial(siniestro, previo, Siniestro.APROBADO)
    logger.warning("pago de indemnización fallido: siniestro aprobado, pendiente de pago",
                   extra={"claim_id": str(siniestro.id_siniestro)})


def on_document_uploaded(data):
    siniestro = _siniestro(data)
    if siniestro and data.get("id_documento"):
        ClaimDocumentsRef.objects.get_or_create(siniestro=siniestro, id_documento=data["id_documento"])


HANDLERS = {
    "inspection.scheduled": on_inspection_scheduled,
    "inspection.completed": on_inspection_completed,
    "payment.completed": on_payment_completed,
    "payment.failed": on_payment_failed,
    "document.uploaded": on_document_uploaded,
}
