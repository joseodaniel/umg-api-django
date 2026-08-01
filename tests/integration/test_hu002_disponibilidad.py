"""
HU-002 - Validacion automatica de disponibilidad | PRUEBAS DE INTEGRACION

    "Como docente, quiero que el sistema valide automaticamente la
     disponibilidad del laboratorio al momento de reservar, para evitar
     conflictos y duplicidades con reservas de otros docentes."

HU-002 no expone un endpoint propio: es una validacion que se dispara dentro de
POST /api/reservas/. Por eso las pruebas atacan ese mismo endpoint, pero desde
un angulo distinto al de HU-001: alli se verificaba el formato de los datos de
entrada, aqui se verifica la interaccion con las reservas que ya existen.

Cada clase implementa uno de los 3 escenarios de aceptacion en formato Gherkin.
"""

from datetime import timedelta

import pytest
from django.urls import reverse

from condiciones.models import Condicion
from reservas.models import Reserva

pytestmark = [pytest.mark.integration, pytest.mark.hu002, pytest.mark.django_db]


# --------------------------------------------------------------------------- #
# Escenario 1 - Conflicto por reserva existente                                #
# --------------------------------------------------------------------------- #

class TestEscenario1ConflictoPorReservaExistente:
    """
    Dado    que existe una reserva en estado "Activa" para el mismo laboratorio,
            fecha y bloque horario
    Cuando  otro docente intenta registrar una reserva con esos mismos datos
    Entonces el sistema rechaza la solicitud con HTTP 409 (Conflict), informa el
            conflicto de disponibilidad y no registra la nueva reserva.

    Verifica: RF-002, RN-001, RN-004
    """

    def test_responde_http_409_ante_un_bloque_identico(
        self, api, url_reservas, payload_valido, docente, otro_docente, lab,
        fecha_futura, crear_reserva
    ):
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')
        payload_valido['UMG_User_ID'] = otro_docente.umg_id

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 409

    def test_no_registra_la_nueva_reserva(
        self, api, url_reservas, payload_valido, docente, otro_docente, lab,
        fecha_futura, crear_reserva
    ):
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')
        payload_valido['UMG_User_ID'] = otro_docente.umg_id

        api.post(url_reservas, payload_valido, format='json')

        assert Reserva.objects.count() == 1, 'Se creo una segunda reserva en conflicto'

    def test_el_mensaje_informa_el_conflicto_de_disponibilidad(
        self, api, url_reservas, payload_valido, docente, otro_docente, lab,
        fecha_futura, crear_reserva
    ):
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')
        payload_valido['UMG_User_ID'] = otro_docente.umg_id

        respuesta = api.post(url_reservas, payload_valido, format='json')

        mensaje = respuesta.data['mensaje'].lower()
        assert 'reserva' in mensaje
        assert 'traslapa' in mensaje or 'disponible' in mensaje

    @pytest.mark.parametrize(
        'inicio, fin, caso',
        [
            ('08:00', '10:00', 'bloque identico'),
            ('09:00', '11:00', 'invade el final del bloque ocupado'),
            ('07:00', '09:00', 'invade el inicio del bloque ocupado'),
            ('08:30', '09:30', 'queda contenido en el bloque ocupado'),
            ('07:00', '11:00', 'envuelve al bloque ocupado'),
        ],
    )
    def test_rechaza_cualquier_forma_de_traslape(
        self, api, url_reservas, payload_valido, docente, otro_docente, lab,
        fecha_futura, crear_reserva, inicio, fin, caso
    ):
        """RN-004: no basta con detectar el bloque exacto, cualquier solape cuenta."""
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')
        payload_valido['UMG_User_ID'] = otro_docente.umg_id
        payload_valido['UMG_Hora_Inicio'] = inicio
        payload_valido['UMG_Hora_Fin'] = fin

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 409, f'No se detecto el traslape: {caso}'
        assert Reserva.objects.count() == 1

    def test_el_mismo_docente_tampoco_puede_duplicar_su_reserva(
        self, api, url_reservas, payload_valido, docente, lab, fecha_futura,
        crear_reserva
    ):
        """
        RN-001 habla de duplicidades, no solo de conflictos entre docentes
        distintos. Reservar dos veces el mismo espacio debe rechazarse aunque
        sea el mismo usuario.
        """
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 409
        assert Reserva.objects.count() == 1

    def test_la_reserva_original_permanece_intacta(
        self, api, url_reservas, payload_valido, docente, otro_docente, lab,
        fecha_futura, crear_reserva
    ):
        original = crear_reserva(
            docente, lab, fecha_futura, '08:00', '10:00', motivo='Clase original'
        )
        payload_valido['UMG_User_ID'] = otro_docente.umg_id
        payload_valido['UMG_Motivo'] = 'Intento de invasion'

        api.post(url_reservas, payload_valido, format='json')

        original.refresh_from_db()
        assert original.umg_motivo == 'Clase original'
        assert original.umg_user_id == docente.umg_id
        assert original.umg_estado == 'R'


