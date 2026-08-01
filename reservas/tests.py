from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from datetime import date, time, timedelta
from unittest.mock import patch
from usuarios.models import Rol, Usuario
from labs.models import Lab
from reservas.models import Reserva
from condiciones.models import Condicion


class ReservaModificarTestCase(TestCase):
    """Pruebas unitarias para PUT /api/reservas/<pk>/modificar/"""

    def setUp(self):
        self.client = APIClient()

        # Crear rol y usuario activo
        self.rol = Rol.objects.create(umg_nombre='Docente', umg_estado=1)
        self.rol_admin = Rol.objects.create(umg_nombre='Administrador', umg_estado=1)
        self.usuario = Usuario.objects.create(
            umg_usuario='docente@umg.edu.gt',
            umg_contrasena='Test1234',
            umg_nombre='Juan',
            umg_apellido='Perez',
            umg_rol=self.rol,
            umg_estado=1
        )
        self.usuario2 = Usuario.objects.create(
            umg_usuario='docente2@umg.edu.gt',
            umg_contrasena='Test1234',
            umg_nombre='Maria',
            umg_apellido='Lopez',
            umg_rol=self.rol,
            umg_estado=1
        )
        self.usuario_admin = Usuario.objects.create(
            umg_usuario='admin@umg.edu.gt',
            umg_contrasena='Test1234',
            umg_nombre='Admin',
            umg_apellido='Sistema',
            umg_rol=self.rol_admin,
            umg_estado=1
        )
        self.usuario_inactivo = Usuario.objects.create(
            umg_usuario='inactivo@umg.edu.gt',
            umg_contrasena='Test1234',
            umg_nombre='Pedro',
            umg_apellido='Gomez',
            umg_rol=self.rol,
            umg_estado=0
        )

        # Crear laboratorios
        self.lab = Lab.objects.create(umg_nombre='Lab A', umg_estado=1)
        self.lab2 = Lab.objects.create(umg_nombre='Lab B', umg_estado=1)
        self.lab_inactivo = Lab.objects.create(umg_nombre='Lab Inactivo', umg_estado=0)

        # Fecha futura para reservas validas
        self.fecha_futura = (date.today() + timedelta(days=7)).isoformat()
        self.fecha_pasada = (date.today() - timedelta(days=1)).isoformat()

        # Crear reserva activa en el futuro
        self.reserva = Reserva.objects.create(
            umg_user=self.usuario,
            umg_lab=self.lab,
            umg_fecha_reserva=date.today() + timedelta(days=7),
            umg_hora_inicio=time(8, 0),
            umg_hora_fin=time(10, 0),
            umg_motivo='Practica original',
            umg_estado='R'
        )

        # Datos validos para modificacion
        self.datos_validos = {
            'UMG_User_ID': self.usuario.umg_id,
            'UMG_Lab_ID': self.lab.umg_id,
            'UMG_Fecha_Reserva': self.fecha_futura,
            'UMG_Hora_Inicio': '10:00',
            'UMG_Hora_Fin': '12:00',
            'UMG_Motivo': 'Practica modificada',
            'UMG_Solicitante_ID': self.usuario.umg_id # Creador
        }

    def _url(self, pk):
        return f'/api/reservas/{pk}/modificar/'

    # ─── Caso exitoso ──────────────────────────────────────────────

    def test_modificacion_valida_retorna_200(self):
        """Modificacion valida antes del inicio retorna HTTP 200."""
        response = self.client.put(self._url(self.reserva.pk), self.datos_validos, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_modificacion_valida_actualiza_datos(self):
        """Los datos de la reserva se actualizan correctamente."""
        self.client.put(self._url(self.reserva.pk), self.datos_validos, format='json')
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.umg_hora_inicio, time(10, 0))
        self.assertEqual(self.reserva.umg_hora_fin, time(12, 0))
        self.assertEqual(self.reserva.umg_motivo, 'Practica modificada')

    def test_modificacion_valida_retorna_datos_serializados(self):
        """La respuesta contiene los datos serializados de la reserva."""
        response = self.client.put(self._url(self.reserva.pk), self.datos_validos, format='json')
        data = response.json()
        self.assertIn('UMG_ID', data)
        self.assertIn('UMG_Hora_Inicio', data)
        self.assertIn('UMG_Motivo', data)
        self.assertEqual(data['UMG_Motivo'], 'Practica modificada')

    def test_modificacion_valida_registra_log(self):
        """La operacion queda registrada en el historial de auditoria."""
        from logs.models import LogEntry
        count_antes = LogEntry.objects.filter(umg_accion='MODIFICAR_RESERVA').count()
        self.client.put(self._url(self.reserva.pk), self.datos_validos, format='json')
        count_despues = LogEntry.objects.filter(umg_accion='MODIFICAR_RESERVA').count()
        self.assertEqual(count_despues, count_antes + 1)

    def test_modificacion_cambiar_laboratorio(self):
        """Se puede cambiar el laboratorio de la reserva."""
        datos = self.datos_validos.copy()
        datos['UMG_Lab_ID'] = self.lab2.umg_id
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.umg_lab_id, self.lab2.umg_id)

    def test_modificacion_cambiar_docente(self):
        """Se puede cambiar el docente asignado a la reserva."""
        datos = self.datos_validos.copy()
        datos['UMG_User_ID'] = self.usuario2.umg_id
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.umg_user_id, self.usuario2.umg_id)

    # ─── Reserva no existe ─────────────────────────────────────────

    def test_reserva_no_existe_retorna_404(self):
        """Retorna 404 si la reserva no existe."""
        response = self.client.put(self._url(99999), self.datos_validos, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ─── Estado no activo ──────────────────────────────────────────

    def test_reserva_cancelada_retorna_409(self):
        """No se puede modificar una reserva cancelada."""
        self.reserva.umg_estado = 'C'
        self.reserva.save()
        response = self.client.put(self._url(self.reserva.pk), self.datos_validos, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('estado activo', response.json()['mensaje'])

    # ─── Actividad ya iniciada ─────────────────────────────────────

    def test_actividad_ya_iniciada_retorna_409(self):
        """No se puede modificar una reserva cuya actividad ya inicio."""
        self.reserva.umg_fecha_reserva = date.today()
        self.reserva.umg_hora_inicio = time(0, 0)
        self.reserva.save()
        response = self.client.put(self._url(self.reserva.pk), self.datos_validos, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('ya ha iniciado', response.json()['mensaje'])

    # ─── Validaciones de datos ─────────────────────────────────────

    def test_fecha_invalida_retorna_400(self):
        """Retorna 400 si la fecha tiene formato invalido."""
        datos = self.datos_validos.copy()
        datos['UMG_Fecha_Reserva'] = 'no-es-fecha'
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_fecha_pasada_retorna_400(self):
        """Retorna 400 si se intenta mover a una fecha pasada."""
        datos = self.datos_validos.copy()
        datos['UMG_Fecha_Reserva'] = self.fecha_pasada
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('fecha pasada', response.json()['mensaje'])

    def test_hora_inicio_mayor_a_fin_retorna_400(self):
        """Retorna 400 si hora_inicio >= hora_fin."""
        datos = self.datos_validos.copy()
        datos['UMG_Hora_Inicio'] = '14:00'
        datos['UMG_Hora_Fin'] = '10:00'
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_hora_inicio_igual_a_fin_retorna_400(self):
        """Retorna 400 si hora_inicio == hora_fin."""
        datos = self.datos_validos.copy()
        datos['UMG_Hora_Inicio'] = '10:00'
        datos['UMG_Hora_Fin'] = '10:00'
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_motivo_vacio_retorna_400(self):
        """Retorna 400 si el motivo esta vacio."""
        datos = self.datos_validos.copy()
        datos['UMG_Motivo'] = ''
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_motivo_solo_espacios_retorna_400(self):
        """Retorna 400 si el motivo es solo espacios en blanco."""
        datos = self.datos_validos.copy()
        datos['UMG_Motivo'] = '   '
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ─── Validaciones de entidades ─────────────────────────────────

    def test_docente_inexistente_retorna_400(self):
        """Retorna 400 si el docente no existe."""
        datos = self.datos_validos.copy()
        datos['UMG_User_ID'] = 99999
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('docente', response.json()['mensaje'].lower())

    def test_docente_inactivo_retorna_400(self):
        """Retorna 400 si el docente esta inactivo."""
        datos = self.datos_validos.copy()
        datos['UMG_User_ID'] = self.usuario_inactivo.umg_id
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_laboratorio_inexistente_retorna_400(self):
        """Retorna 400 si el laboratorio no existe."""
        datos = self.datos_validos.copy()
        datos['UMG_Lab_ID'] = 99999
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('laboratorio', response.json()['mensaje'].lower())

    def test_laboratorio_inactivo_retorna_400(self):
        """Retorna 400 si el laboratorio esta inactivo."""
        datos = self.datos_validos.copy()
        datos['UMG_Lab_ID'] = self.lab_inactivo.umg_id
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ─── Conflictos de disponibilidad ──────────────────────────────

    def test_traslape_con_otra_reserva_retorna_409(self):
        """Retorna 409 si hay traslape con otra reserva activa."""
        # Crear otra reserva que ocupa 10:00-12:00 en el mismo lab y fecha
        Reserva.objects.create(
            umg_user=self.usuario2,
            umg_lab=self.lab,
            umg_fecha_reserva=date.today() + timedelta(days=7),
            umg_hora_inicio=time(10, 0),
            umg_hora_fin=time(12, 0),
            umg_motivo='Otra practica',
            umg_estado='R'
        )
        response = self.client.put(self._url(self.reserva.pk), self.datos_validos, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('traslapa', response.json()['mensaje'])

    def test_sin_traslape_si_otra_reserva_cancelada(self):
        """No hay conflicto si la otra reserva esta cancelada."""
        Reserva.objects.create(
            umg_user=self.usuario2,
            umg_lab=self.lab,
            umg_fecha_reserva=date.today() + timedelta(days=7),
            umg_hora_inicio=time(10, 0),
            umg_hora_fin=time(12, 0),
            umg_motivo='Reserva cancelada',
            umg_estado='C'
        )
        response = self.client.put(self._url(self.reserva.pk), self.datos_validos, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_sin_autotraslape(self):
        """La reserva no se traslapa consigo misma (excluir_id funciona)."""
        # Modificar la reserva manteniendo el mismo horario pero cambiando motivo
        datos = self.datos_validos.copy()
        datos['UMG_Hora_Inicio'] = '08:00'
        datos['UMG_Hora_Fin'] = '10:00'
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_traslape_en_otro_lab_no_afecta(self):
        """Una reserva en otro laboratorio no causa conflicto."""
        Reserva.objects.create(
            umg_user=self.usuario2,
            umg_lab=self.lab2,
            umg_fecha_reserva=date.today() + timedelta(days=7),
            umg_hora_inicio=time(10, 0),
            umg_hora_fin=time(12, 0),
            umg_motivo='En otro lab',
            umg_estado='R'
        )
        response = self.client.put(self._url(self.reserva.pk), self.datos_validos, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_bloqueo_en_horario_retorna_409(self):
        """Retorna 409 si hay un bloqueo activo en el horario solicitado."""
        Condicion.objects.create(
            umg_lab=self.lab,
            umg_fecha=date.today() + timedelta(days=7),
            umg_hora_inicio=time(9, 0),
            umg_hora_fin=time(11, 0),
            umg_tipo='Mantenimiento',
            umg_motivo='Mantenimiento programado',
            umg_estado=1
        )
        response = self.client.put(self._url(self.reserva.pk), self.datos_validos, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('bloqueo', response.json()['mensaje'])

    def test_bloqueo_global_retorna_409(self):
        """Retorna 409 si hay un bloqueo global (sin lab especifico)."""
        Condicion.objects.create(
            umg_lab=None,
            umg_fecha=date.today() + timedelta(days=7),
            umg_hora_inicio=time(10, 0),
            umg_hora_fin=time(12, 0),
            umg_tipo='Asueto',
            umg_motivo='Dia festivo',
            umg_estado=1
        )
        response = self.client.put(self._url(self.reserva.pk), self.datos_validos, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_bloqueo_inactivo_no_afecta(self):
        """Un bloqueo inactivo no genera conflicto."""
        Condicion.objects.create(
            umg_lab=self.lab,
            umg_fecha=date.today() + timedelta(days=7),
            umg_hora_inicio=time(10, 0),
            umg_hora_fin=time(12, 0),
            umg_tipo='Mantenimiento',
            umg_motivo='Mantenimiento cancelado',
            umg_estado=0
        )
        response = self.client.put(self._url(self.reserva.pk), self.datos_validos, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ─── Preservacion de estado ────────────────────────────────────

    def test_estado_no_cambia_despues_de_modificar(self):
        """El estado de la reserva permanece 'R' despues de la modificacion."""
        self.client.put(self._url(self.reserva.pk), self.datos_validos, format='json')
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.umg_estado, 'R')

    # ─── Pruebas de Autorización (Permisos) ─────────────────────────

    def test_modificacion_por_admin_exito(self):
        """Administrador tiene permisos para modificar la reserva de otro docente."""
        datos = self.datos_validos.copy()
        datos['UMG_Solicitante_ID'] = self.usuario_admin.umg_id # Rol Administrador
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_modificacion_por_no_autorizado_retorna_403(self):
        """Rechaza la modificacion con 403 Forbidden si el solicitante no es creador ni admin."""
        datos = self.datos_validos.copy()
        datos['UMG_Solicitante_ID'] = self.usuario2.umg_id # Rol Docente, no creador
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('No tiene permisos', response.json()['mensaje'])

    def test_modificacion_sin_solicitante_id_retorna_400(self):
        """Retorna 400 si no se envia el ID del solicitante para validar permisos."""
        datos = self.datos_validos.copy()
        del datos['UMG_Solicitante_ID']
        response = self.client.put(self._url(self.reserva.pk), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('ID del solicitante es obligatorio', response.json()['mensaje'])


class ReservaCancelarTestCase(TestCase):
    """Pruebas unitarias para PATCH /api/reservas/<pk>/cancelar/"""

    def setUp(self):
        self.client = APIClient()

        # Crear rol y usuarios
        self.rol = Rol.objects.create(umg_nombre='Docente', umg_estado=1)
        self.rol_admin = Rol.objects.create(umg_nombre='Administrador', umg_estado=1)
        self.usuario = Usuario.objects.create(
            umg_usuario='docente@umg.edu.gt',
            umg_contrasena='Test1234',
            umg_nombre='Juan',
            umg_apellido='Perez',
            umg_rol=self.rol,
            umg_estado=1
        )
        self.usuario2 = Usuario.objects.create(
            umg_usuario='docente2@umg.edu.gt',
            umg_contrasena='Test1234',
            umg_nombre='Maria',
            umg_apellido='Lopez',
            umg_rol=self.rol,
            umg_estado=1
        )
        self.usuario_admin = Usuario.objects.create(
            umg_usuario='admin@umg.edu.gt',
            umg_contrasena='Test1234',
            umg_nombre='Admin',
            umg_apellido='Sistema',
            umg_rol=self.rol_admin,
            umg_estado=1
        )

        # Crear laboratorio
        self.lab = Lab.objects.create(umg_nombre='Lab A', umg_estado=1)

        # Crear reserva activa en el futuro
        self.reserva_futura = Reserva.objects.create(
            umg_user=self.usuario,
            umg_lab=self.lab,
            umg_fecha_reserva=date.today() + timedelta(days=7),
            umg_hora_inicio=time(8, 0),
            umg_hora_fin=time(10, 0),
            umg_motivo='Clase del futuro',
            umg_estado='R'
        )

        # Crear reserva que ya inicio en el pasado/hoy temprano
        self.reserva_iniciada = Reserva.objects.create(
            umg_user=self.usuario,
            umg_lab=self.lab,
            umg_fecha_reserva=date.today(),
            umg_hora_inicio=time(0, 0),  # Ya transcurrió
            umg_hora_fin=time(2, 0),
            umg_motivo='Clase del pasado',
            umg_estado='R'
        )

    def _url(self, pk):
        return f'/api/reservas/{pk}/cancelar/'

    def test_cancelacion_antes_del_inicio_exito(self):
        """Docente creador puede cancelar una reserva activa antes de la hora de inicio (HTTP 200)."""
        response = self.client.patch(self._url(self.reserva_futura.pk), HTTP_X_USER_ID=self.usuario.umg_id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.reserva_futura.refresh_from_db()
        self.assertEqual(self.reserva_futura.umg_estado, 'C')

    def test_cancelacion_despues_del_inicio_error(self):
        """Rechaza la operacion si la hora de inicio de la actividad ya transcurrio (HTTP 409)."""
        response = self.client.patch(self._url(self.reserva_iniciada.pk), HTTP_X_USER_ID=self.usuario.umg_id)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('ya ha iniciado', response.json()['mensaje'])
        self.reserva_iniciada.refresh_from_db()
        self.assertEqual(self.reserva_iniciada.umg_estado, 'R')  # Permanece sin cambios

    # ─── Pruebas de Autorización (Permisos) ─────────────────────────

    def test_cancelacion_por_admin_exito(self):
        """Administrador tiene permisos para cancelar la reserva de otro docente."""
        response = self.client.patch(self._url(self.reserva_futura.pk), HTTP_X_USER_ID=self.usuario_admin.umg_id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.reserva_futura.refresh_from_db()
        self.assertEqual(self.reserva_futura.umg_estado, 'C')

    def test_cancelacion_por_no_autorizado_retorna_403(self):
        """Rechaza la cancelacion con 403 Forbidden si el solicitante no es creador ni admin."""
        response = self.client.patch(self._url(self.reserva_futura.pk), HTTP_X_USER_ID=self.usuario2.umg_id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('No tiene permisos', response.json()['mensaje'])
        self.reserva_futura.refresh_from_db()
        self.assertEqual(self.reserva_futura.umg_estado, 'R') # Permanece sin cambios

    def test_cancelacion_sin_solicitante_id_retorna_400(self):
        """Retorna 400 si no se envia el ID del solicitante para validar permisos."""
        response = self.client.patch(self._url(self.reserva_futura.pk))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('ID del solicitante es obligatorio', response.json()['mensaje'])


class ReservaListCreateDetalleTestCase(TestCase):
    """Pruebas unitarias para listar, crear y obtener detalle de reservas."""

    def setUp(self):
        self.client = APIClient()

        # Crear rol y usuarios
        self.rol = Rol.objects.create(umg_nombre='Docente', umg_estado=1)
        self.usuario = Usuario.objects.create(
            umg_usuario='docente@umg.edu.gt',
            umg_contrasena='Test1234',
            umg_nombre='Juan',
            umg_apellido='Perez',
            umg_rol=self.rol,
            umg_estado=1
        )
        self.usuario2 = Usuario.objects.create(
            umg_usuario='docente2@umg.edu.gt',
            umg_contrasena='Test1234',
            umg_nombre='Maria',
            umg_apellido='Lopez',
            umg_rol=self.rol,
            umg_estado=1
        )

        # Crear laboratorios
        self.lab = Lab.objects.create(umg_nombre='Lab A', umg_estado=1)
        self.lab2 = Lab.objects.create(umg_nombre='Lab B', umg_estado=1)

        # Fecha futura
        self.fecha_futura = date.today() + timedelta(days=5)

        # Crear algunas reservas iniciales
        self.reserva1 = Reserva.objects.create(
            umg_user=self.usuario,
            umg_lab=self.lab,
            umg_fecha_reserva=self.fecha_futura,
            umg_hora_inicio=time(8, 0),
            umg_hora_fin=time(10, 0),
            umg_motivo='Clase de Matematica',
            umg_estado='R'
        )
        self.reserva2 = Reserva.objects.create(
            umg_user=self.usuario2,
            umg_lab=self.lab2,
            umg_fecha_reserva=self.fecha_futura,
            umg_hora_inicio=time(10, 0),
            umg_hora_fin=time(12, 0),
            umg_motivo='Clase de Fisica',
            umg_estado='R'
        )

    def _url_list_create(self):
        return '/api/reservas/'

    def _url_detalle(self, pk):
        return f'/api/reservas/{pk}/'

    # ─── Listar Reservas ───────────────────────────────────────────

    def test_listar_todas_las_reservas(self):
        """Retorna lista de todas las reservas de la base de datos."""
        response = self.client.get(self._url_list_create())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 2)

    def test_listar_filtrado_por_laboratorio(self):
        """Filtra la lista de reservas por laboratorio."""
        response = self.client.get(self._url_list_create(), {'labId': self.lab.umg_id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['UMG_Lab_ID'], self.lab.umg_id)

    def test_listar_filtrado_por_fecha(self):
        """Filtra la lista de reservas por fecha."""
        response = self.client.get(self._url_list_create(), {'fecha': self.fecha_futura.isoformat()})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 2)

        # Filtrar con fecha diferente
        fecha_diferente = date.today() + timedelta(days=10)
        response_dif = self.client.get(self._url_list_create(), {'fecha': fecha_diferente.isoformat()})
        self.assertEqual(len(response_dif.json()), 0)

    def test_listar_filtrado_por_usuario(self):
        """Filtra la lista de reservas por usuario."""
        response = self.client.get(self._url_list_create(), {'userId': self.usuario.umg_id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['UMG_User_ID'], self.usuario.umg_id)

    # ─── Crear Reservas ────────────────────────────────────────────

    def test_crear_reserva_exitosa(self):
        """Creacion exitosa de una reserva valida."""
        datos = {
            'UMG_User_ID': self.usuario.umg_id,
            'UMG_Lab_ID': self.lab.umg_id,
            'UMG_Fecha_Reserva': (date.today() + timedelta(days=3)).isoformat(),
            'UMG_Hora_Inicio': '14:00:00',
            'UMG_Hora_Fin': '16:00:00',
            'UMG_Motivo': 'Clase de Programacion 1'
        }
        response = self.client.post(self._url_list_create(), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Reserva.objects.filter(umg_motivo='Clase de Programacion 1').exists())

    def test_crear_reserva_fecha_pasada_error(self):
        """No permite crear una reserva con fecha pasada."""
        datos = {
            'UMG_User_ID': self.usuario.umg_id,
            'UMG_Lab_ID': self.lab.umg_id,
            'UMG_Fecha_Reserva': (date.today() - timedelta(days=1)).isoformat(),
            'UMG_Hora_Inicio': '14:00:00',
            'UMG_Hora_Fin': '16:00:00',
            'UMG_Motivo': 'Fecha pasada'
        }
        response = self.client.post(self._url_list_create(), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('fecha pasada', response.json()['mensaje'])

    def test_crear_reserva_traslape_error(self):
        """No permite crear reservas que se traslapan en el mismo lab/horario."""
        datos = {
            'UMG_User_ID': self.usuario2.umg_id,
            'UMG_Lab_ID': self.lab.umg_id,
            'UMG_Fecha_Reserva': self.fecha_futura.isoformat(),
            'UMG_Hora_Inicio': '09:00:00', # Se traslapa con reserva1 (08:00-10:00)
            'UMG_Hora_Fin': '11:00:00',
            'UMG_Motivo': 'Clase traslapada'
        }
        response = self.client.post(self._url_list_create(), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('traslapa', response.json()['mensaje'])

    def test_crear_reserva_bloqueo_error(self):
        """No permite reservar un laboratorio que tiene un bloqueo activo."""
        Condicion.objects.create(
            umg_lab=self.lab,
            umg_fecha=self.fecha_futura,
            umg_hora_inicio=time(14, 0),
            umg_hora_fin=time(16, 0),
            umg_tipo='Mantenimiento',
            umg_motivo='Mantenimiento',
            umg_estado=1
        )
        datos = {
            'UMG_User_ID': self.usuario.umg_id,
            'UMG_Lab_ID': self.lab.umg_id,
            'UMG_Fecha_Reserva': self.fecha_futura.isoformat(),
            'UMG_Hora_Inicio': '14:30:00',
            'UMG_Hora_Fin': '15:30:00',
            'UMG_Motivo': 'Clase en bloqueo'
        }
        response = self.client.post(self._url_list_create(), datos, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('bloqueo', response.json()['mensaje'])

    # ─── Detalle Reserva ───────────────────────────────────────────

    def test_detalle_reserva_existente(self):
        """Obtiene la informacion detallada de una reserva especifica."""
        response = self.client.get(self._url_detalle(self.reserva1.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['UMG_ID'], self.reserva1.pk)
        self.assertEqual(data['UMG_Motivo'], self.reserva1.umg_motivo)

    def test_detalle_reserva_inexistente_retorna_404(self):
        """Retorna 404 si la reserva especificada no existe."""
        response = self.client.get(self._url_detalle(99999))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


