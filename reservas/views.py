from datetime import datetime

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Q
from datetime import datetime, date
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from .models import Reserva
from .serializers import ReservaListSerializer
from usuarios.models import Usuario
from labs.models import Lab
from condiciones.models import Condicion
from logs.utils import registrar_log


def hay_traslape(lab_id, fecha, hora_inicio, hora_fin, excluir_id=None):
    qs = Reserva.objects.filter(
        umg_lab_id=lab_id,
        umg_fecha_reserva=fecha,
        umg_estado='R',
        umg_hora_inicio__lt=hora_fin,
        umg_hora_fin__gt=hora_inicio
    )
    if excluir_id:
        qs = qs.exclude(pk=excluir_id)
    return qs.exists()


CAMPOS_REQUERIDOS_RESERVA = {
    'UMG_User_ID': 'el docente (UMG_User_ID)',
    'UMG_Lab_ID': 'el laboratorio (UMG_Lab_ID)',
    'UMG_Fecha_Reserva': 'la fecha de la reserva (UMG_Fecha_Reserva)',
    'UMG_Hora_Inicio': 'la hora de inicio (UMG_Hora_Inicio)',
    'UMG_Hora_Fin': 'la hora de fin (UMG_Hora_Fin)',
    'UMG_Motivo': 'el motivo (UMG_Motivo)',
}


def campo_faltante(request_data):
    for campo, etiqueta in CAMPOS_REQUERIDOS_RESERVA.items():
        valor = request_data.get(campo)
        if valor is None:
            return 'Falta {0}.'.format(etiqueta)
        if isinstance(valor, str) and not valor.strip():
            return 'Falta {0}.'.format(etiqueta)
    return None


def hay_bloqueo(lab_id, fecha, hora_inicio, hora_fin):
    return Condicion.objects.filter(
        Q(umg_lab_id=lab_id) | Q(umg_lab__isnull=True),
        umg_fecha=fecha,
        umg_estado=1,
        umg_hora_inicio__lt=hora_fin,
        umg_hora_fin__gt=hora_inicio
    ).exists()


def finalizar_vencidas():
    """
    Promueve a 'F' (Finalizada) toda reserva en estado 'R' cuyo bloque
    horario ya concluyo respecto al momento actual.

    Se ejecuta al inicio de cada consulta (GET), en vez de depender de una
    tarea programada externa: no hay ningun proceso en segundo plano, asi
    que la transicion se calcula "on read" y se persiste antes de responder.
    """
    ahora = timezone.localtime(timezone.now())
    tz_actual = timezone.get_current_timezone()

    candidatas = Reserva.objects.filter(
        umg_estado='R',
        umg_fecha_reserva__lte=ahora.date(),
    )

    vencidas_ids = [
        r.umg_id for r in candidatas
        if timezone.make_aware(
            datetime.combine(r.umg_fecha_reserva, r.umg_hora_fin), tz_actual
        ) <= ahora
    ]

    if vencidas_ids:
        Reserva.objects.filter(umg_id__in=vencidas_ids).update(umg_estado='F')

    return vencidas_ids