# --------------------------------------------------------------------------- #
# Escenario 2 - Disponibilidad confirmada                                      #
# --------------------------------------------------------------------------- #

class TestEscenario2DisponibilidadConfirmada:
    """
    Dado    que no existe ninguna reserva activa para el laboratorio, fecha y
            bloque horario solicitados
    Cuando  el docente envia la solicitud de creacion
    Entonces la validacion de disponibilidad es exitosa y la reserva se registra
            con HTTP 201.

    Verifica: RF-002, RN-004
    """

    def test_registra_cuando_la_agenda_esta_vacia(
        self, api, url_reservas, payload_valido
    ):
        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 201
        assert Reserva.objects.count() == 1

    def test_el_mismo_horario_en_otro_laboratorio_esta_disponible(
        self, api, url_reservas, payload_valido, docente, otro_docente, lab,
        otro_lab, fecha_futura, crear_reserva
    ):
        """La disponibilidad se evalua por laboratorio, no globalmente."""
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')
        payload_valido['UMG_User_ID'] = otro_docente.umg_id
        payload_valido['UMG_Lab_ID'] = otro_lab.umg_id

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 201
        assert Reserva.objects.count() == 2

    def test_el_mismo_horario_en_otra_fecha_esta_disponible(
        self, api, url_reservas, payload_valido, docente, otro_docente, lab,
        fecha_futura, crear_reserva
    ):
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')
        payload_valido['UMG_User_ID'] = otro_docente.umg_id
        payload_valido['UMG_Fecha_Reserva'] = (
            fecha_futura + timedelta(days=1)
        ).isoformat()

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 201
        assert Reserva.objects.count() == 2

    @pytest.mark.parametrize(
        'inicio, fin, caso',
        [
            ('10:00', '12:00', 'arranca justo cuando termina el bloque ocupado'),
            ('07:00', '08:00', 'termina justo cuando arranca el bloque ocupado'),
            ('14:00', '16:00', 'completamente separado'),
        ],
    )
    def test_los_bloques_adyacentes_no_se_consideran_conflicto(
        self, api, url_reservas, payload_valido, docente, otro_docente, lab,
        fecha_futura, crear_reserva, inicio, fin, caso
    ):
        """
        Frontera critica: si la comparacion usara <= en vez de <, dos clases
        consecutivas se rechazarian entre si y el laboratorio quedaria
        infrautilizado.
        """
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')
        payload_valido['UMG_User_ID'] = otro_docente.umg_id
        payload_valido['UMG_Hora_Inicio'] = inicio
        payload_valido['UMG_Hora_Fin'] = fin

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 201, f'Se rechazo un bloque libre: {caso}'
        assert Reserva.objects.count() == 2

    def test_varios_docentes_pueden_encadenar_bloques_el_mismo_dia(
        self, api, url_reservas, payload_valido, docente, otro_docente, lab,
        fecha_futura
    ):
        """Flujo realista: la agenda de un laboratorio se llena por turnos."""
        bloques = [
            (docente.umg_id, '07:00', '09:00'),
            (otro_docente.umg_id, '09:00', '11:00'),
            (docente.umg_id, '11:00', '13:00'),
        ]

        for user_id, inicio, fin in bloques:
            payload_valido['UMG_User_ID'] = user_id
            payload_valido['UMG_Hora_Inicio'] = inicio
            payload_valido['UMG_Hora_Fin'] = fin

            respuesta = api.post(url_reservas, payload_valido, format='json')

            assert respuesta.status_code == 201, f'Fallo el bloque {inicio}-{fin}'

        assert Reserva.objects.count() == 3


# --------------------------------------------------------------------------- #
# Escenario 3 - Las reservas canceladas liberan el espacio                     #
# --------------------------------------------------------------------------- #

