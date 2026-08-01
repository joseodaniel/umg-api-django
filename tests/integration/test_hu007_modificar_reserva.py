"""
HU-007 - Modificar una reserva existente | PRUEBAS DE INTEGRACION

    "Como administrador, quiero modificar los datos de una reserva existente
     antes del inicio de la actividad, para atender cambios en la planificacion
     academica sin generar conflictos de disponibilidad."

Endpoint bajo prueba: PUT /api/reservas/{id}/modificar/ (reservas/views.py:reservas_modificar)

DEF-005 (RF-007 no implementado) esta resuelto: el endpoint existe, valida
RN-006 (actividad ya iniciada), RN-013 (solo el creador o un Admin puede
modificar) y reevalua traslapes/bloqueos excluyendo la propia reserva.

La ruta de detalle ('<int:pk>/') sigue siendo de solo lectura: la
modificacion vive en una ruta distinta ('<int:pk>/modificar/').
"""

from datetime import timedelta

import pytest
from django.urls import reverse

from reservas.models import Reserva

pytestmark = [pytest.mark.integration, pytest.mark.hu007, pytest.mark.django_db]


def url_detalle(pk):
    return reverse('reservas-detalle', args=[pk])


def url_modificar(pk):
    return reverse('reservas-modificar', args=[pk])


# --------------------------------------------------------------------------- #
# Cobertura adicional - La ruta de detalle no modifica                         #
# --------------------------------------------------------------------------- #

class TestLaRutaDeDetalleNoModifica:
    """La modificacion vive en '<int:pk>/modificar/', no en '<int:pk>/'."""

    @pytest.mark.parametrize('metodo', ['put', 'patch'])
    def test_la_ruta_de_detalle_no_admite_modificacion(
        self, api, docente, lab, fecha_futura, crear_reserva, metodo
    ):
        """La ruta existe pero solo declara GET: responde 405, no 200."""
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        respuesta = getattr(api, metodo)(
            url_detalle(reserva.umg_id), {'UMG_Motivo': 'Nuevo motivo'}, format='json'
        )

        assert respuesta.status_code == 405

    @pytest.mark.parametrize('ruta_sufijo', ['editar/', 'actualizar/'])
    def test_ninguna_otra_ruta_plausible_de_modificacion_resuelve(
        self, api, docente, lab, fecha_futura, crear_reserva, ruta_sufijo
    ):
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        respuesta = api.patch(
            f'/api/reservas/{reserva.umg_id}/{ruta_sufijo}',
            {'UMG_Motivo': 'Nuevo motivo'},
            format='json',
        )

        assert respuesta.status_code == 404

    def test_la_reserva_permanece_intacta_tras_intentar_modificarla_por_el_detalle(
        self, api, docente, lab, fecha_futura, crear_reserva
    ):
        reserva = crear_reserva(
            docente, lab, fecha_futura, '08:00', '10:00', motivo='Motivo original'
        )

        api.put(
            url_detalle(reserva.umg_id), {'UMG_Motivo': 'Modificado'}, format='json'
        )

        reserva.refresh_from_db()
        assert reserva.umg_motivo == 'Motivo original'


# --------------------------------------------------------------------------- #
# Escenario 1 - Modificacion valida antes del inicio                           #
# --------------------------------------------------------------------------- #

class TestEscenario1ModificacionValida:
    """
    Dado    que la reserva esta en estado "Activa", la actividad no ha iniciado
            y los nuevos datos no generan conflicto de disponibilidad
    Cuando  el administrador solicita la modificacion
    Entonces el sistema aplica los cambios, registra la operacion en el
            historial de auditoria y responde con HTTP 200.

    Verifica: RF-007, RN-006, RN-007
    """

    def test_aplica_los_cambios_y_responde_200(
        self, api, administrador, docente, lab, fecha_futura, crear_reserva
    ):
        reserva = crear_reserva(
            docente, lab, fecha_futura, '08:00', '10:00', motivo='Motivo original'
        )

        respuesta = api.put(
            url_modificar(reserva.umg_id),
            {
                'UMG_User_ID': docente.umg_id,
                'UMG_Lab_ID': lab.umg_id,
                'UMG_Fecha_Reserva': fecha_futura.isoformat(),
                'UMG_Hora_Inicio': '14:00',
                'UMG_Hora_Fin': '16:00',
                'UMG_Motivo': 'Motivo actualizado',
                'UMG_Solicitante_ID': administrador.umg_id,
            },
            format='json',
        )

        assert respuesta.status_code == 200
        reserva.refresh_from_db()
        assert reserva.umg_motivo == 'Motivo actualizado'
        assert str(reserva.umg_hora_inicio) == '14:00:00'

    def test_registra_la_operacion_en_el_historial(
        self, api, administrador, docente, lab, fecha_futura, crear_reserva
    ):
        """RN-007: la trazabilidad de la modificacion es parte del criterio."""
        from logs.models import LogEntry

        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        api.put(
            url_modificar(reserva.umg_id),
            {
                'UMG_User_ID': docente.umg_id,
                'UMG_Lab_ID': lab.umg_id,
                'UMG_Fecha_Reserva': fecha_futura.isoformat(),
                'UMG_Hora_Inicio': '08:00',
                'UMG_Hora_Fin': '10:00',
                'UMG_Motivo': 'Actualizado',
                'UMG_Solicitante_ID': administrador.umg_id,
            },
            format='json',
        )

        assert LogEntry.objects.filter(umg_accion='MODIFICAR_RESERVA').exists()


