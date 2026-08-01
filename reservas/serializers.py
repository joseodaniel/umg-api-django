from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Reserva


class ReservaListSerializer(serializers.ModelSerializer):
    UMG_ID = serializers.IntegerField(source='umg_id', read_only=True)
    UMG_User_ID = serializers.IntegerField(source='umg_user.umg_id', read_only=True)
    UMG_Docente_Nombre = serializers.SerializerMethodField()
    UMG_Docente_Correo = serializers.CharField(source='umg_user.umg_usuario', read_only=True)
    UMG_Lab_ID = serializers.IntegerField(source='umg_lab.umg_id', read_only=True)
    UMG_Lab_Nombre = serializers.CharField(source='umg_lab.umg_nombre', read_only=True)
    UMG_Fecha_Reserva = serializers.DateField(source='umg_fecha_reserva', read_only=True)
    UMG_Hora_Inicio = serializers.TimeField(source='umg_hora_inicio', read_only=True)
    UMG_Hora_Fin = serializers.TimeField(source='umg_hora_fin', read_only=True)
    UMG_Motivo = serializers.CharField(source='umg_motivo', read_only=True)
    UMG_Estado = serializers.CharField(source='umg_estado', read_only=True)
    UMG_Fecha_Registro = serializers.DateTimeField(source='umg_fecha_registro', read_only=True)

    class Meta:
        model = Reserva
        fields = [
            'UMG_ID', 'UMG_User_ID', 'UMG_Docente_Nombre', 'UMG_Docente_Correo',
            'UMG_Lab_ID', 'UMG_Lab_Nombre', 'UMG_Fecha_Reserva', 'UMG_Hora_Inicio',
            'UMG_Hora_Fin', 'UMG_Motivo', 'UMG_Estado', 'UMG_Fecha_Registro'
        ]

    @extend_schema_field(str)
    def get_UMG_Docente_Nombre(self, obj):
        return "{0} {1}".format(obj.umg_user.umg_nombre, obj.umg_user.umg_apellido)