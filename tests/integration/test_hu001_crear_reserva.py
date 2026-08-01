"""
HU-001 - Registrar una nueva reserva | PRUEBAS DE INTEGRACION

    "Como docente, quiero registrar una nueva reserva indicando mi nombre,
     correo institucional, laboratorio, fecha, bloque horario y motivo, para
     asegurar el espacio donde desarrollare mi actividad academica."

Cada clase implementa uno de los 6 escenarios de aceptacion en formato Gherkin.
Las pruebas recorren el stack completo: URL -> vista -> ORM -> respuesta HTTP.

Endpoint bajo prueba: POST /api/reservas/
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from logs.models import LogEntry
from reservas.models import Reserva

pytestmark = [pytest.mark.integration, pytest.mark.hu001, pytest.mark.django_db]


# --------------------------------------------------------------------------- #
# Escenario 1 - Registro exitoso de una reserva                                #
# --------------------------------------------------------------------------- #

class TestEscenario1RegistroExitoso:
    """
    Dado    que un docente proporciona nombre, correo institucional valido,
            laboratorio, fecha futura, bloque horario dentro del horario habil
            y el motivo de la actividad
    Cuando  envia la solicitud de creacion de la reserva (POST /api/reservas/)
    Entonces el sistema registra la reserva, le asigna un identificador unico e
            inmutable, establece el estado inicial en "Activa" (reservada) y
            responde con HTTP 201 y el detalle en formato JSON.

    Verifica: RF-001, RN-008, RN-010
    """

    def test_responde_http_201(self, api, url_reservas, payload_valido):
        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 201

    def test_persiste_la_reserva_en_la_base_de_datos(
        self, api, url_reservas, payload_valido
    ):
        api.post(url_reservas, payload_valido, format='json')

        assert Reserva.objects.count() == 1

    def test_asigna_un_identificador_unico(self, api, url_reservas, payload_valido):
        """RN-008: el sistema genera el identificador, no lo envia el cliente."""
        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.data['UMG_ID'] is not None
        assert respuesta.data['UMG_ID'] == Reserva.objects.first().umg_id

    def test_establece_el_estado_inicial_en_reservada(
        self, api, url_reservas, payload_valido
    ):
        """RN-010: 'R' en base de datos se presenta como "Reservada" en la GUI."""
        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.data['UMG_Estado'] == 'R'
        assert Reserva.objects.first().umg_estado == 'R'

    def test_devuelve_el_detalle_completo_en_json(
        self, api, url_reservas, payload_valido, docente, lab, fecha_futura
    ):
        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta['Content-Type'].startswith('application/json')
        assert respuesta.data['UMG_User_ID'] == docente.umg_id
        assert respuesta.data['UMG_Docente_Nombre'] == 'Juan Perez'
        assert respuesta.data['UMG_Docente_Correo'] == 'jperez@umg.edu.gt'
        assert respuesta.data['UMG_Lab_ID'] == lab.umg_id
        assert respuesta.data['UMG_Lab_Nombre'] == 'Lab Redes 1'
        assert respuesta.data['UMG_Fecha_Reserva'] == fecha_futura.isoformat()
        assert respuesta.data['UMG_Motivo'] == 'Practica de configuracion de routers'

    def test_registra_la_operacion_en_la_bitacora_de_auditoria(
        self, api, url_reservas, payload_valido, docente
    ):
        """RF-012: toda creacion deja rastro en el historial (enlaza con HU-009)."""
        api.post(url_reservas, payload_valido, format='json')

        registro = LogEntry.objects.filter(umg_accion='CREAR_RESERVA').first()
        assert registro is not None
        assert registro.umg_modulo == 'Reservas'
        assert registro.umg_user_id == docente.umg_id

    @pytest.mark.parametrize('campo', ['UMG_Hora_Inicio', 'UMG_Hora_Fin'])
    def test_la_hora_devuelta_al_crear_coincide_con_la_devuelta_al_consultar(
        self, api, url_reservas, payload_valido, campo
    ):
        creada = api.post(url_reservas, payload_valido, format='json')

        consultada = api.get(
            reverse('reservas-detalle', args=[creada.data['UMG_ID']])
        )

        assert creada.data[campo] == consultada.data[campo]


# --------------------------------------------------------------------------- #
# Escenario 2 - Campos obligatorios incompletos                                #
# --------------------------------------------------------------------------- #

class TestEscenario2CamposObligatoriosIncompletos:
    """
    Dado    que el docente omite uno o mas campos obligatorios
            (por ejemplo, el motivo o el nombre del docente)
    Cuando  envia la solicitud de creacion de la reserva
    Entonces el sistema rechaza la operacion con HTTP 400, indica en el mensaje
            de error el campo faltante y no registra ninguna informacion.

    Verifica: RF-001, RN-002, RN-005
    """

    @pytest.mark.parametrize(
        'campo_omitido',
        [
            'UMG_Motivo',
            'UMG_Fecha_Reserva',
            'UMG_User_ID',
            'UMG_Lab_ID',
            'UMG_Hora_Inicio',
            'UMG_Hora_Fin',
        ],
    )
    def test_rechaza_con_400_al_faltar_un_campo(
        self, api, url_reservas, payload_valido, campo_omitido
    ):
        payload_valido.pop(campo_omitido)

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 400

    def test_no_persiste_nada_cuando_falta_el_motivo(
        self, api, url_reservas, payload_valido
    ):
        payload_valido.pop('UMG_Motivo')

        api.post(url_reservas, payload_valido, format='json')

        assert Reserva.objects.count() == 0

    def test_el_mensaje_de_error_describe_el_problema(
        self, api, url_reservas, payload_valido
    ):
        payload_valido.pop('UMG_Motivo')

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert 'motivo' in respuesta.data['mensaje'].lower()

    def test_rechaza_un_motivo_compuesto_solo_de_espacios(
        self, api, url_reservas, payload_valido
    ):
        payload_valido['UMG_Motivo'] = '     '

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 400
        assert Reserva.objects.count() == 0


# --------------------------------------------------------------------------- #
# Escenario 3 - Identidad del docente / correo institucional                   #
# --------------------------------------------------------------------------- #

class TestEscenario3IdentidadDelDocente:
    """
    Dado    que el docente proporciona un correo electronico que no cumple con
            un formato valido
    Cuando  envia la solicitud de creacion de la reserva
    Entonces el sistema rechaza la operacion con HTTP 400 y un mensaje
            descriptivo, sin registrar la reserva.

    Verifica: RN-009

    NOTA DE ADAPTACION
    ------------------
    El endpoint no recibe el correo: recibe UMG_User_ID y deriva el correo del
    usuario ya registrado (coincide con el comentario de la GUI, donde el correo
    se captura automaticamente de la sesion). Por lo tanto la validacion de
    formato de correo pertenece al alta de usuarios, no a este endpoint.

    Lo que si es verificable aqui es la regla equivalente: solo un docente
    existente y activo puede quedar asociado a una reserva, y el correo devuelto
    debe ser el institucional del usuario.
    """

    def test_rechaza_un_docente_inexistente(self, api, url_reservas, payload_valido):
        payload_valido['UMG_User_ID'] = 999999

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 400
        assert Reserva.objects.count() == 0

    def test_rechaza_un_docente_inactivo(
        self, api, url_reservas, payload_valido, docente_inactivo
    ):
        payload_valido['UMG_User_ID'] = docente_inactivo.umg_id

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 400
        assert 'no existe' in respuesta.data['mensaje'].lower() or \
               'inactivo' in respuesta.data['mensaje'].lower()
        assert Reserva.objects.count() == 0

    def test_rechaza_un_laboratorio_inexistente(
        self, api, url_reservas, payload_valido
    ):
        payload_valido['UMG_Lab_ID'] = 999999

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 400
        assert Reserva.objects.count() == 0

    def test_rechaza_un_laboratorio_inactivo(
        self, api, url_reservas, payload_valido, lab_inactivo
    ):
        payload_valido['UMG_Lab_ID'] = lab_inactivo.umg_id

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 400
        assert Reserva.objects.count() == 0

    def test_la_respuesta_expone_el_correo_institucional_del_docente(
        self, api, url_reservas, payload_valido
    ):
        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.data['UMG_Docente_Correo'].endswith('@umg.edu.gt')


# --------------------------------------------------------------------------- #
# Escenario 4 - Fecha anterior a la fecha actual                               #
# --------------------------------------------------------------------------- #

class TestEscenario4FechaEnElPasado:
    """
    Dado    que el docente indica una fecha de reserva anterior a la fecha
            actual del sistema
    Cuando  envia la solicitud de creacion de la reserva
    Entonces el sistema rechaza la operacion con HTTP 400 y un mensaje que
            indica que la fecha no es valida.

    Verifica: RN-003
    """

    @pytest.mark.parametrize('dias_atras', [1, 7, 365])
    def test_rechaza_fechas_pasadas(
        self, api, url_reservas, payload_valido, dias_atras
    ):
        payload_valido['UMG_Fecha_Reserva'] = (
            date.today() - timedelta(days=dias_atras)
        ).isoformat()

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 400
        assert Reserva.objects.count() == 0

    def test_el_mensaje_indica_que_la_fecha_no_es_valida(
        self, api, url_reservas, payload_valido
    ):
        payload_valido['UMG_Fecha_Reserva'] = (
            date.today() - timedelta(days=1)
        ).isoformat()

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert 'fecha' in respuesta.data['mensaje'].lower()

    def test_acepta_la_fecha_de_hoy(self, api, url_reservas, payload_valido):
        """Frontera: hoy no es pasado, debe permitirse."""
        payload_valido['UMG_Fecha_Reserva'] = date.today().isoformat()

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 201

    @pytest.mark.parametrize(
        'fecha_invalida', ['31-12-2026', '2026/12/31', 'manana', '', '2026-13-45']
    )
    def test_rechaza_formatos_de_fecha_invalidos(
        self, api, url_reservas, payload_valido, fecha_invalida
    ):
        payload_valido['UMG_Fecha_Reserva'] = fecha_invalida

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 400
        assert Reserva.objects.count() == 0


# --------------------------------------------------------------------------- #
# Escenario 5 - Duracion mayor a la permitida                                  #
# --------------------------------------------------------------------------- #

class TestEscenario5DuracionExcedida:
    """
    Dado    que el bloque horario solicitado excede las 4 horas continuas en un
            mismo dia
    Cuando  envia la solicitud de creacion de la reserva
    Entonces el sistema rechaza la operacion con HTTP 400 e informa la duracion
            maxima permitida.

    Verifica: RN-011
    """

    def test_acepta_un_bloque_de_exactamente_4_horas(
        self, api, url_reservas, payload_valido
    ):
        """Frontera inferior: 4 horas justas si deben permitirse."""
        payload_valido['UMG_Hora_Inicio'] = '08:00'
        payload_valido['UMG_Hora_Fin'] = '12:00'

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 201

    @pytest.mark.parametrize(
        'inicio, fin, horas',
        [
            ('08:00', '12:01', '4h 1min'),
            ('08:00', '14:00', '6h'),
            ('07:00', '22:00', '15h'),
        ],
    )
    def test_rechaza_bloques_de_mas_de_4_horas(
        self, api, url_reservas, payload_valido, inicio, fin, horas
    ):
        payload_valido['UMG_Hora_Inicio'] = inicio
        payload_valido['UMG_Hora_Fin'] = fin

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 400, f'Se acepto un bloque de {horas}'
        assert Reserva.objects.count() == 0

    def test_rechaza_hora_de_inicio_posterior_a_la_de_fin(
        self, api, url_reservas, payload_valido
    ):
        payload_valido['UMG_Hora_Inicio'] = '14:00'
        payload_valido['UMG_Hora_Fin'] = '10:00'

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 400
        assert Reserva.objects.count() == 0

    def test_rechaza_un_bloque_de_duracion_cero(
        self, api, url_reservas, payload_valido
    ):
        payload_valido['UMG_Hora_Inicio'] = '10:00'
        payload_valido['UMG_Hora_Fin'] = '10:00'

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 400
        assert Reserva.objects.count() == 0


# --------------------------------------------------------------------------- #
# Escenario 6 - Horario fuera del rango de operacion                           #
# --------------------------------------------------------------------------- #

class TestEscenario6HorarioFueraDeRango:
    """
    Dado    que el bloque horario solicitado se encuentra fuera del horario
            habil de la facultad (07:00 a 22:00)
    Cuando  envia la solicitud de creacion de la reserva
    Entonces el sistema rechaza la operacion con HTTP 400 e informa el horario
            de operacion permitido.

    Verifica: RN-012
    """

    @pytest.mark.parametrize(
        'inicio, fin, caso',
        [
            ('07:00', '09:00', 'frontera inferior exacta'),
            ('20:00', '22:00', 'frontera superior exacta'),
            ('12:00', '15:00', 'dentro del rango'),
        ],
    )
    def test_acepta_bloques_dentro_del_horario_habil(
        self, api, url_reservas, payload_valido, inicio, fin, caso
    ):
        payload_valido['UMG_Hora_Inicio'] = inicio
        payload_valido['UMG_Hora_Fin'] = fin

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 201, f'Se rechazo un bloque valido: {caso}'

    @pytest.mark.parametrize(
        'inicio, fin, caso',
        [
            ('06:00', '08:00', 'inicia antes de las 07:00'),
            ('21:00', '23:30', 'termina despues de las 22:00'),
            ('05:00', '06:00', 'completamente antes del horario habil'),
            ('23:00', '23:59', 'completamente despues del horario habil'),
        ],
    )
    def test_rechaza_bloques_fuera_del_horario_habil(
        self, api, url_reservas, payload_valido, inicio, fin, caso
    ):
        payload_valido['UMG_Hora_Inicio'] = inicio
        payload_valido['UMG_Hora_Fin'] = fin

        respuesta = api.post(url_reservas, payload_valido, format='json')

        assert respuesta.status_code == 400, f'Se acepto un bloque invalido: {caso}'
        assert Reserva.objects.count() == 0
