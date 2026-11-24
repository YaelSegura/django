# Sprint 5 Planning — ERP Django
## Semanas W16–W18 · Espiral 6: Celery e Integraciones

**Sprint Goal:**
Al finalizar el Sprint 5, el ERP ejecutará tareas pesadas de forma
asíncrona con Celery+Redis: correos de confirmación, alertas de
stock bajo y reporte diario de ventas.

## HUs seleccionadas

| ID | Historia | Puntos | Semana |
|---|---|---|---|
| HU-E6-01 | Como dev, quiero infraestructura Celery+Redis funcional | 3 | W16 |
| HU-E6-02 | Como sistema, quiero ejecutar tareas sin bloquear HTTP | 2 | W16 |
| HU-E6-03 | Como cliente, quiero correo de confirmación post-pago | 5 | W17 |
| HU-E6-04 | Como admin, quiero correo cuando el stock es bajo | 3 | W17 |
| HU-E6-05 | Como admin, quiero reporte diario de ventas a las 8 AM | 3 | W18 |
| HU-E6-06 | Como dev, quiero monitorear tareas con Flower | 2 | W16 |

**Total Sprint 5:** 18 puntos

## DoD — Sprint 5
- celery -A core worker → procesa tareas sin error
- POST /catalogo/checkout/ → tarea de correo en la cola (no espera)
- Correo de confirmación recibido en < 30 s (W17)
- Alerta de stock enviada cuando stock < umbral (W17)
- Reporte diario ejecutado a las 8:00 AM (W18)
- python manage.py test → ≥ 155 tests OK

## Sprint Backlog — actualización W17

| Tarea | Estado |
|---|---|
| django-anymail[sendgrid] instalado | ✅ W17 |
| EMAIL_BACKEND: consola en desarrollo; SendGrid solo si hay SENDGRID_API_KEY | ✅ W17 |
| correo_enviado en Pedido + migración 0005 | ✅ W17 |
| Templates confirmacion_pedido y alerta_stock (.html y .txt) | ✅ W17 |
| enviar_confirmacion_pedido con idempotencia | ✅ W17 |
| verificar_stock_bajo con alerta al administrador | ✅ W17 |
| 9 tests con mail.outbox (174 en total) | ✅ W17 |
| Celery Beat + tareas programadas | ⏳ W18 |

### Desviaciones y pendientes W17 (informar al asesor)

1. SendGrid ya no tiene plan gratuito permanente: se usa la prueba de
   Twilio SendGrid (termina el 17/01/2027). Remitente único verificado.
2. Redis/worker no disponibles en Render gratis: en producción las tareas
   se ejecutan en modo eager (CELERY_TASK_ALWAYS_EAGER=True).
3. Migración: 0005_correo_enviado_pedido (la guía decía 0004, ya existía).
4. Tests: son 9 (no 8); las tareas se prueban con .apply(). Total: 174.
5. El botón del correo apunta al catálogo y los subtotales se calculan en
   la tarea (la guía usaba widthratio y una ruta de ventas incorrecta).
6. Incidente de entorno: archivos de env_erp se corrompieron al copiarse
   entre la USB y C:; se creó un entorno nuevo desde requirements.txt.