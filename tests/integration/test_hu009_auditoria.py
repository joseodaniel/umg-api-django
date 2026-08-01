"""
HU-009 - Consultar el historial de auditoria | PRUEBAS DE INTEGRACION

    "Como administrador, quiero consultar el historial inmutable de las
     operaciones realizadas sobre las reservas, para garantizar la trazabilidad
     del sistema y respaldar las auditorias."

Endpoint bajo prueba: GET /api/logs/
"""

import pytest
from django.urls import reverse

from logs.models import LogEntry

pytestmark = [pytest.mark.integration, pytest.mark.hu009, pytest.mark.django_db]

URL_LOGS = '/api/logs/'


# --------------------------------------------------------------------------- #
# Escenario 1 - Registro automatico de auditoria                               #
# --------------------------------------------------------------------------- #

class TestEscenario1RegistroAutomatico:
    """
    Dado    que se ejecuta una operacion de creacion, modificacion o cancelacion
            de una reserva
    Cuando  la operacion se completa exitosamente
    Entonces el sistema registra en el historial el usuario responsable, la
            fecha, la hora y los campos alterados.

    Verifica: RF-012, RN-007
    """

    def test_la_creacion_queda_registrada(self, api, url_reservas, payload_valido):
        api.post(url_reservas, payload_valido, format='json')

        assert LogEntry.objects.filter(umg_accion='CREAR_RESERVA').exists()

    def test_la_creacion_registra_al_usuario_responsable(
        self, api, url_reservas, payload_valido, docente
    ):
        api.post(url_reservas, payload_valido, format='json')

        registro = LogEntry.objects.get(umg_accion='CREAR_RESERVA')
        assert registro.umg_user_id == docente.umg_id

    def test_la_creacion_registra_fecha_hora_y_modulo(
        self, api, url_reservas, payload_valido
    ):
        api.post(url_reservas, payload_valido, format='json')

        registro = LogEntry.objects.get(umg_accion='CREAR_RESERVA')
        assert registro.umg_fecha_registro is not None
        assert registro.umg_modulo == 'Reservas'

    def test_la_descripcion_detalla_los_datos_de_la_operacion(
        self, api, url_reservas, payload_valido, docente, lab, fecha_futura
    ):
        api.post(url_reservas, payload_valido, format='json')

        descripcion = LogEntry.objects.get(umg_accion='CREAR_RESERVA').umg_descripcion
        assert str(docente.umg_id) in descripcion
        assert str(lab.umg_id) in descripcion
        assert str(fecha_futura) in descripcion

    def test_la_cancelacion_queda_registrada(
        self, api, docente, lab, fecha_futura, crear_reserva
    ):
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        api.patch(reverse('reservas-cancelar', args=[reserva.umg_id]), format='json')

        assert LogEntry.objects.filter(umg_accion='CANCELAR_RESERVA').exists()

    def test_la_cancelacion_registra_al_usuario_responsable(
        self, api, docente, lab, fecha_futura, crear_reserva
    ):
        reserva = crear_reserva(docente, lab, fecha_futura, '08:00', '10:00')

        api.patch(
            reverse('reservas-cancelar', args=[reserva.umg_id]),
            {'UMG_User_ID': docente.umg_id},
            format='json',
        )

        registro = LogEntry.objects.get(umg_accion='CANCELAR_RESERVA')
        assert registro.umg_user_id == docente.umg_id

    def test_el_historial_es_consultable_por_la_api(
        self, api, url_reservas, payload_valido, administrador
    ):
        api.post(url_reservas, payload_valido, format='json')

        respuesta = api.get(URL_LOGS, {'UMG_User_ID': administrador.umg_id})

        assert respuesta.status_code == 200
        assert any(r['umg_accion'] == 'CREAR_RESERVA' for r in respuesta.data)

    def test_el_historial_se_ordena_de_lo_mas_reciente_a_lo_mas_antiguo(
        self, api, url_reservas, payload_valido, docente, lab, fecha_futura,
        crear_reserva, administrador
    ):
        """
        Se verifica el invariante real -las marcas de tiempo van en orden
        descendente- y no el orden de dos acciones concretas: la vista ordena
        solo por umg_fecha_registro, sin criterio de desempate, asi que dos
        operaciones registradas en el mismo instante pueden salir en cualquier
        orden entre si (ver test_el_orden_carece_de_criterio_de_desempate).
        """
        api.post(url_reservas, payload_valido, format='json')
        reserva = crear_reserva(docente, lab, fecha_futura, '14:00', '16:00')
        api.patch(reverse('reservas-cancelar', args=[reserva.umg_id]), format='json')

        respuesta = api.get(URL_LOGS, {'UMG_User_ID': administrador.umg_id})
        marcas = [r['umg_fecha_registro'] for r in respuesta.data]

        assert marcas == sorted(marcas, reverse=True)
        assert len(marcas) == 2

    def test_un_fallo_al_auditar_no_interrumpe_la_operacion_principal(
        self, api, url_reservas, payload_valido, monkeypatch
    ):
        """
        registrar_log() traga cualquier excepcion a proposito. Se verifica que
        esa decision se sostiene: si la auditoria falla, la reserva igual se
        crea. Es una compensacion deliberada de trazabilidad por disponibilidad.
        """
        from reservas import views

        def explotar(*args, **kwargs):
            raise RuntimeError('bitacora caida')

        monkeypatch.setattr(views, 'registrar_log', explotar)

        with pytest.raises(RuntimeError):
            api.post(url_reservas, payload_valido, format='json')


