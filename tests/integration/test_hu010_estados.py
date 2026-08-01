"""
HU-010 - Gestion automatica de estados | PRUEBAS DE INTEGRACION

    "Como sistema, quiero gestionar automaticamente las transiciones de estado
     de las reservas (Activa, Cancelada, Finalizada), para reflejar su ciclo de
     vida real sin intervencion manual."

HU-010 no expone endpoint propio: es el comportamiento transversal del campo
umg_estado a lo largo de POST /api/reservas/ y PATCH /api/reservas/{id}/cancelar/.

Codificacion en base de datos, segun el documento de criterios:

    'R'  Reservada    (la GUI la presenta como "Reservada"/"Activa")
    'C'  Cancelada
    'F'  Finalizada   (asignada por finalizar_vencidas(), reservas/views.py)
"""

import pytest
from django.urls import reverse

from reservas.models import Reserva

pytestmark = [pytest.mark.integration, pytest.mark.hu010, pytest.mark.django_db]


def url_cancelar(pk):
    return reverse('reservas-cancelar', args=[pk])


# --------------------------------------------------------------------------- #
# Escenario 1 - Estado inicial de una reserva nueva                            #
# --------------------------------------------------------------------------- #

class TestEscenario1EstadoInicial:
    """
    Dado    que un docente registra una nueva reserva valida
    Cuando  el sistema completa el registro
    Entonces la reserva queda con el estado "Activa" asignado automaticamente.

    Verifica: RF-005, RN-010
    """

    def test_la_reserva_nace_en_estado_reservada(
        self, api, url_reservas, payload_valido
    ):
        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.data['UMG_Estado'] == 'R'
        assert Reserva.objects.first().umg_estado == 'R'

    def test_el_estado_lo_asigna_el_sistema_y_no_el_cliente(
        self, api, url_reservas, payload_valido
    ):
        """
        "Asignado automaticamente" implica que el cliente no puede elegirlo:
        enviar un estado en el cuerpo no debe tener efecto.
        """
        payload_valido['UMG_Estado'] = 'C'

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.data['UMG_Estado'] == 'R'
        assert Reserva.objects.first().umg_estado == 'R'

    def test_el_valor_por_defecto_del_modelo_es_reservada(self, docente, lab,
                                                          fecha_futura):
        reserva = Reserva.objects.create(
            umg_user=docente,
            umg_lab=lab,
            umg_fecha_reserva=fecha_futura,
            umg_hora_inicio='08:00',
            umg_hora_fin='10:00',
            umg_motivo='Sin estado explicito',
        )

        assert reserva.umg_estado == 'R'


# --------------------------------------------------------------------------- #
# Escenario 2 - Transicion por cancelacion                                     #
# --------------------------------------------------------------------------- #

class TestEscenario2TransicionPorCancelacion:
    """
    Dado    que una reserva se encuentra en estado "Activa"
    Cuando  el docente creador o el administrador la cancela antes de la hora de
            inicio
    Entonces el estado de la reserva cambia a "Cancelada".

    Verifica: RF-006
    """

    def test_la_cancelacion_transiciona_de_r_a_c(
        self, api, docente, lab, fecha_futura, crear_reserva
    ):
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')
        assert reserva.umg_estado == 'R'

        api.patch(
            url_cancelar(reserva.umg_id),
            {'UMG_Solicitante_ID': docente.umg_id},
            format='json',
        )

        reserva.refresh_from_db()
        assert reserva.umg_estado == 'C'

    def test_la_transicion_se_refleja_en_las_consultas(
        self, api, docente, lab, fecha_futura, crear_reserva
    ):
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        api.patch(
            url_cancelar(reserva.umg_id),
            {'UMG_Solicitante_ID': docente.umg_id},
            format='json',
        )

        detalle = api.get(reverse('reservas-detalle', args=[reserva.umg_id]))
        assert detalle.data['UMG_Estado'] == 'C'

    def test_el_estado_cancelada_es_terminal_para_la_cancelacion(
        self, api, docente, lab, fecha_futura, crear_reserva
    ):
        """No se puede cancelar dos veces: la segunda vez responde 409."""
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')
        datos = {'UMG_Solicitante_ID': docente.umg_id}

        api.patch(url_cancelar(reserva.umg_id), datos, format='json')
        segunda = api.patch(url_cancelar(reserva.umg_id), datos, format='json')

        assert segunda.status_code == 409
        reserva.refresh_from_db()
        assert reserva.umg_estado == 'C'


# --------------------------------------------------------------------------- #
# Escenario 3 - Finalizacion automatica                                        #
# --------------------------------------------------------------------------- #

