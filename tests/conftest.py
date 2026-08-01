"""
Fixtures compartidas por toda la suite de pruebas.

pytest inyecta estas funciones en cualquier prueba que las declare como
parametro. La fixture 'db' de pytest-django envuelve cada prueba en una
transaccion que se revierte al terminar, por lo que las pruebas quedan aisladas
entre si y el orden de ejecucion no importa.
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from labs.models import Lab
from usuarios.models import Rol, Usuario


# --------------------------------------------------------------------------- #
# Cliente HTTP                                                                 #
# --------------------------------------------------------------------------- #

@pytest.fixture
def api():
    """Cliente que recorre el stack real de DRF: URLconf, vista, ORM."""
    return APIClient()


@pytest.fixture
def url_reservas():
    return reverse('reservas-list-create')


# --------------------------------------------------------------------------- #
# Catalogos base                                                               #
# --------------------------------------------------------------------------- #

@pytest.fixture
def rol_docente(db):
    return Rol.objects.create(
        umg_nombre='Docente',
        umg_descripcion='Personal academico que reserva laboratorios',
    )


@pytest.fixture
def rol_admin(db):
    return Rol.objects.create(
        umg_nombre='Admin',
        umg_descripcion='Gestion global de reservas y auditoria',
    )


@pytest.fixture
def docente(rol_docente):
    return Usuario.objects.create(
        umg_usuario='jperez@umg.edu.gt',
        umg_contrasena='hash-de-prueba',
        umg_nombre='Juan',
        umg_apellido='Perez',
        umg_rol=rol_docente,
        umg_estado=1,
    )


@pytest.fixture
def otro_docente(rol_docente):
    return Usuario.objects.create(
        umg_usuario='mlopez@umg.edu.gt',
        umg_contrasena='hash-de-prueba',
        umg_nombre='Maria',
        umg_apellido='Lopez',
        umg_rol=rol_docente,
        umg_estado=1,
    )


@pytest.fixture
def administrador(rol_admin):
    return Usuario.objects.create(
        umg_usuario='admin@umg.edu.gt',
        umg_contrasena='hash-de-prueba',
        umg_nombre='Ana',
        umg_apellido='Morales',
        umg_rol=rol_admin,
        umg_estado=1,
    )


@pytest.fixture
def docente_inactivo(rol_docente):
    return Usuario.objects.create(
        umg_usuario='inactivo@umg.edu.gt',
        umg_contrasena='hash-de-prueba',
        umg_nombre='Carlos',
        umg_apellido='Ramirez',
        umg_rol=rol_docente,
        umg_estado=0,
    )


@pytest.fixture
def lab(db):
    return Lab.objects.create(umg_nombre='Lab Redes 1', umg_estado=1)


@pytest.fixture
def otro_lab(db):
    return Lab.objects.create(umg_nombre='Lab Software 2', umg_estado=1)


@pytest.fixture
def lab_inactivo(db):
    return Lab.objects.create(umg_nombre='Lab Clausurado', umg_estado=0)


# --------------------------------------------------------------------------- #
# Datos de reserva                                                             #
# --------------------------------------------------------------------------- #

@pytest.fixture
def fecha_futura():
    """Una semana adelante: evita cualquier ambiguedad de zona horaria."""
    return date.today() + timedelta(days=7)


@pytest.fixture
def fecha_pasada():
    """
    Una semana atras. Se usa para montar reservas cuya hora de inicio ya
    transcurrio (HU-007 escenario 3, HU-008 escenario 2). Solo se crean por ORM:
    el endpoint de creacion las rechaza, que es justamente lo que verifica
    HU-001 escenario 4.
    """
    return date.today() - timedelta(days=7)


@pytest.fixture
def payload_valido(docente, lab, fecha_futura):
    """
    Cuerpo minimo que satisface todos los criterios de HU-001 escenario 1:
    docente activo, laboratorio activo, fecha futura, bloque de 2 horas dentro
    del horario habil (07:00-22:00) y motivo presente.
    """
    return {
        'UMG_User_ID': docente.umg_id,
        'UMG_Lab_ID': lab.umg_id,
        'UMG_Fecha_Reserva': fecha_futura.isoformat(),
        'UMG_Hora_Inicio': '08:00',
        'UMG_Hora_Fin': '10:00',
        'UMG_Motivo': 'Practica de configuracion de routers',
    }


@pytest.fixture
def crear_reserva(db):
    """
    Fabrica de reservas directamente en el ORM, sin pasar por la API.

    Se usa para montar el estado previo ("Dado que...") de un escenario sin
    depender del endpoint que justamente se esta probando.
    """
    from reservas.models import Reserva

    def _crear(docente, lab, fecha, hora_inicio='08:00', hora_fin='10:00',
               estado='R', motivo='Reserva preexistente'):
        return Reserva.objects.create(
            umg_user=docente,
            umg_lab=lab,
            umg_fecha_reserva=fecha,
            umg_hora_inicio=hora_inicio,
            umg_hora_fin=hora_fin,
            umg_motivo=motivo,
            umg_estado=estado,
        )

    return _crear
