from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Condicion


class CondicionListSerializer(serializers.ModelSerializer):
    UMG_ID = serializers.IntegerField(source='umg_id', read_only=True)
    UMG_Lab_ID = serializers.SerializerMethodField()
    UMG_Lab_Nombre = serializers.SerializerMethodField()
    UMG_Fecha = serializers.DateField(source='umg_fecha', read_only=True)
    UMG_Hora_Inicio = serializers.TimeField(source='umg_hora_inicio', read_only=True)
    UMG_Hora_Fin = serializers.TimeField(source='umg_hora_fin', read_only=True)
    UMG_Tipo = serializers.CharField(source='umg_tipo', read_only=True)
    UMG_Motivo = serializers.CharField(source='umg_motivo', read_only=True)
    UMG_Estado = serializers.IntegerField(source='umg_estado', read_only=True)
    UMG_Fecha_Registro = serializers.DateTimeField(source='umg_fecha_registro', read_only=True)

    class Meta:
        model = Condicion
        fields = [
            'UMG_ID', 'UMG_Lab_ID', 'UMG_Lab_Nombre', 'UMG_Fecha',
            'UMG_Hora_Inicio', 'UMG_Hora_Fin', 'UMG_Tipo', 'UMG_Motivo',
            'UMG_Estado', 'UMG_Fecha_Registro'
        ]

    @extend_schema_field(int)
    def get_UMG_Lab_ID(self, obj):
        return obj.umg_lab.umg_id if obj.umg_lab else None

    @extend_schema_field(str)
    def get_UMG_Lab_Nombre(self, obj):
        return obj.umg_lab.umg_nombre if obj.umg_lab else "Todos los laboratorios"