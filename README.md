# Microservicio de Siniestros — Claims Service

Microservicio de InsureFlow definido en la sección 4.3 del documento de arquitectura.

## Responsabilidad

Gestionar la apertura, seguimiento y resolución de reclamaciones, orquestando el flujo con Pólizas, Peritaje, Pagos y Documentación (patrón Saga).

## Tecnología

Python · Django REST Framework · PostgreSQL (`claims_db`) · Celery + Redis · Docker

## Modelo de datos (3FN, IDs UUID)

`siniestro`, `claim_status_history` (auditoría de cada cambio de estado) y `claim_documents_ref`.

## Endpoints

```
POST /api/v1/siniestros — reportar siniestro (valida cobertura con Pólizas)
GET  /api/v1/siniestros — listar (filtro ?status=)
GET  /api/v1/siniestros/{id} — consultar siniestro
PUT  /api/v1/siniestros/{id}/estado — actualizar estado
GET  /api/v1/siniestros/asegurado/{id} — siniestros de un asegurado
GET  /api/v1/siniestros/{id}/historial — historial de estados
GET  /health — estado del servicio y de su base de datos
POST /api/v1/eventos — endpoint interno donde otros microservicios entregan eventos
```

## Eventos

Publica:
- claim.opened
- claim.documentation_requested
- claim.approved
- claim.rejected

Consume:
- inspection.scheduled
- inspection.completed
- payment.completed
- payment.failed (compensación)
- document.uploaded

Los eventos se encolan con Celery/Redis y se entregan por HTTP al endpoint `/api/v1/eventos` de cada
suscriptor, con reintentos y backoff exponencial (módulo `comun/eventos.py`). Cada evento se procesa una
sola vez (idempotencia por `event_id`).

## Variables de entorno

- `DATABASE_URL`, `REDIS_URL`: base de datos y Redis propios
- `INTERNAL_TOKEN`: token compartido por todos los microservicios para los eventos
- `RUN_WORKER_IN_WEB=1`: corre el worker de Celery dentro del mismo contenedor (Render gratis)
- `SYNC_TIMEOUT`: timeout de las llamadas REST síncronas (3 s por defecto)
- `POLICY_SERVICE_URL`: microservicio de Pólizas
- `ADJUSTER_SERVICE_URL`: microservicio de Peritaje
- `PAYMENT_SERVICE_URL`: microservicio de Pagos
- `NOTIFICATION_SERVICE_URL`: microservicio de Notificaciones
- `ANALYTICS_SERVICE_URL`: microservicio de Analítica

Si una URL no está configurada, el servicio funciona en modo aislado (omite esa validación o ese evento).

## Ejecución local

```bash
docker compose up --build
```

El servicio queda en http://localhost:8004 y las migraciones se aplican solas al arrancar.

Pruebas:

```bash
docker compose exec claims_service python manage.py test siniestros
```

## Despliegue en Render

En Render: **New → Blueprint** → conectar este repositorio → **Deploy Blueprint**.
El `render.yaml` crea el servicio web, su PostgreSQL y su Redis (plan gratis).

## Enlaces

| | |
|---|---|
| Servicio desplegado | https://claims-service-k83g.onrender.com |
| Estado (health check) | https://claims-service-k83g.onrender.com/health |
| Documentación de la API (Swagger) | https://claims-service-k83g.onrender.com/api/docs |
| Esquema OpenAPI | https://claims-service-k83g.onrender.com/api/schema |
| Métricas Prometheus | https://claims-service-k83g.onrender.com/metrics |
| Sitio y API Gateway | https://insureflow-gateway-kxhm.onrender.com |

## Pruebas y cobertura

Las pruebas exigidas están en `tests/`:

- `tests/test_unitarias.py`: **2 pruebas unitarias** que verifican una regla de negocio aislada, con *mocks* para la base de datos, otros microservicios, la pasarela o el bus de eventos.
- `tests/test_integracion.py`: **1 prueba de integración** que recorre endpoint, lógica de negocio y base de datos.
- Las pruebas adicionales de la aplicación están en `<app>/tests.py`.

Para ejecutarlas (sin PostgreSQL ni Redis):

```bash
pip install -r requirements.txt coverage
USE_SQLITE=1 CELERY_EAGER=1 coverage run manage.py test -v 2
coverage report        # porcentaje de cobertura
coverage html          # reporte navegable en htmlcov/
```

En GitHub Actions (`.github/workflows/ci.yml`) el reporte de cobertura se publica en el resumen de la ejecución y como artefacto `reporte-cobertura`.

## CI/CD

| Archivo | Función |
|---|---|
| `.github/workflows/ci.yml` | En cada push y pull request: lint (flake8), pruebas unitarias y de integración con cobertura, auditoría de dependencias (pip-audit) e imagen Docker. Si algo falla, no se despliega. |
| `.github/workflows/deploy.yml` | Solo cuando CI termina con éxito en `main`: llama al Deploy Hook de Render (secreto `RENDER_DEPLOY_HOOK_URL`) y espera a que `/health` responda. |
| `.github/workflows/codeql.yml` | Análisis estático de seguridad. |

**Estrategia de ramas (GitFlow):**

- `main`: producción.
- `develop`: integración.
- `feature/*`: funcionalidades nuevas.
- `hotfix/*`: correcciones urgentes.

Los cambios entran por *pull request* con el pipeline en verde.

## Base de datos

- **Esquema:** migraciones de Django en `<app>/migrations/`, que se aplican solas al arrancar el contenedor (`start.sh`).
- **Datos de ejemplo:** `datos/datos_ejemplo.json`. Para cargarlos: `python manage.py loaddata datos/datos_ejemplo.json`.
- **Respaldo:** `datos/respaldo.sql` (volcado de PostgreSQL con `pg_dump`).
- **Variables de entorno:** ver `.env.example`. No se suben credenciales al repositorio.
