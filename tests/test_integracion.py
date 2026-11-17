"""Prueba de integración: endpoint + lógica de negocio + base de datos funcionando juntos."""
from unittest import mock

from rest_framework.test import APITestCase

from siniestros.models import Siniestro
from siniestros.tests import COBERTURA, DATOS


@mock.patch("siniestros.servicios.publicar")
@mock.patch("siniestros.views.publicar")
@mock.patch("siniestros.views.get_json", return_value=COBERTURA)
class SiniestroIntegracionTests(APITestCase):
    def test_reportar_valida_cobertura_guarda_y_consulta_historial(self, get_json, publicar_v, publicar_s):
        resp = self.client.post("/api/v1/siniestros", DATOS, format="json")
        self.assertEqual(resp.status_code, 201)
        id_sin = resp.data["id_siniestro"]
        self.assertTrue(Siniestro.objects.filter(pk=id_sin, status="abierto").exists())
        self.assertEqual(publicar_v.call_args[0][0], "claim.opened")
        historial = self.client.get(f"/api/v1/siniestros/{id_sin}/historial").data["historial"]
        self.assertEqual(historial[0]["new_status"], "abierto")
