# Suite de pruebas automatizadas — API de Reserva de Laboratorios

Pruebas derivadas de las Historias de Usuario y sus Criterios de Aceptación en
formato Gherkin (Entregables 3 y 4).

## Cómo ejecutar

```bash
# 1. Instalar dependencias (una sola vez)
pip install -r requirements-dev.txt

# 2. Levantar la base de datos de pruebas (queda corriendo en segundo plano)
docker compose -f docker-compose.test.yml up -d

# 3. Ejecutar la suite
pytest
```

Para apagar la base de pruebas: `docker compose -f docker-compose.test.yml down -v`

## Comandos

### Ejecutar

```bash
pytest                       # toda la suite        -> 227 passed,  3 xfailed
pytest -m unit               # solo unitarias       ->  58 passed,  3 xfailed
pytest -m integration        # solo integración     -> 169 passed
pytest -m smoke              # contra Render        ->   7 passed
```

### Filtrar por historia

```bash
pytest -m hu001              # todo lo que respalda a HU-001
pytest -m "hu001 or hu002"   # varias historias
pytest -m "unit and hu009"   # cruzar tipo e historia
pytest tests/integration/test_hu004_listado_global.py   # un archivo
pytest -k "traslape"         # por nombre de prueba
```

### Generar el reporte

Un solo comando produce las tres salidas que consume el pipeline:

```bash
pytest \
  --html=reports/reporte.html --self-contained-html \
  --junitxml=reports/junit.xml \
  --cov=reservas --cov=labs --cov=usuarios --cov=condiciones --cov=logs \
  --cov-report=html:reports/cobertura \
  --cov-report=term
```

| Salida | Para qué sirve |
|---|---|
| `reports/reporte.html` | Reporte navegable, autocontenido — se abre en cualquier navegador |
| `reports/junit.xml` | Formato estándar que GitHub Actions convierte en el resumen del workflow |
| `reports/cobertura/index.html` | Cobertura línea por línea, con el código coloreado |

### Ver los defectos

```bash
pytest --runxfail            # los 3 xfail se muestran como fallos reales
pytest -rx                   # lista los xfail con su motivo, sin fallar
```

`--runxfail` es la forma de demostrar que los defectos son reales y no pruebas
desactivadas: desarma las marcas y la suite reporta `3 failed`. Los tres son
`DEF-014` (validación de dominio del correo institucional) — es el único
defecto que hoy queda respaldado por una prueba marcada `xfail`. El resto de
los defectos abiertos (ver la sección de más abajo) no tienen marca `xfail`
porque no rompen ningún criterio de aceptación escrito: son hallazgos de
cobertura adicional.

### Inspeccionar

```bash
pytest --collect-only -q     # lista las pruebas sin ejecutarlas
pytest --durations=10        # las 10 más lentas
pytest -x                    # se detiene en el primer fallo
pytest -q                    # salida compacta
```

## Estrategia de ambientes

| Nivel | Contra qué corre | Escribe datos | Cuándo |
|---|---|---|---|
| Unitarias | PostgreSQL 18 efímero (contenedor) | Sí, y revierte | Cada push y en local |
| Integración | PostgreSQL 18 efímero (contenedor) | Sí, y revierte | Cada push y en local |
| Smoke | API desplegada en Render | **No, solo lectura** | Manual / post-deploy |

La base productiva de Render **nunca** participa en las pruebas unitarias ni de integración. Se usa un PostgreSQL 18 desechable —el mismo motor que producción,
por lo que se conserva la fidelidad de comportamiento— y `pytest-django` envuelve cada prueba en una transacción que se revierte al terminar.

Los smoke tests sí golpean el despliegue real, pero se limitan a peticiones `GET`.
Se ejecutan aparte:

```bash
pytest -m smoke
```

La URL sale de `SMOKE_BASE_URL`, resuelta con `python-decouple` igual que las
credenciales de base de datos. Como decouple da prioridad a las variables de
entorno del sistema sobre el archivo `.env`, la misma línea de código sirve en
los dos ambientes:

| Ambiente | Dónde se define |
|---|---|
| Local | `.env` → `SMOKE_BASE_URL=https://umg-api-django.onrender.com` |
| GitHub Actions | *Settings → Secrets and variables → Actions → Variables* |

Si no está definida, las pruebas se omiten (`skip`) y la suite normal no se ve
afectada.