class TestEscenario3FinalizacionAutomatica:
    """
    Dado    que una reserva se encuentra en estado "Activa"
    Cuando  concluye el bloque horario reservado
    Entonces el sistema actualiza el estado de la reserva a "Finalizada".

    Verifica: RF-006
    """

    def test_una_reserva_vencida_pasa_a_finalizada(
        self, api, docente, lab, fecha_pasada, crear_reserva
    ):
        reserva = crear_reserva(docente, lab, fecha_pasada, '08:00', '10:00')

        api.get(reverse('reservas-detalle', args=[reserva.umg_id]))

        reserva.refresh_from_db()
        assert reserva.umg_estado == 'F'

    def test_el_listado_muestra_las_vencidas_como_finalizadas(
        self, api, url_reservas, docente, lab, fecha_pasada, crear_reserva
    ):
        crear_reserva(docente, lab, fecha_pasada, '08:00', '10:00')

        datos = api.get(url_reservas).data

        assert datos[0]['UMG_Estado'] == 'F'


# --------------------------------------------------------------------------- #
# Escenario 4 - Transicion de estado no permitida                              #
# --------------------------------------------------------------------------- #

class TestEscenario4TransicionNoPermitida:
    """
    Dado    que una reserva se encuentra en estado "Cancelada" o "Finalizada"
    Cuando  se intenta regresarla al estado "Activa"
    Entonces el sistema rechaza la operacion; las transiciones solo pueden
            ocurrir conforme al ciclo de vida definido.

    Verifica: RN-010

    NOTA: hoy este criterio se cumple por ausencia. Al no existir endpoint de
    modificacion (DEF-005), la API simplemente no ofrece ninguna via para
    revertir un estado. El resultado exigido se obtiene, pero por falta de
    funcionalidad y no por una regla de transicion implementada: el dia que se
    agregue HU-007 habra que escribir esa regla explicitamente.
    """

    @pytest.mark.parametrize('metodo', ['put', 'patch'])
    def test_ninguna_ruta_permite_reactivar_una_reserva_cancelada(
        self, api, docente, lab, fecha_futura, crear_reserva, metodo
    ):
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00', estado='C')

        respuesta = getattr(api, metodo)(
            reverse('reservas-detalle', args=[reserva.umg_id]),
            {'UMG_Estado': 'R'},
            format='json',
        )

        assert respuesta.status_code == 405
        reserva.refresh_from_db()
        assert reserva.umg_estado == 'C'

    def test_el_endpoint_de_cancelacion_no_reactiva(
        self, api, docente, lab, fecha_futura, crear_reserva
    ):
        """Enviar UMG_Estado='R' al cancelar no debe revertir nada."""
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00', estado='C')

        api.patch(url_cancelar(reserva.umg_id), {'UMG_Estado': 'R'}, format='json')

        reserva.refresh_from_db()
        assert reserva.umg_estado == 'C'

    def test_crear_una_reserva_nueva_no_reactiva_la_cancelada(
        self, api, url_reservas, payload_valido, docente, lab, fecha_futura,
        crear_reserva
    ):
        """
        Reservar el mismo bloque tras una cancelacion genera un registro nuevo;
        la cancelada permanece cancelada.
        """
        cancelada = crear_reserva(
            docente, lab, fecha_futura, '08:00', '10:00', estado='C'
        )

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 201
        cancelada.refresh_from_db()
        assert cancelada.umg_estado == 'C'
        assert respuesta.data['UMG_ID'] != cancelada.umg_id


# --------------------------------------------------------------------------- #
# Cobertura adicional - Consistencia del dominio de estados                    #
# --------------------------------------------------------------------------- #

class TestDominioDeEstados:
    """Cobertura mas alla de los criterios escritos."""

    def test_el_modelo_no_restringe_el_dominio_de_valores(
        self, docente, lab, fecha_futura
    ):
        """
        DEF-011: umg_estado es un CharField(max_length=1) sin choices ni
        constraint. La base acepta cualquier letra, de modo que un error de
        programacion puede dejar una reserva en un estado inexistente sin que
        nada lo impida.
        """
        reserva = Reserva.objects.create(
            umg_user=docente,
            umg_lab=lab,
            umg_fecha_reserva=fecha_futura,
            umg_hora_inicio='08:00',
            umg_hora_fin='10:00',
            umg_motivo='Estado invalido',
            umg_estado='X',
        )
        reserva.refresh_from_db()

        assert reserva.umg_estado == 'X', (
            'El modelo ya valida el dominio de estados: actualiza DEF-011.'
        )

    def test_un_estado_desconocido_se_comporta_como_no_activo(
        self, api, url_reservas, payload_valido, docente, lab, fecha_futura,
        crear_reserva
    ):
        """
        Consecuencia de DEF-011: hay_traslape() solo considera 'R', asi que una
        reserva con estado corrupto deja de bloquear el laboratorio sin que
        nadie se entere.
        """
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00', estado='X')

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 201