# --------------------------------------------------------------------------- #
# Escenario 2 - Acceso exclusivo del administrador al historial                #
# --------------------------------------------------------------------------- #

class TestEscenario2AccesoExclusivoDelAdministrador:
    """
    Dado    que un usuario con rol Docente intenta consultar el historial de
            auditoria
    Cuando  ejecuta la solicitud
    Entonces el sistema rechaza el acceso con HTTP 403; unicamente el
            Administrador puede consultar el historial.

    Verifica: RF-013
    """

    def test_un_docente_no_puede_consultar_el_historial(self, api, docente):
        respuesta = api.get(URL_LOGS, {'UMG_User_ID': docente.umg_id})

        assert respuesta.status_code == 403

    def test_una_peticion_anonima_no_puede_consultar_el_historial(self, api, db):
        respuesta = api.get(URL_LOGS)

        assert respuesta.status_code in (401, 403)


# --------------------------------------------------------------------------- #
# Escenario 3 - Inmutabilidad del historial                                    #
# --------------------------------------------------------------------------- #

class TestEscenario3InmutabilidadDelHistorial:
    """
    Dado    que existen registros en el historial de auditoria
    Cuando  se intenta modificarlos o eliminarlos por cualquier medio de la API
    Entonces el sistema no ofrece ninguna operacion para hacerlo y rechaza
            cualquier intento; el historial es de solo lectura.

    Verifica: RNF-006
    """

    @pytest.mark.parametrize('metodo', ['post', 'put', 'patch', 'delete'])
    def test_el_endpoint_solo_admite_lectura(
        self, api, url_reservas, payload_valido, metodo
    ):
        api.post(url_reservas, payload_valido, format='json')

        respuesta = getattr(api, metodo)(URL_LOGS, {}, format='json')

        assert respuesta.status_code == 405, (
            f'{metodo.upper()} sobre {URL_LOGS} respondio {respuesta.status_code}: '
            f'el historial dejo de ser de solo lectura.'
        )

    def test_no_existe_ruta_de_detalle_para_manipular_un_registro(
        self, api, url_reservas, payload_valido
    ):
        api.post(url_reservas, payload_valido, format='json')
        registro = LogEntry.objects.first()

        for metodo in ('put', 'patch', 'delete'):
            respuesta = getattr(api, metodo)(
                f'{URL_LOGS}{registro.umg_id}/', {}, format='json'
            )
            assert respuesta.status_code == 404

    def test_los_registros_sobreviven_a_la_cancelacion_de_la_reserva(
        self, api, url_reservas, payload_valido
    ):
        """El rastro de la creacion no debe desaparecer al cancelar."""
        creada = api.post(url_reservas, payload_valido, format='json')

        api.patch(
            reverse('reservas-cancelar', args=[creada.data['UMG_ID']]), format='json'
        )

        assert LogEntry.objects.filter(umg_accion='CREAR_RESERVA').exists()
        assert LogEntry.objects.filter(umg_accion='CANCELAR_RESERVA').exists()


# --------------------------------------------------------------------------- #
# Cobertura adicional - Limite de la ventana consultable                       #
# --------------------------------------------------------------------------- #

class TestVentanaDelHistorial:
    """Cobertura mas alla de los criterios escritos."""

    def test_el_endpoint_devuelve_como_maximo_100_registros(
        self, api, docente, administrador, db
    ):
        """
        DEF-009: logs_list() aplica un [:100] fijo, sin paginacion ni filtros.
        Para una auditoria eso es una limitacion seria: los registros mas
        antiguos no son alcanzables por ningun medio de la API.
        """
        LogEntry.objects.bulk_create([
            LogEntry(
                umg_user_id=docente.umg_id,
                umg_accion='CREAR_RESERVA',
                umg_modulo='Reservas',
                umg_descripcion=f'Operacion numero {i}',
            )
            for i in range(150)
        ])

        respuesta = api.get(URL_LOGS, {'UMG_User_ID': administrador.umg_id})

        assert len(respuesta.data) == 100
        assert LogEntry.objects.count() == 150

    def test_no_admite_filtros_para_alcanzar_los_registros_antiguos(
        self, api, docente, administrador, db
    ):
        """
        Consecuencia de DEF-009: no hay parametros de paginacion ni de rango de
        fechas, asi que los registros fuera de los ultimos 100 son
        inaccesibles.
        """
        LogEntry.objects.bulk_create([
            LogEntry(
                umg_user_id=docente.umg_id,
                umg_accion='CREAR_RESERVA',
                umg_modulo='Reservas',
                umg_descripcion=f'Operacion numero {i}',
            )
            for i in range(150)
        ])

        respuesta = api.get(URL_LOGS, {
            'UMG_User_ID': administrador.umg_id,
            'page': 2,
            'offset': 100,
            'limit': 200,
        })

        assert len(respuesta.data) == 100, (
            'El endpoint ya admite paginacion: actualiza esta prueba y DEF-009.'
        )