**Sobre el arranque en frío.** Render suspende los servicios del plan gratuito
tras un rato sin tráfico, y la primera petición dispara el arranque del
contenedor —que puede tardar más de un minuto—. Para que ninguna prueba falle por
una causa ajena a la API, la fixture `sesion` despierta el servicio antes de
empezar y reintenta hasta agotar un presupuesto de 4 minutos. Ese costo se paga
una sola vez por corrida: una vez despierto, la suite completa toma ~25 s.

## Estructura

```
tests/
├── conftest.py                          fixtures compartidas (usuarios, labs, payloads)
├── unit/
│   ├── test_hu001_reglas.py             contrato de la reserva + formato de correo
│   ├── test_hu002_reglas.py             hay_traslape() y hay_bloqueo()
│   ├── test_hu003_reglas.py             contrato del laboratorio
│   ├── test_hu008_reglas.py             contrato de usuario y rol (RN-013)
│   └── test_hu009_reglas.py             registrar_log() y contrato del historial
├── integration/
│   ├── test_hu001_crear_reserva.py            6 escenarios — registrar reserva
│   ├── test_hu002_disponibilidad.py           3 escenarios — validar disponibilidad
│   ├── test_hu003_consultar_disponibilidad.py 3 escenarios — disponibilidad de labs
│   ├── test_hu004_listado_global.py           2 escenarios — listado global
│   ├── test_hu005_consultar_por_id.py         2 escenarios — detalle por ID
│   ├── test_hu006_filtrar_reservas.py         2 escenarios — filtros
│   ├── test_hu007_modificar_reserva.py        4 escenarios — modificar reserva
│   ├── test_hu008_cancelar_reserva.py         3 escenarios — cancelación
│   ├── test_hu009_auditoria.py                3 escenarios — historial
│   └── test_hu010_estados.py                  4 escenarios — ciclo de vida
└── smoke/
    └── test_smoke_produccion.py         verificación de solo lectura sobre Render
```

Cada clase de `integration/` corresponde a un escenario del documento de criterios
y lleva el Gherkin completo en su docstring, de modo que la trazabilidad
criterio → prueba es directa.

## Estado actual

| Suite | Resultado | Duración |
|---|---|---|
| Unitarias | `58 passed, 3 xfailed` | ~1.7 s |
| Integración | `169 passed` | ~2.7 s |
| Smoke (Render) | `7 passed` | ~26 s |

### Por qué hay menos unitarias que de integración

No es una omisión, es una consecuencia de cómo está escrito el código. De las
doce funciones del proyecto, **solo dos están extraídas como funciones
independientes de la vista**: `hay_traslape()` y `hay_bloqueo()`. Todo el resto de
la lógica de negocio vive *dentro* de funciones-vista que reciben un `request` y
consultan la base, de modo que no se puede ejercitar en aislamiento sin
refactorizar primero.

Por eso las unitarias cubren lo que sí es aislable —las dos reglas de
disponibilidad, la expresión regular del correo, `registrar_log()` y los
contratos de los serializers— y el comportamiento de los endpoints se verifica
por integración. Es una observación sobre la testabilidad del diseño, no un
defecto contra los criterios de aceptación.

**Las 10 historias y sus 32 escenarios de aceptación están cubiertos.**

| Historia | Pruebas | Estado |
|---|---|---|
| HU-001 — Registrar una nueva reserva | `61 passed, 3 xfailed` | ⚠️ DEF-014 |
| HU-002 — Validación automática de disponibilidad | `39 passed` | ✅ Sin defectos |
| HU-003 — Consultar disponibilidad de laboratorios | `18 passed` | ✅ Sin defectos |
| HU-004 — Visualizar el listado global de reservas | `9 passed` | ✅ Sin defectos |
| HU-005 — Consultar una reserva por su identificador | `9 passed` | ✅ Sin defectos |
| HU-006 — Filtrar reservas por criterios | `11 passed` | ✅ Sin defectos |
| HU-007 — Modificar una reserva existente | `14 passed` | ✅ Sin defectos |
| HU-008 — Cancelar una reserva activa | `19 passed` | ✅ Sin defectos |
| HU-009 — Consultar el historial de auditoría | `33 passed` | ⚠️ DEF-009, DEF-013, DEF-015 |
| HU-010 — Gestión automática de estados | `14 passed` | ⚠️ DEF-011 |

Cada historia tiene su propio archivo de unitarias y de integración, así que
`pytest -m hu00X` devuelve exactamente lo que respalda a esa historia.

### Resumen ejecutivo

