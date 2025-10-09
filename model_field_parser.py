from typing import Dict, Any


class ModelFieldParser:
    """Parse GraphQL model fields from introspection results"""

    def __init__(self):
        self.scalar_types = {
            'String', 'Int', 'Float', 'Boolean', 'ID',
            'AWSDate', 'AWSTime', 'AWSDateTime', 'AWSTimestamp',
            'AWSEmail', 'AWSJSON', 'AWSURL', 'AWSPhone', 'AWSIPAddress'
        }
        self.metadata_fields = {'id', 'createdAt', 'updatedAt', 'owner'}

    def parse_model_structure(self, introspection_result: Dict) -> Dict[str, Any]:
        if 'data' in introspection_result and '__type' in introspection_result['data']:
            type_data = introspection_result['data']['__type']
        else:
            type_data = introspection_result

        model_info = {
            'name': type_data.get('name'),
            'kind': type_data.get('kind'),
            'description': type_data.get('description'),
            'fields': []
        }

        if type_data.get('fields'):
            for field in type_data['fields']:
                parsed_field = self.parse_field(field)
                model_info['fields'].append(parsed_field) if parsed_field else None

        return model_info

    def parse_field(self, field: Dict) -> Dict[str, Any]:
        base_type = self.get_base_type_name(field.get('type', {}))
        if 'Connection' in base_type or field.get('name') in self.metadata_fields:
            return {}

        field_info = {
            'name': field.get('name'),
            'description': field.get('description'),
            'type': base_type,
            'is_required': self.is_required_field(field.get('type', {})),
            'is_list': self.is_list_type(field.get('type', {})),
            'is_scalar': base_type in self.scalar_types,
            'is_object': field.get('type', {}).get('kind') == 'ENUM',
            'is_enum': self.get_type_kind(field.get('type', {})) in ['OBJECT', 'INTERFACE'],
        }

        return field_info

    def parse_type(self, type_obj: Dict) -> Dict[str, Any]:
        """
        Recursively parse type information
        """
        if not type_obj:
            return {'name': 'Unknown', 'kind': 'UNKNOWN'}

        type_info = {
            'name': type_obj.get('name'),
            'kind': type_obj.get('kind'),
            'full_type': self.get_full_type_string(type_obj)
        }

        # If there's nested type info (NON_NULL, LIST), include it
        if type_obj.get('ofType'):
            type_info['of_type'] = self.parse_type(type_obj['ofType'])

        return type_info

    def get_full_type_string(self, type_obj: Dict) -> str:
        """
        Get human-readable type string (e.g., '[String!]!')
        """
        if not type_obj:
            return 'Unknown'

        if type_obj.get('name'):
            return type_obj['name']

        if type_obj['kind'] == 'NON_NULL':
            inner = self.get_full_type_string(type_obj.get('ofType', {}))
            return f"{inner}!"

        if type_obj['kind'] == 'LIST':
            inner = self.get_full_type_string(type_obj.get('ofType', {}))
            return f"[{inner}]"

        return type_obj.get('kind', 'Unknown')

    def get_base_type_name(self, type_obj: Dict) -> str:
        """
        Get the base type name, unwrapping NON_NULL and LIST wrappers
        """
        if not type_obj:
            return 'Unknown'

        if type_obj.get('name'):
            return type_obj['name']

        if type_obj.get('ofType'):
            return self.get_base_type_name(type_obj['ofType'])

        return 'Unknown'

    def get_type_kind(self, type_obj: Dict) -> str:
        if not type_obj:
            return 'UNKNOWN'

        if type_obj['kind'] in ['NON_NULL', 'LIST'] and type_obj.get('ofType'):
            return self.get_type_kind(type_obj['ofType'])

        return type_obj.get('kind', 'UNKNOWN')

    @staticmethod
    def is_required_field(type_obj: Dict) -> bool:
        return type_obj and type_obj.get('kind') == 'NON_NULL'

    def is_list_type(self, type_obj: Dict) -> bool:
        if not type_obj:
            return False

        if type_obj['kind'] == 'LIST':
            return True

        if type_obj.get('ofType'):
            return self.is_list_type(type_obj['ofType'])

        return False
