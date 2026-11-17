"""Pruebas unitarias: una unidad de lógica de negocio aislada; las dependencias externas se simulan con mocks."""
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from siniestros.models import Siniestro
from siniestros.servicios import TransicionInvalida, cambiar_estado


class SagaUnitTests(TestCase):
    def test_no_permite_transicion_invalida(self):
        pagado = Siniestro(status=Siniestro.PAGADO)
        with self.assertRaises(TransicionInvalida):
            cambiar_estado(pagado, Siniestro.EN_PERITAJE)


class AprobacionUnitTests(TestCase):
    @mock.patch("siniestros.servicios.publicar")
    def test_aprobar_publica_claim_approved_con_monto(self, publicar):
        s = Siniestro.objects.create(id_poliza=uuid.uuid4(), id_asegurado=uuid.uuid4(), status=Siniestro.EN_PERITAJE,
                                     estimated_amount=Decimal("3500000"), descripcion="Choque",
                                     incident_date=timezone.now() - timedelta(hours=3))
        cambiar_estado(s, Siniestro.APROBADO)
        evento, datos = publicar.call_args[0]
        self.assertEqual(evento, "claim.approved")
        self.assertEqual(datos["amount"], Decimal("3500000"))
        self.assertEqual(s.historial.count(), 1)