@extend_schema(methods=['GET'], operation_id='reservas_listar')
@extend_schema(methods=['POST'], operation_id='reservas_crear')
@api_view(['GET', 'POST'])
def reservas_list_create(request):
    if request.method == 'GET':
        finalizar_vencidas()

        lab_id = request.query_params.get('labId')
        fecha = request.query_params.get('fecha')
        user_id = request.query_params.get('userId')

        reservas = Reserva.objects.select_related('umg_user', 'umg_lab').all()

        if lab_id:
            reservas = reservas.filter(umg_lab_id=lab_id)
        if fecha:
            reservas = reservas.filter(umg_fecha_reserva=fecha)
        if user_id:
            reservas = reservas.filter(umg_user_id=user_id)

        reservas = reservas.order_by('-umg_fecha_reserva', 'umg_hora_inicio')
        serializer = ReservaListSerializer(reservas, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        mensaje_faltante = campo_faltante(request.data)
        if mensaje_faltante:
            return Response({'mensaje': mensaje_faltante}, status=status.HTTP_400_BAD_REQUEST)

        user_id = request.data.get('UMG_User_ID')
        lab_id = request.data.get('UMG_Lab_ID')
        fecha = request.data.get('UMG_Fecha_Reserva')
        hora_inicio_str = request.data.get('UMG_Hora_Inicio')
        hora_fin_str = request.data.get('UMG_Hora_Fin')
        motivo = request.data.get('UMG_Motivo', '').strip()

        try:
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return Response({'mensaje': 'La fecha proporcionada no es valida.'}, status=status.HTTP_400_BAD_REQUEST)

        if fecha_obj < timezone.localdate():
            return Response({'mensaje': 'No se puede crear una reserva para una fecha pasada.'}, status=status.HTTP_400_BAD_REQUEST)

        # Parsear horas a objetos time
        try:
            for fmt in ('%H:%M:%S', '%H:%M'):
                try:
                    hora_inicio = datetime.strptime(hora_inicio_str, fmt).time()
                    break
                except (ValueError, TypeError):
                    continue
            else:
                raise ValueError
        except (ValueError, TypeError):
            return Response({'mensaje': 'El formato de hora de inicio no es valido. Use HH:MM o HH:MM:SS.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            for fmt in ('%H:%M:%S', '%H:%M'):
                try:
                    hora_fin = datetime.strptime(hora_fin_str, fmt).time()
                    break
                except (ValueError, TypeError):
                    continue
            else:
                raise ValueError
        except (ValueError, TypeError):
            return Response({'mensaje': 'El formato de hora de fin no es valido. Use HH:MM o HH:MM:SS.'}, status=status.HTTP_400_BAD_REQUEST)

        if hora_inicio >= hora_fin:
            return Response({'mensaje': 'La hora de inicio debe ser menor a la hora de fin.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            hora_inicio_obj = datetime.strptime(hora_inicio, '%H:%M')
            hora_fin_obj = datetime.strptime(hora_fin, '%H:%M')
        except (ValueError, TypeError):
            return Response({'mensaje': 'El formato de hora debe ser HH:MM.'}, status=status.HTTP_400_BAD_REQUEST)

        duracion_minutos = (hora_fin_obj - hora_inicio_obj).total_seconds() / 60
        if duracion_minutos > 240:
            return Response({'mensaje': 'La duracion maxima permitida por reserva es de 4 horas continuas.'}, status=status.HTTP_400_BAD_REQUEST)

        hora_apertura = datetime.strptime('07:00', '%H:%M')
        hora_cierre = datetime.strptime('22:00', '%H:%M')
        if hora_inicio_obj < hora_apertura or hora_fin_obj > hora_cierre:
            return Response({'mensaje': 'El bloque horario debe estar dentro del horario habil de la facultad (07:00 a 22:00).'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            usuario = Usuario.objects.get(pk=user_id, umg_estado=1)
        except Usuario.DoesNotExist:
            return Response({'mensaje': 'El docente especificado no existe o esta inactivo.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            lab = Lab.objects.get(pk=lab_id, umg_estado=1)
        except Lab.DoesNotExist:
            return Response({'mensaje': 'El laboratorio especificado no existe o esta inactivo.'}, status=status.HTTP_400_BAD_REQUEST)

        if hay_traslape(lab_id, fecha_obj, hora_inicio, hora_fin):
            msg = 'Ya existe una reserva activa para ese laboratorio que se traslapa con el horario solicitado.'
            return Response({'mensaje': msg}, status=status.HTTP_409_CONFLICT)

        if hay_bloqueo(lab_id, fecha_obj, hora_inicio, hora_fin):
            msg = 'El laboratorio no esta disponible en ese horario debido a un bloqueo registrado.'
            return Response({'mensaje': msg}, status=status.HTTP_409_CONFLICT)

        reserva = Reserva.objects.create(
            umg_user=usuario,
            umg_lab=lab,
            umg_fecha_reserva=fecha_obj,
            umg_hora_inicio=hora_inicio,
            umg_hora_fin=hora_fin,
            umg_motivo=motivo
        )

        msg_log = "El usuario {0} reservo el laboratorio {1} para el {2} de {3} a {4}. Motivo: {5}.".format(
            user_id, lab_id, fecha_obj, hora_inicio, hora_fin, motivo
        )
        registrar_log(user_id, "CREAR_RESERVA", "Reservas", msg_log)

        serializer = ReservaListSerializer(reserva)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(operation_id='reservas_obtener_detalle')
@api_view(['GET'])
def reservas_detalle(request, pk):
    finalizar_vencidas()

    try:
        reserva = Reserva.objects.select_related('umg_user', 'umg_lab').get(pk=pk)
    except Reserva.DoesNotExist:
        return Response({'mensaje': 'La reserva especificada no existe.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = ReservaListSerializer(reserva)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['PATCH'])
def reservas_cancelar(request, pk):
    finalizar_vencidas()

    try:
        reserva = Reserva.objects.get(pk=pk)
    except Reserva.DoesNotExist:
        return Response({'mensaje': 'La reserva especificada no existe.'}, status=status.HTTP_404_NOT_FOUND)

    if reserva.umg_estado == 'C':
        return Response({'mensaje': 'Esta reserva ya se encuentra cancelada.'}, status=status.HTTP_409_CONFLICT)

    # Verificar que la actividad no haya iniciado
    ahora = datetime.now()
    inicio_reserva = datetime.combine(reserva.umg_fecha_reserva, reserva.umg_hora_inicio)
    if ahora >= inicio_reserva:
        return Response(
            {'mensaje': 'No se puede cancelar una reserva cuya actividad ya ha iniciado.'},
            status=status.HTTP_409_CONFLICT
        )

    # Validar permisos
    solicitante_id = (
        request.headers.get('X-User-ID') or
        request.headers.get('x-user-id') or
        request.data.get('UMG_Solicitante_ID') or
        request.query_params.get('solicitanteId')
    )
    if not solicitante_id:
        return Response({'mensaje': 'El ID del solicitante es obligatorio para verificar permisos.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        solicitante = Usuario.objects.select_related('umg_rol').get(pk=solicitante_id, umg_estado=1)
    except Usuario.DoesNotExist:
        return Response({'mensaje': 'El usuario solicitante no existe o esta inactivo.'}, status=status.HTTP_400_BAD_REQUEST)

    es_creador = (reserva.umg_user_id == solicitante.umg_id)
    es_admin = (solicitante.umg_rol.umg_nombre == 'Administrador')

    if not (es_creador or es_admin):
        return Response({'mensaje': 'No tiene permisos para realizar esta accion.'}, status=status.HTTP_403_FORBIDDEN)

    reserva.umg_estado = 'C'
    reserva.save()

    msg_log = "Se cancelo la reserva con ID {0}.".format(pk)
    registrar_log(solicitante.umg_id, "CANCELAR_RESERVA", "Reservas", msg_log)

    return Response({'mensaje': 'Reserva cancelada correctamente.'}, status=status.HTTP_200_OK)


@api_view(['PUT'])
def reservas_modificar(request, pk):
    try:
        reserva = Reserva.objects.get(pk=pk)
    except Reserva.DoesNotExist:
        return Response({'mensaje': 'La reserva especificada no existe.'}, status=status.HTTP_404_NOT_FOUND)

    if reserva.umg_estado != 'R':
        return Response({'mensaje': 'Solo se pueden modificar reservas en estado activo (Reservada).'}, status=status.HTTP_409_CONFLICT)

    # Verificar que la actividad no haya iniciado
    ahora = datetime.now()
    inicio_reserva = datetime.combine(reserva.umg_fecha_reserva, reserva.umg_hora_inicio)
    if ahora >= inicio_reserva:
        return Response(
            {'mensaje': 'No se puede modificar una reserva cuya actividad ya ha iniciado.'},
            status=status.HTTP_409_CONFLICT
        )

    # Validar permisos
    solicitante_id = (
        request.headers.get('X-User-ID') or
        request.headers.get('x-user-id') or
        request.data.get('UMG_Solicitante_ID') or
        request.query_params.get('solicitanteId')
    )
    if not solicitante_id:
        return Response({'mensaje': 'El ID del solicitante es obligatorio para verificar permisos.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        solicitante = Usuario.objects.select_related('umg_rol').get(pk=solicitante_id, umg_estado=1)
    except Usuario.DoesNotExist:
        return Response({'mensaje': 'El usuario solicitante no existe o esta inactivo.'}, status=status.HTTP_400_BAD_REQUEST)

    es_creador = (reserva.umg_user_id == solicitante.umg_id)
    es_admin = (solicitante.umg_rol.umg_nombre == 'Administrador')

    if not (es_creador or es_admin):
        return Response({'mensaje': 'No tiene permisos para realizar esta accion.'}, status=status.HTTP_403_FORBIDDEN)

    # Leer datos del request
    user_id = request.data.get('UMG_User_ID')
    lab_id = request.data.get('UMG_Lab_ID')
    fecha = request.data.get('UMG_Fecha_Reserva')
    hora_inicio_str = request.data.get('UMG_Hora_Inicio')
    hora_fin_str = request.data.get('UMG_Hora_Fin')
    motivo = request.data.get('UMG_Motivo', '').strip()

    # Validar fecha
    try:
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return Response({'mensaje': 'La fecha proporcionada no es valida.'}, status=status.HTTP_400_BAD_REQUEST)

    if fecha_obj < date.today():
        return Response({'mensaje': 'No se puede mover una reserva a una fecha pasada.'}, status=status.HTTP_400_BAD_REQUEST)

    # Parsear horas a objetos time
    try:
        for fmt in ('%H:%M:%S', '%H:%M'):
            try:
                hora_inicio = datetime.strptime(hora_inicio_str, fmt).time()
                break
            except (ValueError, TypeError):
                continue
        else:
            raise ValueError
    except (ValueError, TypeError):
        return Response({'mensaje': 'El formato de hora de inicio no es valido. Use HH:MM o HH:MM:SS.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        for fmt in ('%H:%M:%S', '%H:%M'):
            try:
                hora_fin = datetime.strptime(hora_fin_str, fmt).time()
                break
            except (ValueError, TypeError):
                continue
        else:
            raise ValueError
    except (ValueError, TypeError):
        return Response({'mensaje': 'El formato de hora de fin no es valido. Use HH:MM o HH:MM:SS.'}, status=status.HTTP_400_BAD_REQUEST)

    # Validar horario
    if hora_inicio >= hora_fin:
        return Response({'mensaje': 'La hora de inicio debe ser menor a la hora de fin.'}, status=status.HTTP_400_BAD_REQUEST)

    # Validar motivo
    if not motivo:
        return Response({'mensaje': 'El motivo de la reserva es obligatorio.'}, status=status.HTTP_400_BAD_REQUEST)

    # Validar docente
    try:
        usuario = Usuario.objects.get(pk=user_id, umg_estado=1)
    except Usuario.DoesNotExist:
        return Response({'mensaje': 'El docente especificado no existe o esta inactivo.'}, status=status.HTTP_400_BAD_REQUEST)

    # Validar laboratorio
    try:
        lab = Lab.objects.get(pk=lab_id, umg_estado=1)
    except Lab.DoesNotExist:
        return Response({'mensaje': 'El laboratorio especificado no existe o esta inactivo.'}, status=status.HTTP_400_BAD_REQUEST)

    # Verificar traslape (excluyendo la reserva actual)
    if hay_traslape(lab_id, fecha_obj, hora_inicio, hora_fin, excluir_id=pk):
        msg = 'Ya existe una reserva activa para ese laboratorio que se traslapa con el horario solicitado.'
        return Response({'mensaje': msg}, status=status.HTTP_409_CONFLICT)

    # Verificar bloqueos
    if hay_bloqueo(lab_id, fecha_obj, hora_inicio, hora_fin):
        msg = 'El laboratorio no esta disponible en ese horario debido a un bloqueo registrado.'
        return Response({'mensaje': msg}, status=status.HTTP_409_CONFLICT)

    # Actualizar la reserva
    reserva.umg_user = usuario
    reserva.umg_lab = lab
    reserva.umg_fecha_reserva = fecha_obj
    reserva.umg_hora_inicio = hora_inicio
    reserva.umg_hora_fin = hora_fin
    reserva.umg_motivo = motivo
    reserva.save()

    msg_log = "Se modifico la reserva con ID {0}. Nuevo laboratorio: {1}, Fecha: {2}, Horario: {3} a {4}. Motivo: {5}.".format(
        pk, lab_id, fecha_obj, hora_inicio, hora_fin, motivo
    )
    registrar_log(solicitante.umg_id, "MODIFICAR_RESERVA", "Reservas", msg_log)

    serializer = ReservaListSerializer(reserva)
    return Response(serializer.data, status=status.HTTP_200_OK)