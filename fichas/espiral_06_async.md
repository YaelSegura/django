# Ficha de Sistematización — Espiral 6
## ERP Django · Espiral E6: Celery e Integraciones
## UTEC Celaya · Técnico en Programación (SEP 3061300006-23)

| Campo | Contenido |
|---|---|
| **Número de espiral** | 6 |
| **Nombre del ciclo** | Celery e Integraciones |
| **Semanas** | W16 – W18 |
| **Fecha de inicio** | 17/11/2026 |
| **Fecha de cierre** | 24/11/2026 |
| **Responsable** | Yael Segura |
| **Asesor** | MC. Román Fernando López González |

---

## 1. Objetivo del ciclo
Implementar procesamiento asíncrono con Celery y Redis para: correos transaccionales de confirmación de pedido, alertas de stock bajo y reportes diarios automáticos vía Celery Beat, en un entorno sin Docker Desktop (laboratorio en modo EAGER) y con producción en el plan gratuito de Render.

---

## 2. Tareas realizadas
| # | Tarea | Estado | Semana |
|---|---|---|---|
| 1 | Celery 5.3.6 + redis 5.0.1 + flower 2.0.1 | ✅ | W16 |
| 2 | core/celery.py + core/__init__.py | ✅ | W16 |
| 3 | CELERY_* en settings: Redis si hay REDIS_URL, EAGER si no | ✅ | W16 |
| 4 | Webhook payment_intent.succeeded como único disparador del correo | ✅ | W16 |
| 5 | django-anymail[sendgrid]==10.3; SendGrid en prod si hay API Key | ✅ | W17 |
| 6 | Pedido.correo_enviado + migración 0005 (idempotencia) | ✅ | W17 |
| 7 | Templates confirmacion_pedido y alerta_stock (.html + .txt) | ✅ | W17 |
| 8 | enviar_confirmacion_pedido: correo real + idempotencia + retry | ✅ | W17 |
| 9 | verificar_stock_bajo: alerta al admin | ✅ | W17 |
| 10 | Templates reporte_ventas (.html + .txt) con KPIs y tabla | ✅ | W18 |
| 11 | reporte_ventas_diario con annotate + Sum(F(...)) | ✅ | W18 |
| 12 | CELERY_BEAT_SCHEDULE: crontab(6:50) + timedelta(hours=1) | ✅ | W18 |
| 13 | Fix kombu==5.3.7 (VersionMismatch con redis-py 5.0.1) | ✅ | W18 |
| 14 | Acción admin para reenviar confirmación de pagados sin correo | ✅ | W18 |

---

## 3. Evidencias
- Pruebas: `python manage.py test tests` → **Ran 186 tests — OK (skipped=2)**
- Pruebas de la espiral: `test_w16_celery` (9), `test_w17_correo` (9), `test_w18_beat` (10), `test_w18_dependencias` (2)
- Correo de confirmación: consola local `Resultado 1: ok` / `Resultado 2: skip`
- Logs de Render a verificar tras desplegar:
  - [ ] `Celery Beat embebido ACTIVADO (reporte diario 06:50 hora MX)`
  - [ ] `celery@... ready.` y `beat: Starting...` sin `VersionMismatch`
  - [ ] `Scheduler: Sending due task reporte-ventas-diario-8am`

---

## 4. Criterios de aceptación
| Criterio | Estado |
|---|---|
| Worker procesa enviar_confirmacion_pedido | ✅ |
| correo_enviado=True previene duplicados | ✅ |
| Alerta de stock enviada al admin | ✅ |
| reporte_ventas_diario en CELERY_BEAT_SCHEDULE | ✅ |
| verificar_stock_bajo en CELERY_BEAT_SCHEDULE | ✅ |
| 186 tests OK | ✅ |

---

## 5. Problemas encontrados
| Problema | Causa | Solución aplicada |
|---|---|---|
| Sin Docker Desktop en el laboratorio | Política del equipo | Modo EAGER sin REDIS_URL; Redis/worker solo en Render |
| Webhook: VersionMismatch: redis-py 6.1.0 or later | pip freeze subió kombu a 5.7.0 | kombu==5.3.7 + prueba de compatibilidad |
| Top de productos vacío | El checkout crea Pedido, no Venta | Top suma también items_snapshot |
| SendGrid 401 (Unauthorized) | Se usó una API Key de Twilio (SK...) en lugar de SendGrid (SG...) | Usar API Key de SendGrid (SG...) |
| SendGrid 403 | DEFAULT_FROM_EMAIL ≠ remitente verificado | Usar el From del Single Sender |

---

## 6. Lecciones aprendidas
1. El modo EAGER es ideal para desarrollar, pero oculta los errores de conexión con el broker: hay que probar el transporte real o al menos la compatibilidad de versiones.
2. La idempotencia (correo_enviado) se diseña desde el modelo, no se agrega después.
3. En plataformas como Twilio/SendGrid, es crucial verificar en qué panel estás (Twilio API vs SendGrid API) y qué formato de clave se necesita.