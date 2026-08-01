"""Schema OpenAPI automatico para las vistas del proyecto."""

import ast
import json
import inspect
import sys
import textwrap
from pathlib import Path
from datetime import date, datetime, time

from drf_spectacular.openapi import AutoSchema
from rest_framework import serializers


DOCS = json.loads((Path(__file__).with_name('schema_docs.json')).read_text(encoding='utf-8'))


class DynamicAutoSchema(AutoSchema):
    """Descubre serializers, ejemplos y metadatos de cada endpoint."""

    def _module_serializer(self):
        module = inspect.getmodule(self.view.__class__)
        if module is None:
            return None
        candidates = [
            value for value in vars(sys.modules[module.__name__]).values()
            if inspect.isclass(value)
            and issubclass(value, serializers.BaseSerializer)
            and value is not serializers.BaseSerializer
        ]
        if len(candidates) == 1:
            return candidates[0]()
        preferred = [
            value for value in candidates
            if value.__name__.endswith(('ListSerializer', 'Serializer'))
        ]
        return preferred[0]() if len(preferred) == 1 else None

    def _get_serializer(self):
        serializer = self._module_serializer()
        return serializer if serializer is not None else super()._get_serializer()

    def _view_function(self, method):
        handler = getattr(self.view, method.lower(), None)
        for cell in (getattr(handler, '__closure__', ()) or ()):
            if inspect.isfunction(cell.cell_contents):
                return cell.cell_contents
        return None

    def _view_source(self, method):
        function = self._view_function(method)
        return textwrap.dedent(inspect.getsource(function)) if function else ''

    def _operation_metadata(self, method):
        function = self._view_function(method)
        if function is None:
            return None, None

        module = function.__module__.split('.')[0].replace('_', ' ')
        name = function.__name__.lower()
        words = name.split('_')
        actions = set(DOCS.get('actions', []))
        resource_words = [word for word in words if word not in actions]
        resource = ' '.join(resource_words) or module

        config = DOCS.get('methods', {}).get(method, {})
        action = DOCS.get('views', {}).get(name)
        if action is None:
            # Buscar en las reglas dinamicas definidas en el JSON
            for rule in DOCS.get('rules', []):
                if rule['method'] == method and rule['keyword'] in words:
                    action = config.get(rule['key'], config.get('default'))
                    break
            else:
                action = config.get('default', method)

        return module.title(), f'{action} {resource}'

    @staticmethod
    def _attr_keys(source, attr):
        tree = ast.parse(source)
        keys = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                target = node.func.value
                if node.func.attr == 'get' and isinstance(target, ast.Attribute):
                    if isinstance(target.value, ast.Name) and target.value.id == 'request' and target.attr == attr:
                        if node.args and isinstance(node.args[0], ast.Constant):
                            keys.append(node.args[0].value)
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
                if isinstance(node.value.value, ast.Name) and node.value.value.id == 'request' and node.value.attr == attr:
                    key = node.slice.value if isinstance(node.slice, ast.Constant) else None
                    if key:
                        keys.append(key)
        return list(dict.fromkeys(keys))

    def _request_keys(self, source):
        return self._attr_keys(source, 'data')

    def _query_param_keys(self, source):
        return self._attr_keys(source, 'query_params')

    @staticmethod
    def _value_for(key):
        name = key.lower()
        if 'fecha' in name:
            return date.today().isoformat()
        if 'hora' in name:
            return time(8, 0).isoformat()
        if 'id' in name or 'estado' in name:
            return 1
        if 'correo' in name or 'usuario' in name:
            return 'ejemplo@umg.edu.gt'
        if 'contrasena' in name:
            return 'Cambiar123'
        return 'string'

    def _request_example(self, method):
        keys = self._request_keys(self._view_source(method))
        if keys:
            return {key: self._value_for(key) for key in keys}
        serializer = self._get_serializer()
        if serializer is None:
            return None
        return {
            name: self._value_for(name)
            for name, field in serializer.fields.items()
            if not field.read_only
        } or None

    def _query_parameters(self, method):
        keys = self._query_param_keys(self._view_source(method))
        return [
            {
                'name': key,
                'in': 'query',
                'required': False,
                'schema': {'type': 'string'},
                'example': self._value_for(key),
            }
            for key in keys
        ]

    def get_operation(self, path, path_regex, path_prefix, method, registry):
        operation = super().get_operation(path, path_regex, path_prefix, method, registry)
        if not operation:
            return operation

        tag, summary = self._operation_metadata(method)
        if tag:
            operation.setdefault('tags', [tag])
        if summary:
            operation.setdefault('summary', summary)

        methods_with_examples = set(DOCS.get('methods_with_examples', ['POST', 'PUT']))
        if method not in methods_with_examples:
            return operation
        request_body = operation.get('requestBody')
        if not request_body:
            return operation
        example = self._request_example(method)
        if example is None:
            return operation
        for media in request_body.get('content', {}).values():
            media.setdefault('examples', {})['auto-generated'] = {
                'summary': 'Estructura base generada automaticamente',
                'value': example,
            }
        return operation