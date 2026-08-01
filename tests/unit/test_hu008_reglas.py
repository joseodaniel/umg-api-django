"""
HU-008 - Cancelar una reserva activa | PRUEBAS UNITARIAS

El escenario 3 de HU-008 exige rechazar con HTTP 403 a quien no sea el docente
creador ni un Administrador (RN-013). Esa comprobacion no existe (DEF-007), y no
hay funcion que aislar para probarla.

Lo que si se puede verificar en aislamiento es el dato sobre el que se apoyaria
cualquier control de acceso futuro: el contrato del usuario y su rol. Si el rol
no viaja resuelto, ni el backend ni el cliente pueden decidir nada.

Cobertura: RN-013 (contrato de datos), seguridad del contrato de usuario
"""

import pytest

from usuarios.serializers import UsuarioListSerializer

pytestmark = [pytest.mark.unit, pytest.mark.hu008]


class TestContratoDelUsuarioYSuRol:

    def test_expone_los_campos_del_contrato(self, docente):
        datos = UsuarioListSerializer(docente).data

        assert set(datos.keys()) == {
            'UMG_ID', 'UMG_Usuario', 'UMG_Nombre', 'UMG_Apellido',
            'UMG_Rol_ID', 'UMG_Rol_Nombre', 'UMG_Estado', 'UMG_Ingreso',
            'UMG_Fecha_Creacion', 'UMG_Ultimo_Acceso',
        }

    def test_resuelve_el_rol_a_su_nombre(self, docente, administrador):
        """
        RN-013 razona en terminos de roles ("ni posee el rol de Administrador"),
        asi que el nombre del rol tiene que estar disponible y no solo su
        identificador numerico.
        """
        assert UsuarioListSerializer(docente).data['UMG_Rol_Nombre'] == 'Docente'
        assert (
            UsuarioListSerializer(administrador).data['UMG_Rol_Nombre']
            == 'Admin'
        )

    def test_distingue_a_un_docente_de_un_administrador(self, docente, administrador):
        """La materia prima de la autorizacion que falta implementar."""
        datos_docente = UsuarioListSerializer(docente).data
        datos_admin = UsuarioListSerializer(administrador).data

        assert datos_docente['UMG_Rol_ID'] != datos_admin['UMG_Rol_ID']

    def test_el_correo_es_el_identificador_de_acceso(self, docente):
        datos = UsuarioListSerializer(docente).data

        assert datos['UMG_Usuario'] == 'jperez@umg.edu.gt'

    def test_distingue_a_los_usuarios_inactivos(self, docente, docente_inactivo):
        """Un usuario dado de baja no deberia poder cancelar nada."""
        assert UsuarioListSerializer(docente).data['UMG_Estado'] == 1
        assert UsuarioListSerializer(docente_inactivo).data['UMG_Estado'] == 0


class TestNoFiltracionDeCredenciales:
    """
    Barrera de seguridad, mas alla de los criterios escritos.

    Las contrasenas se guardan en texto plano y GET /api/usuarios/ es publico por
    la falta de autorizacion (ambos descritos en DEF-007). Si el serializer
    llegara a exponer el campo, las entregaria directamente a cualquiera. Estas
    pruebas existen para que agregarlo sea imposible sin que alguien lo note.
    """

    def test_ningun_campo_del_contrato_alude_a_la_contrasena(self, docente):
        datos = UsuarioListSerializer(docente).data

        for campo in datos:
            assert 'contrasena' not in campo.lower()
            assert 'password' not in campo.lower()

    def test_el_valor_de_la_contrasena_no_aparece_en_la_salida(self, docente):
        datos = UsuarioListSerializer(docente).data

        assert 'hash-de-prueba' not in str(datos)

    def test_tampoco_se_filtra_al_serializar_varios_usuarios(
        self, docente, otro_docente, administrador
    ):
        datos = UsuarioListSerializer(
            [docente, otro_docente, administrador], many=True
        ).data

        assert 'hash-de-prueba' not in str(datos)
