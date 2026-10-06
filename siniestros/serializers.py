from django.utils import timezone
from rest_framework import serializers

from .models import ClaimStatusHistory, Siniestro


class SiniestroSerializer(serializers.ModelSerializer):
    documentos = serializers.SerializerMethodField()
    id_asegurado = serializers.UUIDField(required=False)

    class Meta:
        model = Siniestro
        fields = [
            "id_siniestro",
            "id_poliza",
            "id_asegurado",
            "incident_date",
            "reported_at",
            "status",
            "estimated_amount",
            "descripcion",
            "documentos",
        ]
        read_only_fields = ["id_siniestro", "reported_at", "status"]

    def get_documentos(self, obj):
        return [str(ref.id_documento) for ref in obj.documentos.all()]

    def validate_incident_date(self, value):
        if value > timezone.now():
            raise serializers.ValidationError("La fecha del incidente no puede ser futura.")
        return value

    def validate_estimated_amount(self, value):
        if value < 0:
            raise serializers.ValidationError("El monto estimado no puede ser negativo.")
        return value


class HistorialSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClaimStatusHistory
        fields = ["id_hist", "previous_status", "new_status", "changed_by", "changed_at"]


class EstadoSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[c for c, _ in Siniestro.STATUS_CHOICES if c != Siniestro.PAGADO])
    changed_by = serializers.UUIDField(required=False)
    estimated_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False)
