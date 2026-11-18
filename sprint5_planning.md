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
| pip install django-anymail[sendgrid] | ✅ W17 |
| EMAIL_BACKEND configurado (consola en desarrollo; SendGrid en producción solo si hay SENDGRID_API_KEY) | ✅ W17 |
| correo_enviado en Pedido + migración 0005 | ✅ W17 |
| Templates confirmacion_pedido (.html y .txt) | ✅ W17 |
| Templates alerta_stock (.html y .txt) | ✅ W17 |
| enviar_confirmacion_pedido: correo real + idempotencia | ✅ W17 |
| verificar_stock_bajo: alerta al administrador | ✅ W17 |
| 9 tests con mail.outbox (174 en total) | ✅ W17 |
| Celery Beat + tareas programadas | ⏳ W18 |

### Desviaciones y pendientes W17 (informar al asesor)

1. **Cuenta de SendGrid:** pendiente de autorización del asesor. Mientras
   no exista SENDGRID_API_KEY, el sistema usa el backend de consola y
   los correos se verifican con tests (mail.outbox) y en consola.
2. **Redis en Render:** no hay broker en producción, así que el encolado
   falla de forma controlada (aviso en log) y no se envían correos allá.
   Alternativas a decidir con el asesor: modo eager, Render Key Value u
   otro servicio.
3. **Migración:** la nueva es 0005_correo_enviado_pedido (la guía decía
   0004, que ya existía).
4. **Tests:** son 9 (no 8); las tareas se prueban con .apply() para no
   depender de Redis. Total acumulado: 174.
5. **Botón del correo:** apunta al catálogo (la guía apuntaba a una ruta
   de ventas que no corresponde a pedidos). Subtotales calculados en la
   tarea en lugar de widthratio.