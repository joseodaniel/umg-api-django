from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import LogEntry
from .serializers import LogEntrySerializer
from usuarios.models import Usuario


@api_view(['GET'])
def logs_list(request):
    user_id = request.query_params.get('UMG_User_ID')

    try:
        solicitante = Usuario.objects.get(pk=user_id, umg_estado=1)
    except (Usuario.DoesNotExist, ValueError, TypeError):
        return Response(
            {'mensaje': 'Debe indicar un UMG_User_ID valido.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    if solicitante.umg_rol.umg_nombre != 'Admin':
        return Response(
            {'mensaje': 'Solo el administrador puede consultar el historial de auditoria.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    logs = LogEntry.objects.all().order_by('-umg_fecha_registro')[:100]
    serializer = LogEntrySerializer(logs, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)