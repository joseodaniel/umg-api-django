"""
HU-008 - Cancelar una reserva activa | PRUEBAS DE INTEGRACION

    "Como docente, quiero cancelar una de mis reservas activas antes de la hora
     de inicio, para liberar el laboratorio cuando la actividad ya no se
     realizara."

Endpoint bajo prueba: PATCH /api/reservas/{id}/cancelar/
"""

import pytest
from django.urls import reverse

from logs.models import LogEntry
from reservas.models import Reserva

pytestmark = [pytest.mark.integration, pytest.mark.hu008, pytest.mark.django_db]


def url_cancelar(pk):
    return reverse('reservas-cancelar', args=[pk])


# --------------------------------------------------------------------------- #
# Escenario 1 - Cancelacion valida por el creador                              #
# --------------------------------------------------------------------------- #

class TestEscenario1CancelacionValida:
    """
    Dado    que la reserva esta en estado "Activa" y la hora de inicio aun no ha
            llegado
    Cuando  el docente creador solicita la cancelacion
    Entonces el sistema cambia el estado a "Cancelada", libera inmediatamente el
            laboratorio y responde con HTTP 200.

    Verifica: RF-008, RN-006
    """

    def test_responde_http_200(self, api, docente, lab, fecha_futura, crear_reserva):
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        respuesta = api.patch(url_cancelar(reserva.umg_id), format='json')

        assert respuesta.status_code == 200

    def test_cambia_el_estado_a_cancelada(
        self, api, docente, lab, fecha_futura, crear_reserva
    ):
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        api.patch(url_cancelar(reserva.umg_id), format='json')

        reserva.refresh_from_db()
        assert reserva.umg_estado == 'C'

    def test_libera_inmediatamente_el_laboratorio(
        self, api, url_reservas, payload_valido, docente, otro_docente, lab,
        fecha_futura, crear_reserva
    ):
        """
        "Libera inmediatamente" es verificable: el mismo bloque debe poder
        reservarse enseguida, sin ningun proceso intermedio.
        """
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')
        payload_valido['UMG_User_ID'] = otro_docente.umg_id

        assert api.post(url_reservas, payload_valido, format='json').status_code == 409

        api.patch(url_cancelar(reserva.umg_id), format='json')

        assert api.post(url_reservas, payload_valido, format='json').status_code == 201

    def test_conserva_el_registro_en_lugar_de_borrarlo(
        self, api, docente, lab, fecha_futura, crear_reserva
    ):
        """Cancelar no es eliminar: el historial debe preservarse."""
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        api.patch(url_cancelar(reserva.umg_id), format='json')

        assert Reserva.objects.filter(pk=reserva.umg_id).exists()
        assert Reserva.objects.count() == 1

    def test_registra_la_cancelacion_en_la_bitacora(
        self, api, docente, lab, fecha_futura, crear_reserva
    ):
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        api.patch(url_cancelar(reserva.umg_id), format='json')

        registro = LogEntry.objects.filter(umg_accion='CANCELAR_RESERVA').first()
        assert registro is not None
        assert str(reserva.umg_id) in registro.umg_descripcion

    def test_cancelar_una_reserva_inexistente_devuelve_404(self, api, db):
        respuesta = api.patch(url_cancelar(999999), format='json')

        assert respuesta.status_code == 404

    def test_cancelar_dos_veces_devuelve_409(
        self, api, docente, lab, fecha_futura, crear_reserva
    ):
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        assert api.patch(url_cancelar(reserva.umg_id), format='json').status_code == 200
        assert api.patch(url_cancelar(reserva.umg_id), format='json').status_code == 409


# --------------------------------------------------------------------------- #
# Escenario 2 - Cancelacion posterior al inicio de la actividad                #
# --------------------------------------------------------------------------- #

