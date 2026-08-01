"""
SMOKE TESTS - Ambiente desplegado (Render)

Verifican que el despliegue real responde correctamente. Son un complemento de
la suite unit/integracion, no un reemplazo:

    Suite unit + integracion  ->  Postgres efimero. Crea y borra datos.
    Smoke tests (este archivo) ->  API real en Render. SOLO LECTURA.

NOTA: aqui solo se emiten peticiones GET. Ninguna prueba de
este archivo puede crear, modificar ni eliminar informacion en produccion.

Ejecucion:
    pytest -m smoke

La URL sale de SMOKE_BASE_URL, resuelta con python-decouple igual que el resto
del proyecto. Decouple da prioridad a las variables de entorno del sistema sobre
el archivo .env, asi que la misma linea de codigo sirve en los dos ambientes:

    Local  ->  se define en .env
    CI     ->  se define como variable del workflow de GitHub Actions

Si SMOKE_BASE_URL no esta definida, todas las pruebas se omiten (skip), de modo
que la suite normal nunca se ve afectada.
"""

import time

import pytest
import requests
from decouple import config

pytestmark = pytest.mark.smoke

BASE_URL = config('SMOKE_BASE_URL', default='').rstrip('/')

# Tiempo maximo por peticion, una vez que el servicio ya esta despierto.
TIMEOUT = 30

# Render suspende los servicios del plan gratuito tras un rato sin trafico. La
# primera peticion dispara el arranque en frio del contenedor, que puede tardar
# bastante mas que una peticion normal. Se utiliza para prevenir que la prueba falle por una causa ajena a la API.
PRESUPUESTO_ARRANQUE_EN_FRIO = 240

requiere_url = pytest.mark.skipif(
    not BASE_URL,
    reason='Define SMOKE_BASE_URL con la URL publica del servicio en Render.',
)


@pytest.fixture(scope='session')
def sesion():
    """
    Sesion HTTP compartida por todas las pruebas, ya con el servicio despierto.

    Se reintenta hasta agotar PRESUPUESTO_ARRANQUE_EN_FRIO. Si al final no
    responde, se aborta con un mensaje claro en vez de dejar que cada prueba
    falle por timeout una tras otra.
    """
    with requests.Session() as s:
        s.headers.update({'Accept': 'application/json'})

        limite = time.monotonic() + PRESUPUESTO_ARRANQUE_EN_FRIO
        ultimo_error = None

        while time.monotonic() < limite:
            try:
                if s.get(f'{BASE_URL}/api/labs/', timeout=TIMEOUT).status_code == 200:
                    break
            except requests.RequestException as exc:
                ultimo_error = exc
        else:
            pytest.fail(
                f'{BASE_URL} no respondio en {PRESUPUESTO_ARRANQUE_EN_FRIO}s. '
                f'Ultimo error: {ultimo_error}'
            )

        yield s


def _get(sesion, ruta):
    return sesion.get(f'{BASE_URL}{ruta}', timeout=TIMEOUT)


# --------------------------------------------------------------------------- #
# Disponibilidad del servicio                                                  #
# --------------------------------------------------------------------------- #

@requiere_url
class TestDisponibilidadDelServicio:

    def test_el_esquema_openapi_responde(self, sesion):
        """Si /api/schema/ responde, Django y drf-spectacular estan arriba."""
        respuesta = _get(sesion, '/api/schema/')

        assert respuesta.status_code == 200

    def test_el_endpoint_de_laboratorios_responde(self, sesion):
        respuesta = _get(sesion, '/api/labs/')

        assert respuesta.status_code == 200
        assert isinstance(respuesta.json(), list)

    def test_el_endpoint_de_reservas_responde(self, sesion):
        """Valida de paso que la conexion a PostgreSQL esta viva."""
        respuesta = _get(sesion, '/api/reservas/')

        assert respuesta.status_code == 200
        assert isinstance(respuesta.json(), list)


# --------------------------------------------------------------------------- #
# Contrato de la respuesta                                                     #
# --------------------------------------------------------------------------- #

@requiere_url
class TestContratoDeLaApi:

    def test_las_reservas_conservan_el_contrato_de_campos(self, sesion):
        """
        Si hay reservas registradas, cada una debe traer los campos que el
        cliente espera. Con la base vacia la prueba se omite.
        """
        reservas = _get(sesion, '/api/reservas/').json()

        if not reservas:
            pytest.skip('No hay reservas registradas en el ambiente desplegado.')

        campos_esperados = {
            'UMG_ID', 'UMG_User_ID', 'UMG_Docente_Nombre', 'UMG_Docente_Correo',
            'UMG_Lab_ID', 'UMG_Lab_Nombre', 'UMG_Fecha_Reserva', 'UMG_Hora_Inicio',
            'UMG_Hora_Fin', 'UMG_Motivo', 'UMG_Estado', 'UMG_Fecha_Registro',
        }
        assert campos_esperados.issubset(set(reservas[0].keys()))

    def test_los_estados_persistidos_son_validos(self, sesion):
        """RN-010: en base de datos solo deben existir 'R', 'C' y 'F'."""
        reservas = _get(sesion, '/api/reservas/').json()

        if not reservas:
            pytest.skip('No hay reservas registradas en el ambiente desplegado.')

        estados = {r['UMG_Estado'] for r in reservas}
        assert estados.issubset({'R', 'C', 'F'}), f'Estados inesperados: {estados}'


# --------------------------------------------------------------------------- #
# Manejo de errores                                                            #
# --------------------------------------------------------------------------- #

@requiere_url
class TestManejoDeErrores:

    def test_una_reserva_inexistente_devuelve_404_semantico(self, sesion):
        """
        RNF-005: mensaje de error semantico, sin exponer detalles internos.
        Enlaza con HU-005 escenario 2.
        """
        respuesta = _get(sesion, '/api/reservas/999999999/')

        assert respuesta.status_code == 404
        assert 'mensaje' in respuesta.json()

    def test_no_se_filtra_el_traceback_de_django(self, sesion):
        """DEBUG debe estar apagado en produccion."""
        respuesta = _get(sesion, '/api/reservas/999999999/')

        assert 'Traceback' not in respuesta.text
        assert 'DJANGO_SETTINGS_MODULE' not in respuesta.text
