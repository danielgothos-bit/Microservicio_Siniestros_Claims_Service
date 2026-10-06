import uuid

from django.db import models
from django.db.models import F, Q


class Siniestro(models.Model):
    ABIERTO = "abierto"
    EN_PERITAJE = "en_peritaje"
    DOCUMENTACION_PENDIENTE = "documentacion_pendiente"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"
    PAGADO = "pagado"
    CERRADO = "cerrado"

    STATUS_CHOICES = [
        (ABIERTO, "Abierto"),
        (EN_PERITAJE, "En peritaje"),
        (DOCUMENTACION_PENDIENTE, "Documentación pendiente"),
        (APROBADO, "Aprobado"),
        (RECHAZADO, "Rechazado"),
        (PAGADO, "Pagado"),
        (CERRADO, "Cerrado"),
    ]

    # Transiciones de estado permitidas (el paso a "pagado" solo llega por el evento de Pagos).
    TRANSICIONES = {
        ABIERTO: {EN_PERITAJE, DOCUMENTACION_PENDIENTE, APROBADO, RECHAZADO, CERRADO},
        EN_PERITAJE: {DOCUMENTACION_PENDIENTE, APROBADO, RECHAZADO},
        DOCUMENTACION_PENDIENTE: {ABIERTO, EN_PERITAJE, APROBADO, RECHAZADO},
        APROBADO: {CERRADO},
        RECHAZADO: {CERRADO},
        PAGADO: {CERRADO},
        CERRADO: set(),
    }

    id_siniestro = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_poliza = models.UUIDField()  # FK-ext -> Policy Service
    id_asegurado = models.UUIDField()  # FK-ext -> Policyholder Service
    incident_date = models.DateTimeField()
    reported_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=ABIERTO)
    estimated_amount = models.DecimalField(max_digits=14, decimal_places=2)
    descripcion = models.TextField()

    class Meta:
        db_table = "siniestro"
        indexes = [
            models.Index(fields=["id_poliza"], name="idx_siniestro_poliza"),
            models.Index(fields=["status"], name="idx_siniestro_status"),
            models.Index(fields=["id_asegurado"], name="idx_siniestro_asegurado"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=[
                    "abierto", "en_peritaje", "documentacion_pendiente",
                    "aprobado", "rechazado", "pagado", "cerrado",
                ]),
                name="chk_siniestro_status",
            ),
            models.CheckConstraint(condition=Q(estimated_amount__gte=0), name="chk_siniestro_amount"),
            models.CheckConstraint(condition=Q(incident_date__lte=F("reported_at")), name="chk_siniestro_fechas"),
        ]

    def __str__(self):
        return f"Siniestro {self.id_siniestro} - {self.status}"


class ClaimStatusHistory(models.Model):
    """Auditoría de cada cambio de estado (requisito regulatorio, sección 5.3)."""

    id_hist = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    siniestro = models.ForeignKey(Siniestro, on_delete=models.CASCADE, related_name="historial", db_column="id_siniestro")
    previous_status = models.CharField(max_length=30, blank=True, null=True)
    new_status = models.CharField(max_length=30)
    changed_by = models.UUIDField(blank=True, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "claim_status_history"
        ordering = ["changed_at"]
        indexes = [
            models.Index(fields=["siniestro"], name="idx_claim_status_history_sin"),
        ]


class ClaimDocumentsRef(models.Model):
    """Referencias a documentos del Document Service asociados al siniestro."""

    id_ref = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    siniestro = models.ForeignKey(Siniestro, on_delete=models.CASCADE, related_name="documentos", db_column="id_siniestro")
    id_documento = models.UUIDField()  # FK-ext -> Document Service

    class Meta:
        db_table = "claim_documents_ref"
        constraints = [
            models.UniqueConstraint(fields=["siniestro", "id_documento"], name="uq_claim_documento"),
        ]