class TestEscenario2CancelacionTardia:
    """
    Dado    que la hora de inicio de la actividad ya transcurrio
    Cuando  se solicita la cancelacion de la reserva
    Entonces el sistema rechaza la operacion con un mensaje de error y la
            reserva no queda cancelada.

    Verifica: RN-006
    """

    def test_rechaza_la_cancelacion_de_una_actividad_pasada(
        self, api, docente, lab, fecha_pasada, crear_reserva
    ):
        reserva = crear_reserva(docente, lab, fecha_pasada, '08:00', '10:00')

        respuesta = api.patch(url_cancelar(reserva.umg_id), format='json')

        assert respuesta.status_code in (400, 409)

    def test_el_estado_no_queda_cancelado(
        self, api, docente, lab, fecha_pasada, crear_reserva
    ):
        """
        No se afirma que el estado se quede en 'R': reservas_cancelar()
        tambien ejecuta finalizar_vencidas() (HU-010), que promueve la
        reserva vencida a 'F' como efecto colateral independiente del
        intento de cancelacion. Lo que RN-006 exige es que ese intento no
        la deje 'C'.
        """
        reserva = crear_reserva(docente, lab, fecha_pasada, '08:00', '10:00')

        api.patch(url_cancelar(reserva.umg_id), format='json')

        reserva.refresh_from_db()
        assert reserva.umg_estado != 'C'


# --------------------------------------------------------------------------- #
# Escenario 3 - Cancelacion por un usuario no autorizado                       #
# --------------------------------------------------------------------------- #

class TestEscenario3UsuarioNoAutorizado:
    """
    Dado    que el solicitante no es el docente creador de la reserva ni posee
            el rol de Administrador
    Cuando  intenta cancelar la reserva
    Entonces el sistema rechaza la operacion con HTTP 403 (Forbidden).

    Verifica: RN-013
    """

    pytestmark = pytest.mark.xfail(
        strict=True,
        reason=(
            'DEF-007: la API no tiene autenticacion ni control de roles. '
            'reservas_cancelar() no recibe ni consulta la identidad del '
            'solicitante, asi que cualquiera puede cancelar cualquier reserva.'
        ),
    )

    def test_un_docente_ajeno_no_puede_cancelar_la_reserva(
        self, api, docente, otro_docente, lab, fecha_futura, crear_reserva
    ):
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        respuesta = api.patch(
            url_cancelar(reserva.umg_id),
            {'UMG_User_ID': otro_docente.umg_id},
            format='json',
        )

        assert respuesta.status_code == 403

    def test_una_peticion_anonima_no_puede_cancelar(
        self, api, docente, lab, fecha_futura, crear_reserva
    ):
        """Sin identificar al solicitante, la operacion deberia rechazarse."""
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        respuesta = api.patch(url_cancelar(reserva.umg_id), format='json')

        assert respuesta.status_code in (401, 403)


# --------------------------------------------------------------------------- #
# Evidencia del alcance de DEF-007                                             #
# --------------------------------------------------------------------------- #

class TestAlcanceDeLaFaltaDeAutorizacion:
    """
    Pruebas que documentan el estado actual: pasan hoy porque comprueban que la
    proteccion NO existe. Sirven para dimensionar el riesgo de DEF-007 y
    fallaran el dia que se implemente la autorizacion.
    """

    def test_cualquier_peticion_puede_cancelar_una_reserva_ajena(
        self, api, docente, lab, fecha_futura, crear_reserva
    ):
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        respuesta = api.patch(url_cancelar(reserva.umg_id), format='json')

        assert respuesta.status_code == 200, (
            'La cancelacion ya exige autorizacion: retira esta prueba y quita '
            'las marcas xfail del escenario 3.'
        )

    def test_la_bitacora_no_registra_quien_cancelo(
        self, api, docente, lab, fecha_futura, crear_reserva
    ):
        """
        Consecuencia directa de DEF-007 sobre HU-009: reservas_cancelar() llama
        a registrar_log(None, ...) porque no tiene a quien atribuir la accion.
        El historial queda con el que pero sin el quien.
        """
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        api.patch(url_cancelar(reserva.umg_id), format='json')

        registro = LogEntry.objects.get(umg_accion='CANCELAR_RESERVA')
        assert registro.umg_user_id is None, (
            'La cancelacion ya registra al responsable: actualiza esta prueba.'
        )