# --------------------------------------------------------------------------- #
# Escenario 2 - Modificacion con conflicto de disponibilidad                   #
# --------------------------------------------------------------------------- #

class TestEscenario2ConflictoDeDisponibilidad:
    """
    Dado    que los nuevos datos coinciden con otra reserva activa (mismo
            laboratorio, fecha y bloque)
    Cuando  el administrador solicita la modificacion
    Entonces el sistema rechaza la operacion con HTTP 409 y la reserva original
            permanece sin cambios.

    Verifica: RN-004
    """

    def test_rechaza_con_409_y_no_altera_la_reserva(
        self, api, administrador, docente, otro_docente, lab, fecha_futura,
        crear_reserva
    ):
        propia = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')
        crear_reserva(otro_docente, lab, fecha_futura, '14:00', '16:00')

        respuesta = api.put(
            url_modificar(propia.umg_id),
            {
                'UMG_User_ID': docente.umg_id,
                'UMG_Lab_ID': lab.umg_id,
                'UMG_Fecha_Reserva': fecha_futura.isoformat(),
                'UMG_Hora_Inicio': '14:00',
                'UMG_Hora_Fin': '16:00',
                'UMG_Motivo': 'Motivo original',
                'UMG_Solicitante_ID': administrador.umg_id,
            },
            format='json',
        )

        assert respuesta.status_code == 409
        propia.refresh_from_db()
        assert str(propia.umg_hora_inicio) == '08:00:00'

    def test_mover_la_reserva_a_su_propio_horario_no_es_conflicto(
        self, api, administrador, docente, lab, fecha_futura, crear_reserva
    ):
        """
        Al reevaluar la disponibilidad hay que excluir la reserva que se esta
        modificando, o chocaria consigo misma. La funcion hay_traslape() ya
        acepta el parametro excluir_id justamente para esto.
        """
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        respuesta = api.put(
            url_modificar(reserva.umg_id),
            {
                'UMG_User_ID': docente.umg_id,
                'UMG_Lab_ID': lab.umg_id,
                'UMG_Fecha_Reserva': fecha_futura.isoformat(),
                'UMG_Hora_Inicio': '08:00',
                'UMG_Hora_Fin': '10:00',
                'UMG_Motivo': 'Solo cambia el motivo',
                'UMG_Solicitante_ID': administrador.umg_id,
            },
            format='json',
        )

        assert respuesta.status_code == 200


# --------------------------------------------------------------------------- #
# Escenario 3 - Modificacion de una actividad ya iniciada                      #
# --------------------------------------------------------------------------- #

class TestEscenario3ActividadYaIniciada:
    """
    Dado    que la hora de inicio de la reserva ya transcurrio
    Cuando  se solicita la modificacion de esa reserva
    Entonces el sistema rechaza la operacion con un mensaje de error y no aplica
            ningun cambio.

    Verifica: RN-006
    """

    def test_rechaza_la_modificacion_de_una_actividad_iniciada(
        self, api, administrador, docente, lab, fecha_pasada, crear_reserva
    ):
        reserva = crear_reserva(
            docente, lab, fecha_pasada, '08:00', '10:00', motivo='Motivo original'
        )

        respuesta = api.put(
            url_modificar(reserva.umg_id),
            {
                'UMG_User_ID': docente.umg_id,
                'UMG_Lab_ID': lab.umg_id,
                'UMG_Fecha_Reserva': fecha_pasada.isoformat(),
                'UMG_Hora_Inicio': '08:00',
                'UMG_Hora_Fin': '10:00',
                'UMG_Motivo': 'Intento tardio',
                'UMG_Solicitante_ID': administrador.umg_id,
            },
            format='json',
        )

        assert respuesta.status_code in (400, 409)
        reserva.refresh_from_db()
        assert reserva.umg_motivo == 'Motivo original'