class TestEscenario3LasCanceladasLiberanElEspacio:
    """
    Dado    que la unica reserva existente para ese laboratorio, fecha y bloque
            horario se encuentra en estado "Cancelada"
    Cuando  un docente solicita reservar ese mismo espacio
    Entonces el sistema considera el laboratorio disponible y permite el
            registro de la nueva reserva.

    Verifica: RN-006, RF-008
    """

    def test_una_reserva_cancelada_no_bloquea_el_espacio(
        self, api, url_reservas, payload_valido, docente, otro_docente, lab,
        fecha_futura, crear_reserva
    ):
        crear_reserva(docente, lab, fecha_futura, '08:00', '10:00', estado='C')
        payload_valido['UMG_User_ID'] = otro_docente.umg_id

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 201

    def test_la_cancelada_se_conserva_como_historico(
        self, api, url_reservas, payload_valido, docente, otro_docente, lab,
        fecha_futura, crear_reserva
    ):
        """Liberar el espacio no significa borrar el registro."""
        cancelada = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00', estado='C')
        payload_valido['UMG_User_ID'] = otro_docente.umg_id

        api.post(url_reservas, payload_valido, format='json')

        cancelada.refresh_from_db()
        assert cancelada.umg_estado == 'C'
        assert Reserva.objects.count() == 2

    def test_flujo_completo_reservar_cancelar_y_volver_a_reservar(
        self, api, url_reservas, payload_valido, docente, otro_docente, lab,
        fecha_futura
    ):
        """
        Recorre el ciclo de vida completo a traves de la API, sin tocar el ORM:

            1. El primer docente reserva el bloque         -> 201
            2. Otro docente intenta el mismo bloque        -> 409
            3. El primero cancela su reserva               -> 200
            4. El otro docente reintenta                   -> 201
        """
        # 1. Reserva original
        primera = api.post(url_reservas, payload_valido, format='json')
        assert primera.status_code == 201
        reserva_id = primera.data['UMG_ID']

        # 2. El espacio esta ocupado
        payload_valido['UMG_User_ID'] = otro_docente.umg_id
        bloqueada = api.post(url_reservas, payload_valido, format='json')
        assert bloqueada.status_code == 409

        # 3. Se cancela la original
        cancelacion = api.patch(
            reverse('reservas-cancelar', args=[reserva_id]),
            {'UMG_Solicitante_ID': docente.umg_id},
            format='json',
        )
        assert cancelacion.status_code == 200

        # 4. El espacio quedo libre
        reintento = api.post(url_reservas, payload_valido, format='json')
        assert reintento.status_code == 201
        assert reintento.data['UMG_User_ID'] == otro_docente.umg_id

        assert Reserva.objects.filter(umg_estado='C').count() == 1
        assert Reserva.objects.filter(umg_estado='R').count() == 1


# --------------------------------------------------------------------------- #
# Cobertura adicional - Bloqueos administrativos                               #
# --------------------------------------------------------------------------- #

class TestBloqueosAdministrativos:
    """
    Cobertura mas alla de los criterios escritos.

    RF-002 habla de validar la disponibilidad del laboratorio, y el sistema la
    determina con dos reglas: las reservas de otros docentes (escenarios 1 a 3)
    y las condiciones administrativas de la tabla UMG_CONDI (mantenimientos,
    asuetos). El documento de criterios no cubre la segunda, pero afecta el
    mismo resultado, asi que se verifica aqui.
    """

    def test_un_mantenimiento_del_laboratorio_impide_reservar(
        self, api, url_reservas, payload_valido, lab, fecha_futura
    ):
        Condicion.objects.create(
            umg_lab=lab,
            umg_fecha=fecha_futura,
            umg_hora_inicio='07:00',
            umg_hora_fin='12:00',
            umg_tipo='MANTENIMIENTO',
            umg_motivo='Actualizacion de equipos',
            umg_estado=1,
        )

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 409
        assert Reserva.objects.count() == 0

    def test_un_asueto_institucional_impide_reservar_cualquier_laboratorio(
        self, api, url_reservas, payload_valido, otro_lab, fecha_futura
    ):
        """Una condicion con umg_lab NULL aplica a toda la facultad."""
        Condicion.objects.create(
            umg_lab=None,
            umg_fecha=fecha_futura,
            umg_hora_inicio='07:00',
            umg_hora_fin='22:00',
            umg_tipo='ASUETO',
            umg_motivo='Feriado nacional',
            umg_estado=1,
        )
        payload_valido['UMG_Lab_ID'] = otro_lab.umg_id

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 409
        assert Reserva.objects.count() == 0

    def test_un_bloqueo_dado_de_baja_no_impide_reservar(
        self, api, url_reservas, payload_valido, lab, fecha_futura
    ):
        Condicion.objects.create(
            umg_lab=lab,
            umg_fecha=fecha_futura,
            umg_hora_inicio='07:00',
            umg_hora_fin='12:00',
            umg_tipo='MANTENIMIENTO',
            umg_motivo='Mantenimiento reprogramado',
            umg_estado=0,
        )

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 201

    def test_un_bloqueo_fuera_del_horario_solicitado_no_estorba(
        self, api, url_reservas, payload_valido, lab, fecha_futura
    ):
        Condicion.objects.create(
            umg_lab=lab,
            umg_fecha=fecha_futura,
            umg_hora_inicio='14:00',
            umg_hora_fin='18:00',
            umg_tipo='MANTENIMIENTO',
            umg_motivo='Mantenimiento vespertino',
            umg_estado=1,
        )

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 201
