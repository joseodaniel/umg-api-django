from datetime import datetime

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Q

from .models import Lab
from .serializers import LabSerializer
from logs.utils import registrar_log
from reservas.models import Reserva
from condiciones.models import Condicion


@api_view(['GET', 'POST'])
def labs_list_create(request):
    if request.method == 'GET':
        labs = Lab.objects.all().order_by('umg_nombre')
        serializer = LabSerializer(labs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        nombre = request.data.get('UMG_Nombre', '').strip()

        if not nombre:
            return Response({'mensaje': 'El nombre del laboratorio es obligatorio.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(nombre) > 30:
            return Response({'mensaje': 'El nombre no puede superar los 30 caracteres.'}, status=status.HTTP_400_BAD_REQUEST)

        if Lab.objects.filter(umg_nombre=nombre).exists():
            return Response({'mensaje': f"Ya existe un laboratorio con el nombre '{nombre}'."}, status=status.HTTP_409_CONFLICT)

        lab = Lab.objects.create(umg_nombre=nombre)

        registrar_log(
            None,
            "CREAR_LABORATORIO",
            "Laboratorios",
            f"Se registró el laboratorio '{lab.umg_nombre}' con ID {lab.umg_id}."
        )

        serializer = LabSerializer(lab)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['PUT'])
def labs_update(request, pk):
    try:
        lab = Lab.objects.get(pk=pk)
    except Lab.DoesNotExist:
        return Response({'mensaje': 'El laboratorio especificado no existe.'}, status=status.HTTP_404_NOT_FOUND)

    nombre = request.data.get('UMG_Nombre', '').strip()
    estado = request.data.get('UMG_Estado')

    if not nombre:
        return Response({'mensaje': 'El nombre del laboratorio es obligatorio.'}, status=status.HTTP_400_BAD_REQUEST)

    if Lab.objects.filter(umg_nombre=nombre).exclude(pk=pk).exists():
        return Response({'mensaje': f"Ya existe otro laboratorio con el nombre '{nombre}'."}, status=status.HTTP_409_CONFLICT)

    lab.umg_nombre = nombre
    if estado is not None:
        lab.umg_estado = estado
    lab.save()

    registrar_log(
        None,
        "EDITAR_LABORATORIO",
        "Laboratorios",
        f"Se actualizó el laboratorio con ID {pk}."
    )

    return Response({'mensaje': 'Laboratorio actualizado correctamente.'}, status=status.HTTP_200_OK)


@api_view(['GET'])
def labs_disponibles(request):
    """
    Como docente, quiero consultar los laboratorios disponibles filtrando por
    fecha y horario, para elegir el espacio adecuado antes de registrar mi
    reserva.

    GET /api/labs/disponibles/?fecha=YYYY-MM-DD&hora_inicio=HH:MM&hora_fin=HH:MM
    """
    fecha_str = request.query_params.get('fecha')
    hora_inicio_str = request.query_params.get('hora_inicio')
    hora_fin_str = request.query_params.get('hora_fin')

    if not fecha_str:
        return Response({'mensaje': 'El parametro fecha es obligatorio.'}, status=status.HTTP_400_BAD_REQUEST)
    if not hora_inicio_str:
        return Response({'mensaje': 'El parametro hora_inicio es obligatorio.'}, status=status.HTTP_400_BAD_REQUEST)
    if not hora_fin_str:
        return Response({'mensaje': 'El parametro hora_fin es obligatorio.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return Response({'mensaje': 'El parametro fecha debe tener el formato YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        hora_inicio = datetime.strptime(hora_inicio_str, '%H:%M').time()
    except (ValueError, TypeError):
        return Response({'mensaje': 'El parametro hora_inicio debe tener el formato HH:MM.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        hora_fin = datetime.strptime(hora_fin_str, '%H:%M').time()
    except (ValueError, TypeError):
        return Response({'mensaje': 'El parametro hora_fin debe tener el formato HH:MM.'}, status=status.HTTP_400_BAD_REQUEST)

    if hora_inicio >= hora_fin:
        return Response({'mensaje': 'hora_inicio debe ser menor a hora_fin.'}, status=status.HTTP_400_BAD_REQUEST)

    # Un bloqueo sin laboratorio especifico (UMG_Lab_ID = NULL) aplica a todos.
    hay_bloqueo_general = Condicion.objects.filter(
        umg_lab__isnull=True,
        umg_fecha=fecha_obj,
        umg_estado=1,
        umg_hora_inicio__lt=hora_fin,
        umg_hora_fin__gt=hora_inicio,
    ).exists()

    if hay_bloqueo_general:
        return Response([], status=status.HTTP_200_OK)

    ocupados_ids = Reserva.objects.filter(
        umg_fecha_reserva=fecha_obj,
        umg_estado='R',
        umg_hora_inicio__lt=hora_fin,
        umg_hora_fin__gt=hora_inicio,
    ).values_list('umg_lab_id', flat=True)

    bloqueados_ids = Condicion.objects.filter(
        umg_lab__isnull=False,
        umg_fecha=fecha_obj,
        umg_estado=1,
        umg_hora_inicio__lt=hora_fin,
        umg_hora_fin__gt=hora_inicio,
    ).values_list('umg_lab_id', flat=True)

    labs_libres = (
        Lab.objects.filter(umg_estado=1)
        .exclude(pk__in=ocupados_ids)
        .exclude(pk__in=bloqueados_ids)
        .order_by('umg_nombre')
    )

    serializer = LabSerializer(labs_libres, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)