"""
HU-003 - Consultar disponibilidad de laboratorios | PRUEBAS DE INTEGRACION

    "Como docente, quiero consultar los laboratorios disponibles filtrando por
     fecha y horario, para elegir el espacio adecuado antes de registrar mi
     reserva."

Endpoint bajo prueba: GET /api/labs/disponibles/ (labs/views.py:labs_disponibles)

DEF-004 (RF-003 no implementado) esta resuelto: el endpoint ya existe y cruza
GET /api/labs/ con las reservas y bloqueos del dia para responder que
laboratorios estan libres en una fecha y horario dados.

La clase TestAlternativaComponiendoEndpointsExistentes se conserva porque sigue
siendo cierta: documenta el rodeo de dos llamadas que la GUI puede usar como
alternativa, y sirve de referencia de rendimiento frente al endpoint dedicado.
"""

import time
from datetime import timedelta

import pytest

from labs.models import Lab
from reservas.models import Reserva

pytestmark = [pytest.mark.integration, pytest.mark.hu003, pytest.mark.django_db]


RUTA_PROPUESTA = '/api/labs/disponibles/'


# --------------------------------------------------------------------------- #
# Escenario 1 - Consulta con laboratorios disponibles                          #
# --------------------------------------------------------------------------- #

class TestEscenario1ConsultaConLaboratoriosDisponibles:
    """
    Dado    que el docente indica una fecha y un horario validos
    Cuando  consulta la disponibilidad de laboratorios
    Entonces el sistema retorna la lista de laboratorios libres en formato JSON,
            con HTTP 200 y en un tiempo inferior a 1 segundo.

    Verifica: RF-003, RNF-003
    """

    def test_responde_http_200_con_la_lista_de_libres(
        self, api, docente, lab, otro_lab, fecha_futura, crear_reserva
    ):
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        respuesta = api.get(
            RUTA_PROPUESTA,
            {
                'fecha': fecha_futura.isoformat(),
                'hora_inicio': '08:00',
                'hora_fin': '10:00',
            },
        )

        assert respuesta.status_code == 200
        nombres = [item['UMG_Nombre'] for item in respuesta.data]
        assert otro_lab.umg_nombre in nombres
        assert lab.umg_nombre not in nombres

    def test_responde_en_menos_de_un_segundo(self, api, fecha_futura):
        """RNF-003."""
        inicio = time.monotonic()
        respuesta = api.get(
            RUTA_PROPUESTA,
            {
                'fecha': fecha_futura.isoformat(),
                'hora_inicio': '08:00',
                'hora_fin': '10:00',
            },
        )
        transcurrido = time.monotonic() - inicio

        assert respuesta.status_code == 200
        assert transcurrido < 1.0


# --------------------------------------------------------------------------- #
# Escenario 2 - Sin disponibilidad para los criterios indicados                #
# --------------------------------------------------------------------------- #

class TestEscenario2SinDisponibilidad:
    """
    Dado    que todos los laboratorios se encuentran reservados para la fecha y
            horario consultados
    Cuando  el docente consulta la disponibilidad
    Entonces el sistema responde con HTTP 200 y una lista vacia, sin tratarlo
            como un error.

    Verifica: RF-003
    """

    def test_devuelve_lista_vacia_y_no_un_error(
        self, api, docente, lab, otro_lab, fecha_futura, crear_reserva
    ):
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')
        crear_reserva(docente, otro_lab, fecha_futura, '08:00', '10:00')

        respuesta = api.get(
            RUTA_PROPUESTA,
            {
                'fecha': fecha_futura.isoformat(),
                'hora_inicio': '08:00',
                'hora_fin': '10:00',
            },
        )

        assert respuesta.status_code == 200
        assert respuesta.data == []


# --------------------------------------------------------------------------- #
# Escenario 3 - Parametros de consulta invalidos                               #
# --------------------------------------------------------------------------- #

class TestEscenario3ParametrosInvalidos:
    """
    Dado    que el docente envia una fecha con formato incorrecto o un horario
            inexistente
    Cuando  ejecuta la consulta de disponibilidad
    Entonces el sistema responde con HTTP 400 y un mensaje que describe el
            parametro invalido.

    Verifica: RNF-004
    """

    @pytest.mark.parametrize(
        'params, caso',
        [
            ({'fecha': '31-12-2026', 'hora_inicio': '08:00', 'hora_fin': '10:00'},
             'fecha en formato dd-mm-yyyy'),
            ({'fecha': 'manana', 'hora_inicio': '08:00', 'hora_fin': '10:00'},
             'fecha no parseable'),
            ({'fecha': '2026-12-31', 'hora_inicio': '25:00', 'hora_fin': '26:00'},
             'hora inexistente'),
            ({'fecha': '2026-12-31', 'hora_inicio': '10:00', 'hora_fin': '08:00'},
             'rango invertido'),
            ({'hora_inicio': '08:00', 'hora_fin': '10:00'},
             'falta la fecha'),
        ],
    )
    def test_rechaza_parametros_invalidos_con_400(self, api, params, caso):
        respuesta = api.get(RUTA_PROPUESTA, params)

        assert respuesta.status_code == 400, f'No se rechazo: {caso}'
        assert 'mensaje' in respuesta.data