| Veredicto | Historias |
|---|---|
| ✅ Cumplen por completo | HU-002, HU-003, HU-004, HU-005, HU-006, HU-007, HU-008 |
| ⚠️ Cumplen parcialmente | HU-001, HU-009, HU-010 |
| ❌ Sin implementar | — |

**Las 10 historias cumplen sus criterios de aceptación.** El hallazgo que más
afectaba la cobertura era **DEF-007** (la API no tenía autenticación ni
control de roles), que dejaba inalcanzables tres escenarios de HTTP 403
(HU-007 #4, HU-008 #3, HU-009 #2). Se mitigó sin resolver la causa raíz: cada
endpoint que lo necesitaba (`cancelar`, `modificar`, `GET /api/logs/`) ahora
exige que el cliente declare quién hace la petición (encabezado `X-User-ID`,
campo `UMG_Solicitante_ID`/`UMG_User_ID` en el cuerpo, o `solicitanteId` en
la query, según el endpoint) y verifica el rol o la titularidad de la
reserva antes de autorizar. Es una pseudo-autenticación por convención, no
una sesión ni un token: cualquiera puede seguir declarando ser cualquier
usuario, y el resto de los endpoints (`GET`/`POST /api/reservas/`,
`GET /api/labs/`, `GET /api/usuarios/`, …) sigue sin pedir identidad alguna.
Ver el detalle en DEF-007 más abajo.

### HU-001 — detalle por escenario

| # | Escenario | Regla | Resultado |
|---|---|---|---|
| 1 | Registro exitoso de una reserva | RF-001, RN-008, RN-010 | ✅ Cumple |
| 2 | Campos obligatorios incompletos | RF-001, RN-002, RN-005 | ✅ Cumple |
| 3 | Correo electrónico con formato inválido | RN-009 | ✅ Cumple (adaptado, ver nota) |
| 4 | Fecha anterior a la fecha actual | RN-003 | ✅ Cumple |
| 5 | Duración mayor a la permitida | RN-011 | ✅ Cumple |
| 6 | Horario fuera del rango de operación | RN-012 | ✅ Cumple |

**Nota sobre el escenario 3.** El endpoint no recibe el correo del docente:
recibe `UMG_User_ID` y deriva el correo del usuario ya registrado, tal como
describe el comentario de la GUI ("se captura de manera automática el correo del
usuario que está logeado"). La validación de formato de correo pertenece por
tanto al alta de usuarios, no a este endpoint. La prueba verifica la regla
equivalente que sí aplica aquí: solo un docente existente y activo puede quedar
asociado a una reserva.

### HU-002 — detalle por escenario

| # | Escenario | Regla | Resultado |
|---|---|---|---|
| 1 | Conflicto por reserva existente → HTTP 409 | RF-002, RN-001, RN-004 | ✅ Cumple |
| 2 | Disponibilidad confirmada → HTTP 201 | RF-002, RN-004 | ✅ Cumple |
| 3 | Las canceladas liberan el espacio → HTTP 201 | RN-006, RF-008 | ✅ Cumple |

HU-002 no expone un endpoint propio: es una validación que se dispara dentro de
`POST /api/reservas/`. Las pruebas atacan ese mismo endpoint que HU-001, pero
desde otro ángulo — allí se verifica el formato de los datos de entrada, aquí la
interacción con las reservas que ya existen.

**Cobertura más allá de los criterios.** Se agregaron tres grupos de pruebas que
el documento no contempla pero que afectan el mismo resultado:

- **Bloques adyacentes.** Que `10:00-12:00` se acepte después de un `08:00-10:00`
  es la frontera crítica de la regla: si la comparación usara `<=` en vez de `<`,
  dos clases consecutivas se rechazarían entre sí y el laboratorio quedaría
  infrautilizado. Se verifican los tres casos de borde.
- **Bloqueos administrativos.** RF-002 habla de validar disponibilidad, y el
  sistema la determina con dos reglas: las reservas de otros docentes y las
  condiciones de `UMG_CONDI` (mantenimientos, asuetos). Los criterios solo cubren
  la primera; se prueba también la segunda, incluyendo los asuetos
  institucionales que aplican a todos los laboratorios a la vez.
- **Flujo completo end-to-end.** `test_flujo_completo_reservar_cancelar_y_volver_a_reservar`
  recorre el ciclo de vida entero a través de la API, sin tocar el ORM: reservar
  (201) → otro docente choca (409) → cancelar (200) → el otro docente lo logra
  (201). Es la prueba que demuestra que las tres historias encajan entre sí.

### HU-003 — detalle por escenario

| # | Escenario | Regla | Resultado |
|---|---|---|---|
| 1 | Consulta con laboratorios disponibles | RF-003, RNF-003 | ✅ Cumple |
| 2 | Sin disponibilidad para los criterios | RF-003 | ✅ Cumple |
| 3 | Parámetros de consulta inválidos | RNF-004 | ✅ Cumple |

**DEF-004 está resuelto.** El endpoint existe: `GET /api/labs/disponibles/`
(`labs/views.py:labs_disponibles`), y reutiliza el mismo criterio de traslape
que `POST /api/reservas/` además de excluir laboratorios bloqueados por
`UMG_CONDI`. El archivo conserva `TestAlternativaComponiendoEndpointsExistentes`
— el rodeo de dos llamadas (`GET /api/labs/` + `GET /api/reservas/?fecha=`)
sigue funcionando y queda como referencia de rendimiento frente al endpoint
dedicado, aunque ya no es la única vía.

## Defectos detectados

De los quince defectos originales, **diez ya están resueltos**. Solo DEF-014
sigue respaldado por una prueba `xfail(strict=True)` — el resto de los
abiertos (DEF-009, DEF-011, DEF-013, DEF-015) son cobertura adicional sin
marca `xfail`, según se explica en cada uno. `strict=True` significa que si
alguien corrige el código, la prueba fallará avisando que ya puede quitarse la
marca — así se detectaron los diez resueltos.

| Defecto | Estado |
|---|---|
| DEF-001 | ✅ Resuelto |
| DEF-002 | ✅ Resuelto |
| DEF-003 | ✅ Resuelto |
| DEF-004 | ✅ Resuelto |
| DEF-005 | ✅ Resuelto |
| DEF-006 | ✅ Resuelto |
| DEF-007 | 🟡 Mitigado (no resuelto de raíz) |
| DEF-008 | ✅ Resuelto |
| DEF-009 | 🔴 Abierto |
| DEF-010 | ✅ Resuelto |
| DEF-011 | 🔴 Abierto |
| DEF-012 | ✅ Resuelto |
| DEF-013 | 🔴 Abierto |
| DEF-014 | 🔴 Abierto |
| DEF-015 | 🔴 Abierto |

### DEF-001 — Omitir la hora devuelve HTTP 500 en lugar de 400

**Estado: ✅ Resuelto.** `UMG_Hora_Inicio` y `UMG_Hora_Fin` ya forman parte de
`CAMPOS_REQUERIDOS_RESERVA`; si faltan, `campo_faltante()` devuelve 400 antes
de llegar a la comparación que antes lanzaba el `TypeError`.

**Severidad:** Alta · **Escenario:** HU-001 #2 · **Ubicación:** `reservas/views.py:73`

```python
if hora_inicio >= hora_fin:
```

La comparación se ejecuta antes de comprobar que ambos campos vengan presentes.
Si el cliente omite `UMG_Hora_Inicio` o `UMG_Hora_Fin`, el valor es `None` y
Python lanza:

```
TypeError: '>=' not supported between instances of 'NoneType' and 'str'
```

El resultado es un HTTP 500 en vez del 400 que exige el criterio. Además de
incumplir el contrato, un 500 no le dice al cliente qué campo corrigió mal.

**Corrección sugerida:** validar la presencia de ambos campos antes de compararlos.

### DEF-002 — RN-011 no implementada (duración máxima de 4 horas)

**Estado: ✅ Resuelto.** `reservas_list_create()` calcula la duración del
bloque y rechaza con 400 cualquier reserva de más de 240 minutos.

**Severidad:** Media · **Escenario:** HU-001 #5 · **Ubicación:** `reservas/views.py`

No existe validación de duración del bloque. La API acepta con HTTP 201 reservas
de 6 h e incluso de 15 h continuas. Coincide con el hallazgo ya reportado en la
GUI ("si se exceden las 4 horas continuas el mismo día, se permite hacer la
reserva"), lo que confirma que la regla falta en toda la pila, no solo en el
frontend.

### DEF-003 — RN-012 no implementada (horario hábil 07:00–22:00)

**Estado: ✅ Resuelto.** `reservas_list_create()` rechaza con 400 cualquier
bloque que empiece antes de las 07:00 o termine después de las 22:00.

**Severidad:** Media · **Escenario:** HU-001 #6 · **Ubicación:** `reservas/views.py`

No existe validación del horario de operación. La API acepta bloques de 05:00 a
06:00 o de 23:00 a 23:59. Concuerda con el comentario de la GUI, que ofrece un
rango de 06:00 a 23:30 en lugar del 07:00–22:00 especificado.

### DEF-004 — RF-003 no implementado (consulta de disponibilidad)

**Estado: ✅ Resuelto.** `GET /api/labs/disponibles/` (`labs/views.py:labs_disponibles`)
implementa exactamente lo sugerido más abajo: recibe `fecha`, `hora_inicio` y
`hora_fin`, reutiliza la misma condición de traslape que `POST /api/reservas/`
y además excluye laboratorios bloqueados por `UMG_CONDI` (algo que ni la
alternativa client-side cubría).

**Severidad:** Alta · **Escenarios:** HU-003 #1, #2 y #3 · **Ubicación:** `labs/urls.py`

La API no expone ninguna ruta que responda "qué laboratorios están libres en tal
fecha y horario". Las rutas existentes son:

```
GET  /api/labs/            catálogo completo, sin filtros de ocupación
PUT  /api/labs/<pk>/
GET  /api/reservas/        filtra por labId, fecha y userId — no por hora
```

Coincide con el documento de historias, que anota "NO HAY" en la columna de
endpoints de HU-003.

**Impacto.** No es un hueco de datos sino de conveniencia y rendimiento: la
información es deducible componiendo dos llamadas, y así lo verifica
`TestAlternativaComponiendoEndpointsExistentes`. Pero el costo lo paga cada
cliente:

- Descarga el catálogo completo de laboratorios y **todas** las reservas del día,
  aunque solo le interese una franja de dos horas.
- Reimplementa la lógica de traslape en el frontend — la misma que el backend ya
  tiene en `hay_traslape()`. Dos implementaciones de una regla de negocio que
  pueden divergir.
- No aplica los bloqueos de `UMG_CONDI`: un laboratorio en mantenimiento aparece
  como libre en la GUI y solo se descubre al recibir el 409 al reservar.

Estos tres párrafos describen el hallazgo original; el endpoint ya se
implementó siguiendo esa misma recomendación (ver "Estado" arriba).

### DEF-005 — RF-007 no implementado (modificar una reserva)

**Estado: ✅ Resuelto.** `PUT /api/reservas/{id}/modificar/`
(`reservas/views.py:reservas_modificar`) reutiliza `hay_traslape(..., excluir_id=pk)`
tal como sugería la corrección original, revalida RN-006 (actividad no
iniciada) y RN-013 (solo el creador o un Admin puede modificar). La ruta de
detalle (`<int:pk>/`) sigue siendo de solo lectura a propósito: modificar vive
en su propia ruta.

**Severidad:** Alta · **Escenarios:** HU-007 #1 a #4 · **Ubicación:** `reservas/urls.py`

No existe endpoint de modificación. Las rutas declaradas son `''` (GET, POST),
`'<int:pk>/'` (solo GET) y `'<int:pk>/cancelar/'` (PATCH). Un `PUT` o `PATCH`
sobre el detalle responde **405 Method Not Allowed**.

**Impacto.** El único rodeo posible es cancelar y recrear, y eso rompe una
promesa del propio documento:

- **RN-008 dice que el identificador es inmutable**, pero "modificar" por este
  camino genera uno nuevo. Cualquier referencia externa al ID anterior queda
  rota.
- Cada corrección de un dato deja una reserva cancelada que, para HU-004 y
  HU-009, es ruido indistinguible de una cancelación real.

`TestAlternativaCancelarYRecrear` se conserva y sigue en verde: el rodeo
todavía funciona, aunque ya no es necesario.

### DEF-006 — RN-006 no implementada (cancelar una actividad ya iniciada)

**Estado: ✅ Resuelto.** `reservas_cancelar()` compara la fecha/hora de inicio
de la reserva contra el momento actual y responde 409 si la actividad ya
comenzó, antes de tocar el estado.

**Severidad:** Media · **Escenario:** HU-008 #2 · **Ubicación:** `reservas/views.py:126-142`

`reservas_cancelar()` solo comprueba que la reserva no esté ya cancelada. No
compara la fecha ni la hora de inicio contra el momento actual, así que una
reserva del año pasado puede cancelarse igual que una futura. Coincide con el
hallazgo ya reportado en la GUI ("se permite cancelar una reserva cuando ya
transcurrió").

### DEF-007 — La API no tiene autenticación ni control de roles

**Estado: 🟡 Mitigado, no resuelto de raíz.** Los tres escenarios de HTTP 403
que este defecto bloqueaba ya pasan (HU-007 #4, HU-008 #3, HU-009 #2), pero no
porque se haya agregado autenticación real: cada endpoint que necesitaba
autorizar una acción implementó su propia verificación puntual.

- `reservas_cancelar()` y `reservas_modificar()` leen la identidad del
  solicitante de `X-User-ID` (encabezado), `UMG_Solicitante_ID` (cuerpo) o
  `solicitanteId` (query string) — el primero que venga presente — y exigen
  que sea el creador de la reserva o tenga rol `Admin`; si no, 403. Si no se
  envía ninguno, 400.
- `logs_list()` exige `UMG_User_ID` por query param y el rol `Admin`; si no,
  403.

Es una **pseudo-autenticación por convención**: el backend confía en el ID que
el cliente declara, sin verificarlo contra ninguna sesión ni token. Sigue sin
existir `DEFAULT_AUTHENTICATION_CLASSES` ni `DEFAULT_PERMISSION_CLASSES` en

```python
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'umg_config.schema.DynamicAutoSchema',
}
```

y `POST /api/auth/login/` sigue sin emitir token ni sesión. **El resto de los
endpoints permanece completamente abierto**: `GET`/`POST /api/reservas/`,
`GET /api/labs/`, `GET /api/labs/disponibles/` y `GET /api/usuarios/` no piden
ninguna identidad. Cualquiera que conozca (o adivine) un `UMG_ID` puede
declarar ser ese usuario ante `cancelar`, `modificar` o `logs`.

**Nota adicional de seguridad, fuera de los criterios de aceptación.** Las
contraseñas se guardan y comparan en texto plano (`usuarios/views.py:45-51` y
`74-76`). Combinado con la ausencia de autenticación real, cualquiera con
acceso a la API puede listar usuarios vía `GET /api/usuarios/` para obtener
los `UMG_ID` que necesita para suplantar a alguien ante los endpoints ya
protegidos. No es parte de ninguna historia, pero conviene que quede
registrado.

**Corrección de fondo pendiente:** sustituir esta convención por sesión o
token (p. ej. `TokenAuthentication` de DRF) y `permission_classes` reales por
vista, en vez de que cada vista reimplemente su propia verificación de
identidad leyendo campos del request.

### DEF-008 — La cancelación no registra al usuario responsable

**Estado: ✅ Resuelto.** `reservas_cancelar()` ahora calcula `solicitante` (la
misma verificación de identidad que introdujo la mitigación de DEF-007) y se
lo pasa a `registrar_log(solicitante.umg_id, ...)`. `reservas_modificar()`
hace lo mismo para `MODIFICAR_RESERVA`.

**Severidad:** Media · **Escenario:** HU-009 #1 · **Ubicación:** `reservas/views.py:140`

```python
registrar_log(None, "CANCELAR_RESERVA", "Reservas", msg_log)
                ^^^^
```

La creación sí registra al docente (`registrar_log(user_id, ...)`), pero la
cancelación pasa `None` porque, sin autenticación (DEF-007), la vista no tiene a
quién atribuir la acción. El criterio exige registrar "el usuario responsable, la
fecha, la hora y los campos alterados": el historial queda con el *qué* pero sin
el *quién*, que es justamente lo que una auditoría necesita.

### DEF-009 — El historial solo expone los últimos 100 registros

**Estado: 🔴 Abierto.** Sigue sin haber paginación ni filtros de rango; el
`[:100]` fijo continúa igual.

**Severidad:** Media · **Escenario:** HU-009 #1 · **Ubicación:** `logs/views.py:10`

```python
logs = LogEntry.objects.all().order_by('-umg_fecha_registro')[:100]
```

El recorte es fijo y no hay paginación ni filtros por rango de fechas. Los
registros más antiguos **no son alcanzables por ningún medio de la API**. Para
una historia cuyo propósito es "respaldar las auditorías", significa que el
historial es consultable solo durante una ventana reciente y arbitraria.

### DEF-010 — El estado "Finalizada" no existe

**Estado: ✅ Resuelto**, aunque no por la vía sugerida originalmente.
`finalizar_vencidas()` (`reservas/views.py`) persiste el estado `'F'` — en vez
de calcularlo en el serializer al responder — y se ejecuta "on read/write" al
inicio de `GET /api/reservas/`, `GET /api/reservas/{id}/` y
`PATCH /api/reservas/{id}/cancelar/`.

**Severidad:** Media · **Escenario:** HU-010 #3 · **Ubicación:** `reservas/views.py`

```python
umg_estado = models.CharField(max_length=1, default='R')  # R = Reservada, C = Cancelada
```

El modelo solo contemplaba `'R'` y `'C'`. No había tarea programada, señal ni
cálculo derivado que promoviera una reserva vencida a "Finalizada". Una reserva
del año pasado seguía figurando como `'R'` (Activa) indefinidamente, lo que
distorsionaba el listado de HU-004 y cualquier reporte de ocupación.

### DEF-011 — `umg_estado` no restringe su dominio de valores

**Estado: 🔴 Abierto.** El campo sigue sin `choices` ni constraint, ahora con
tres valores válidos (`'R'`, `'C'`, `'F'`) que tampoco están reforzados a nivel
de base de datos o modelo.

**Severidad:** Baja · **Escenario:** cobertura adicional de HU-010 · **Ubicación:** `reservas/models.py:13`

`CharField(max_length=1)` sin `choices` ni constraint en base de datos: acepta
cualquier letra. La suite verifica que se puede guardar `'X'` sin que nada lo
impida.

**Por qué importa:** `hay_traslape()` filtra por `umg_estado='R'`, así que una
reserva con estado corrupto **deja de bloquear el laboratorio** silenciosamente.
El espacio aparece libre y se puede sobre-reservar.

### DEF-012 — La hora se devuelve en dos formatos distintos

**Estado: ✅ Resuelto.** `reservas_list_create()` y `reservas_modificar()`
parsean `UMG_Hora_Inicio`/`UMG_Hora_Fin` a `datetime.time` (aceptando tanto
`HH:MM` como `HH:MM:SS`) antes de crear o guardar la reserva, tal como sugería
la corrección original. El mismo campo ya viaja consistente entre el `POST`,
el `PUT` y los `GET`.

**Severidad:** Baja · **Escenario:** HU-001 #1 · **Ubicación:** `reservas/views.py`

El mismo campo viaja con formato distinto según el endpoint:

```
POST /api/reservas/       →  "UMG_Hora_Inicio": "14:00"
GET  /api/reservas/{id}/  →  "UMG_Hora_Inicio": "14:00:00"
GET  /api/reservas/       →  "UMG_Hora_Inicio": "14:00:00"
```

La vista pasa el string crudo a `Reserva.objects.create()`. El objeto en memoria
conserva el string tal cual, y el serializer lo repite sin normalizar; releído de
la base es un objeto `time` y se serializa como `HH:MM:SS`.

**Por qué importaba:** un cliente que parseara la respuesta del POST con el
mismo código que usa para el GET fallaba. Es el tipo de inconsistencia que no
molesta hasta que alguien compara ambas respuestas.

### DEF-013 — El historial no tiene criterio de desempate en el orden

**Estado: 🔴 Abierto.** Sin cambios.

**Severidad:** Baja · **Escenario:** cobertura adicional de HU-009 · **Ubicación:** `logs/views.py:10`

El ordenamiento es solo por `-umg_fecha_registro`, sin desempatar por
identificador. Varias operaciones registradas dentro del mismo instante quedan en
orden indeterminado, de modo que no siempre se puede reconstruir la secuencia
exacta de los hechos. No se acompaña de una prueba porque el comportamiento es no
determinista: una prueba que lo afirmara sería intermitente.

### DEF-014 — La validación de correo no exige el dominio institucional

**Estado: 🔴 Abierto.** Es el único defecto que hoy sigue respaldado por un
`xfail(strict=True)` en la suite (`pytest -m hu001`).

**Severidad:** Baja · **Escenario:** HU-001 #3 · **Ubicación:** `usuarios/views.py:10`

```python
EMAIL_REGEX = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
```

La historia habla de "correo institucional válido", pero la expresión solo
comprueba la forma genérica de un correo. `jperez@gmail.com` pasa la validación,
de modo que se puede dar de alta un docente con una cuenta personal.

Las pruebas unitarias de `TestFormatoDelCorreoInstitucional` verifican que los
ocho formatos inválidos sí se rechazan correctamente; el `xfail` cubre solo el
caso del dominio.

### DEF-015 — `registrar_log()` no cumple su promesa dentro de una transacción

**Estado: 🔴 Abierto.** `logs/utils.py` no cambió; sigue siendo un `try/except`
simple alrededor de `LogEntry.objects.create()`.

**Severidad:** Media (latente) · **Escenario:** HU-009 #1 · **Ubicación:** `logs/utils.py:4-17`

El docstring promete:

> *Nunca lanza excepción: si falla el log, no debe interrumpir la operación principal.*

Esa garantía no se sostiene dentro de una transacción. Django crea las claves
foráneas en PostgreSQL como `DEFERRABLE INITIALLY DEFERRED`, así que una
violación de FK **no se detecta en el `INSERT` sino en el `COMMIT`**. Para
entonces `registrar_log()` ya retornó y su `except` no puede atrapar nada: la
excepción estalla fuera de la función y aborta toda la operación — exactamente lo
contrario de lo que buscaba proteger.

Comprobado en `test_hu009_reglas.py`:

| Contexto | Comportamiento |
|---|---|
| Autocommit (como hoy en producción) | Traga el error, se pierde el registro, la operación continúa ✅ |
| Dentro de `transaction.atomic()` | `IntegrityError` al confirmar, la operación completa se revierte 💥 |

**Por qué importa aunque hoy no falle.** Ninguna vista usa `transaction.atomic()`
ni `ATOMIC_REQUESTS`, así que el problema está latente. Se vuelve real en cuanto
alguien envuelva la creación de una reserva en una transacción — que es
justamente lo natural al querer hacerla atómica, y una mejora que este mismo
informe recomendaría.

**Corrección sugerida:** capturar la excepción dentro de un savepoint
(`with transaction.atomic(): ...` anidado dentro del `try`), de modo que el
rollback quede acotado al `INSERT` de la bitácora y no contamine la transacción
externa.

## Integración continua

`.github/workflows/pruebas.yml` avanza en tres etapas encadenadas. Cada una solo
arranca si la anterior terminó en verde:

```
1 - Unitarias  ──▶  2 - Integración  ──▶  3 - Smoke (manual)
  58 + 3 xfail          169 pruebas          7 pruebas
   ~1.7 s              ~2.7 s                ~26 s
```

El orden va de lo más barato y específico a lo más caro y amplio: si una regla de
negocio está rota, no tiene sentido gastar tiempo levantando la API completa ni
mucho menos golpear el servicio desplegado.

Cada etapa publica sus propios artifacts:

| Etapa | Artifacts |
|---|---|
| Unitarias | `junit-unitarias.xml`, `reporte-unitarias.html` |
| Integración | `junit-integracion.xml`, `reporte-integracion.html`, `cobertura/` |
| Smoke | `junit-smoke.xml`, `reporte-smoke.html` |

La cobertura se mide en la etapa de integración, que es la que ejercita el código
de punta a punta.

La etapa de smoke se dispara a mano desde *Actions → Run workflow* marcando la
casilla. No corre en cada push porque un push no cambia el código desplegado, y
porque cada corrida implica el arranque en frío de Render. Para que corra
siempre, basta con borrar la condición `if` de ese job.

**La base de datos se levanta con el mismo `docker-compose.test.yml` que usás en
tu máquina**.

**Ejecuciones concurrentes.** El workflow declara `concurrency` con
`cancel-in-progress: true`, agrupado por rama. Si hacés dos pushes seguidos a la
misma rama, la corrida del commit anterior se cancela y solo sobrevive la del más
reciente. Ramas distintas nunca se cancelan entre sí.

Los smoke tests se disparan manualmente desde *Actions → Run workflow*, marcando
la casilla correspondiente. Requieren definir la variable `SMOKE_BASE_URL` en
*Settings → Secrets and variables → Actions → Variables*.

## Cómo agregar las siguientes historias

1. Crear `tests/integration/test_hu00X_<nombre>.py`.
2. Una clase por escenario, nombrada `TestEscenarioNDescripcion`.
3. Copiar el Gherkin del documento de criterios al docstring de la clase.
4. Marcar el módulo con `pytestmark = [pytest.mark.integration, pytest.mark.hu00X, pytest.mark.django_db]`.
5. Reutilizar las fixtures de `conftest.py`; agregar ahí las nuevas que sean
   compartidas por más de un archivo.

Las fixtures `crear_reserva`, `otro_docente`, `otro_lab`, `rol_admin` y
`administrador` ya se usan en HU-002, HU-007, HU-008, HU-009 y HU-010 — la
fábrica de reservas por ORM y un segundo docente/laboratorio/administrador
para armar conflictos, permisos y bloqueos sin depender del endpoint bajo
prueba.