# --------------------------------------------------------------------------- #
# Escenario 4 - Modificacion por un usuario sin permisos                       #
# --------------------------------------------------------------------------- #

class TestEscenario4UsuarioSinPermisos:
    """
    Dado    que el solicitante no es el docente creador de la reserva ni posee
            el rol de Administrador
    Cuando  intenta modificar la reserva
    Entonces el sistema rechaza la operacion con HTTP 403 (Forbidden).

    Verifica: RN-013
    """

    def test_un_docente_ajeno_no_puede_modificar_la_reserva(
        self, api, docente, otro_docente, lab, fecha_futura, crear_reserva
    ):
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        respuesta = api.put(
            url_modificar(reserva.umg_id),
            {
                'UMG_User_ID': docente.umg_id,
                'UMG_Lab_ID': lab.umg_id,
                'UMG_Fecha_Reserva': fecha_futura.isoformat(),
                'UMG_Hora_Inicio': '08:00',
                'UMG_Hora_Fin': '10:00',
                'UMG_Motivo': 'Intento ajeno',
                'UMG_Solicitante_ID': otro_docente.umg_id,
            },
            format='json',
        )

        assert respuesta.status_code == 403


# --------------------------------------------------------------------------- #
# La alternativa disponible hoy                                                #
# --------------------------------------------------------------------------- #

class TestAlternativaCancelarYRecrear:
    """
    Sin endpoint de modificacion, la unica via para cambiar una reserva es
    cancelarla y crear una nueva. Estas pruebas verifican que el rodeo funciona,
    y de paso exponen lo que se pierde por el camino.
    """

    def test_cancelar_y_recrear_logra_el_efecto_deseado(
        self, api, url_reservas, payload_valido, docente, lab, fecha_futura
    ):
        original = api.post(url_reservas, payload_valido, format='json')
        reserva_id = original.data['UMG_ID']

        api.patch(
            reverse('reservas-cancelar', args=[reserva_id]),
            {'UMG_Solicitante_ID': docente.umg_id},
            format='json',
        )

        payload_valido['UMG_Hora_Inicio'] = '14:00'
        payload_valido['UMG_Hora_Fin'] = '16:00'
        nueva = api.post(url_reservas, payload_valido, format='json')

        assert nueva.status_code == 201
        # Se relee por GET en lugar de confiar en el cuerpo del POST: ese
        # devuelve la hora sin normalizar (DEF-012).
        detalle = api.get(url_detalle(nueva.data['UMG_ID']))
        assert detalle.data['UMG_Hora_Inicio'] == '14:00:00'

    def test_el_rodeo_cambia_el_identificador_de_la_reserva(
        self, api, url_reservas, payload_valido
    ):
        """
        Consecuencia concreta de DEF-005: RN-008 promete que el identificador es
        inmutable, pero "modificar" via cancelar-y-recrear genera uno nuevo.
        Cualquier referencia externa al identificador anterior queda rota.
        """
        original = api.post(url_reservas, payload_valido, format='json')
        id_original = original.data['UMG_ID']

        api.patch(
            reverse('reservas-cancelar', args=[id_original]),
            {'UMG_Solicitante_ID': payload_valido['UMG_User_ID']},
            format='json',
        )
        payload_valido['UMG_Motivo'] = 'Motivo corregido'
        nueva = api.post(url_reservas, payload_valido, format='json')

        assert nueva.data['UMG_ID'] != id_original
        assert Reserva.objects.count() == 2

    def test_el_rodeo_deja_una_reserva_cancelada_que_ensucia_el_historial(
        self, api, url_reservas, payload_valido
    ):
        """
        Cada correccion de un dato deja una reserva cancelada. Para HU-004 y
        HU-009 eso es ruido indistinguible de una cancelacion real.
        """
        original = api.post(url_reservas, payload_valido, format='json')
        api.patch(
            reverse('reservas-cancelar', args=[original.data['UMG_ID']]),
            {'UMG_Solicitante_ID': payload_valido['UMG_User_ID']},
            format='json',
        )
        payload_valido['UMG_Motivo'] = 'Motivo corregido'
        api.post(url_reservas, payload_valido, format='json')

        canceladas = Reserva.objects.filter(umg_estado='C')
        assert canceladas.count() == 1