# --------------------------------------------------------------------------- #
# 3. La alternativa disponible hoy                                             #
# --------------------------------------------------------------------------- #

class TestAlternativaComponiendoEndpointsExistentes:
    """
    Sin endpoint de disponibilidad, un cliente puede deducirla con dos llamadas:

        GET /api/labs/                     -> catalogo completo
        GET /api/reservas/?fecha=YYYY-MM-DD -> reservas de ese dia

    y luego descartar en el cliente los laboratorios ocupados. Estas pruebas
    confirman que la informacion necesaria si esta expuesta, y miden lo que
    cuesta obtenerla asi.
    """

    @staticmethod
    def _labs_libres(api, fecha, hora_inicio, hora_fin):
        """Reproduce el calculo que hoy le toca hacer al cliente."""
        labs = api.get('/api/labs/').data
        reservas = api.get('/api/reservas/', {'fecha': fecha.isoformat()}).data

        ocupados = {
            r['UMG_Lab_ID']
            for r in reservas
            if r['UMG_Estado'] == 'R'
            and r['UMG_Hora_Inicio'] < hora_fin
            and r['UMG_Hora_Fin'] > hora_inicio
        }
        return [l for l in labs if l['UMG_ID'] not in ocupados]

    def test_la_composicion_identifica_los_laboratorios_libres(
        self, api, docente, lab, otro_lab, fecha_futura, crear_reserva
    ):
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        libres = self._labs_libres(api, fecha_futura, '08:00:00', '10:00:00')

        nombres = [l['UMG_Nombre'] for l in libres]
        assert otro_lab.umg_nombre in nombres
        assert lab.umg_nombre not in nombres

    def test_una_reserva_cancelada_no_ocupa_el_laboratorio(
        self, api, docente, lab, otro_lab, fecha_futura, crear_reserva
    ):
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00', estado='C')

        libres = self._labs_libres(api, fecha_futura, '08:00:00', '10:00:00')

        assert len(libres) == 2

    def test_devuelve_vacio_cuando_todo_esta_ocupado(
        self, api, docente, lab, otro_lab, fecha_futura, crear_reserva
    ):
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')
        crear_reserva(docente, otro_lab, fecha_futura, '08:00', '10:00')

        libres = self._labs_libres(api, fecha_futura, '08:00:00', '10:00:00')

        assert libres == []

    def test_el_endpoint_de_reservas_no_admite_filtro_por_horario(
        self, api, docente, lab, fecha_futura, crear_reserva
    ):
        """
        Limitacion concreta que HU-003 vendria a resolver: GET /api/reservas/
        filtra por labId, fecha y userId, pero no por hora. El cliente recibe
        todas las reservas del dia y tiene que descartar el resto por su cuenta.
        """
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')
        crear_reserva(docente, lab, fecha_futura, '14:00', '16:00')

        respuesta = api.get(
            '/api/reservas/',
            {
                'fecha': fecha_futura.isoformat(),
                'hora_inicio': '08:00',
                'hora_fin': '10:00',
            },
        )

        assert respuesta.status_code == 200
        assert len(respuesta.data) == 2, (
            'GET /api/reservas/ ya filtra por horario: actualiza esta prueba.'
        )

    def test_la_consulta_compuesta_responde_en_menos_de_un_segundo(
        self, api, docente, fecha_futura
    ):
        """
        RNF-003 sobre la alternativa actual, con un volumen mas realista que el
        de las demas pruebas: 15 laboratorios y 150 reservas repartidas en tres
        dias.
        """
        labs = [
            Lab.objects.create(umg_nombre=f'Lab Carga {i:02d}') for i in range(15)
        ]
        Reserva.objects.bulk_create([
            Reserva(
                umg_user=docente,
                umg_lab=labs[i % len(labs)],
                umg_fecha_reserva=fecha_futura + timedelta(days=i % 3),
                umg_hora_inicio='08:00',
                umg_hora_fin='10:00',
                umg_motivo=f'Carga {i}',
                umg_estado='R',
            )
            for i in range(150)
        ])

        inicio = time.monotonic()
        self._labs_libres(api, fecha_futura, '08:00:00', '10:00:00')
        transcurrido = time.monotonic() - inicio

        assert transcurrido < 1.0, f'La consulta compuesta tardo {transcurrido:.2f}s'
