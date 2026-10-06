import uuid
from unittest import mock

from rest_framework.test import APITestCase

from comun.clientes import ServicioNoDisponible
from comun.eventos import INTERNAL_TOKEN

POLIZA = str(uuid.uuid4())
ASEGURADO = str(uuid.uuid4())

COBERTURA = {
    "id_poliza": POLIZA,
    "id_asegurado": ASEGURADO,
    "vigente": True,
    "product_type": "auto",
    "premium": "1200000.00",
    "effective_date": "2026-01-01",
}

DATOS = {
    "id_poliza": POLIZA,
    "incident_date": "2026-09-20T15:30:00-05:00",
    "estimated_amount": "4500000.00",
    "descripcion": "Choque trasero en la Av. 80",
}


@mock.patch("siniestros.servicios.publicar")
@mock.patch("siniestros.views.publicar")
@mock.patch("siniestros.views.get_json", return_value=COBERTURA)
class SiniestrosTests(APITestCase):
    def reportar(self):
        return self.client.post("/api/v1/siniestros", DATOS, format="json")

    def evento(self, nombre, data):
        return self.client.post("/api/v1/eventos", {"event": nombre, "data": data},
                                format="json", HTTP_X_INTERNAL_TOKEN=INTERNAL_TOKEN)

    def test_reportar_valida_cobertura_y_publica(self, get_json, publicar_v, publicar_s):
        resp = self.reportar()
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["status"], "abierto")
        self.assertEqual(resp.data["id_asegurado"], ASEGURADO)
        get_json.assert_called_once_with("POLICY", f"/api/v1/polizas/{POLIZA}/cobertura", params={"fecha": "2026-09-20"})
        evento, data = publicar_v.call_args[0]
        self.assertEqual(evento, "claim.opened")
        self.assertEqual(data["product_type"], "auto")

    def test_sin_cobertura(self, get_json, publicar_v, publicar_s):
        get_json.return_value = dict(COBERTURA, vigente=False)
        resp = self.reportar()
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.data["code"], "NO_COVERAGE")
        publicar_v.assert_not_called()

    def test_polizas_caido(self, get_json, publicar_v, publicar_s):
        get_json.side_effect = ServicioNoDisponible("Circuito abierto hacia POLICY.")
        self.assertEqual(self.reportar().status_code, 503)

    def test_transiciones_e_historial(self, get_json, publicar_v, publicar_s):
        id = self.reportar().data["id_siniestro"]

        resp = self.client.put(f"/api/v1/siniestros/{id}/estado", {"status": "documentacion_pendiente"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(publicar_s.call_args[0][0], "claim.documentation_requested")

        resp = self.client.put(f"/api/v1/siniestros/{id}/estado", {"status": "aprobado"}, format="json")
        self.assertEqual(publicar_s.call_args[0][0], "claim.approved")
        self.assertEqual(str(publicar_s.call_args[0][1]["amount"]), "4500000.00")

        resp = self.client.put(f"/api/v1/siniestros/{id}/estado", {"status": "abierto"}, format="json")
        self.assertEqual(resp.status_code, 409)

        resp = self.client.get(f"/api/v1/siniestros/{id}/historial")
        estados = [h["new_status"] for h in resp.data["historial"]]
        self.assertEqual(estados, ["abierto", "documentacion_pendiente", "aprobado"])

    def test_flujo_completo_por_eventos(self, get_json, publicar_v, publicar_s):
        id = self.reportar().data["id_siniestro"]

        self.evento("inspection.scheduled", {"id_siniestro": id})
        self.assertEqual(self.client.get(f"/api/v1/siniestros/{id}").data["status"], "en_peritaje")

        self.evento("inspection.completed", {"id_siniestro": id, "findings": "Daño en bomper"})
        self.assertEqual(self.client.get(f"/api/v1/siniestros/{id}").data["status"], "aprobado")
        self.assertEqual(publicar_s.call_args[0][0], "claim.approved")

        self.evento("payment.completed", {"tipo": "indemnizacion", "id_siniestro": id})
        self.assertEqual(self.client.get(f"/api/v1/siniestros/{id}").data["status"], "pagado")

        doc = str(uuid.uuid4())
        self.evento("document.uploaded", {"id_siniestro": id, "id_documento": doc})
        self.assertEqual(self.client.get(f"/api/v1/siniestros/{id}").data["documentos"], [doc])

    def test_compensacion_pago_fallido(self, get_json, publicar_v, publicar_s):
        id = self.reportar().data["id_siniestro"]
        self.client.put(f"/api/v1/siniestros/{id}/estado", {"status": "aprobado"}, format="json")

        self.evento("payment.failed", {"tipo": "indemnizacion", "id_siniestro": id})
        resp = self.client.get(f"/api/v1/siniestros/{id}/historial")
        self.assertEqual(resp.data["status"], "aprobado")
        self.assertEqual(resp.data["historial"][-1]["previous_status"], "aprobado")

    def test_evento_sin_token(self, get_json, publicar_v, publicar_s):
        resp = self.client.post("/api/v1/eventos", {"event": "payment.completed", "data": {}}, format="json")
        self.assertEqual(resp.status_code, 401)
