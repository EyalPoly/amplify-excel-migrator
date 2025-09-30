from typing import Dict, List, Any


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

    def generate_field_summary(self, model_info: Dict) -> str:
        """
        Generate a human-readable summary of the model

        Args:
            model_info: Parsed model information

        Returns:
            Formatted string summary
        """
        lines = []
        lines.append(f"Model: {model_info['name']}")
        lines.append(f"Type: {model_info['kind']}")

        if model_info.get('description'):
            lines.append(f"Description: {model_info['description']}")

        lines.append("\nFields:")
        lines.append("-" * 60)

        for field in model_info['fields']:
            # Build field line
            field_line = f"  {field['name']:<20} {field['type']['full_type']:<20}"

            # Add flags
            flags = []
            if field['is_required']:
                flags.append("required")
            if field['is_list']:
                flags.append("list")
            if field['is_scalar']:
                flags.append("scalar")
            elif field['is_object']:
                flags.append("object")
            elif field['is_enum']:
                flags.append("enum")
            if field['is_connection']:
                flags.append("connection")

            if flags:
                field_line += f" [{', '.join(flags)}]"

            lines.append(field_line)

        return "\n".join(lines)

    def to_typescript_interface(self, model_info: Dict) -> str:
        """
        Generate TypeScript interface from model structure

        Args:
            model_info: Parsed model information

        Returns:
            TypeScript interface string
        """
        lines = []
        lines.append(f"interface {model_info['name']} {{")

        for field in model_info['fields']:
            ts_type = self.graphql_to_typescript_type(field['type']['full_type'])
            optional = '' if field['is_required'] else '?'
            lines.append(f"  {field['name']}{optional}: {ts_type};")

        lines.append("}")

        return "\n".join(lines)

    def graphql_to_typescript_type(self, graphql_type: str) -> str:
        """
        Convert GraphQL type to TypeScript type

        Args:
            graphql_type: GraphQL type string

        Returns:
            TypeScript type string
        """
        # Remove NON_NULL markers
        ts_type = graphql_type.replace('!', '')

        # Type mappings
        type_map = {
            'String': 'string',
            'Int': 'number',
            'Float': 'number',
            'Boolean': 'boolean',
            'ID': 'string',
            'AWSDate': 'string',
            'AWSTime': 'string',
            'AWSDateTime': 'string',
            'AWSTimestamp': 'number',
            'AWSEmail': 'string',
            'AWSJSON': 'any',
            'AWSURL': 'string',
            'AWSPhone': 'string',
            'AWSIPAddress': 'string'
        }

        # Handle lists
        if '[' in ts_type:
            inner_type = ts_type.replace('[', '').replace(']', '')
            inner_ts = type_map.get(inner_type, inner_type)
            return f"{inner_ts}[]"

        return type_map.get(ts_type, ts_type)


# Example usage
def main():
    # Your Group model introspection result
    introspection_result = {
        'data': {
            '__type': {
                'description': None,
                'fields': [
                    {
                        'description': None,
                        'name': 'name',
                        'type': {
                            'kind': 'NON_NULL',
                            'name': None,
                            'ofType': {
                                'kind': 'SCALAR',
                                'name': 'String',
                                'ofType': None
                            }
                        }
                    },
                    {
                        'description': None,
                        'name': 'description',
                        'type': {
                            'kind': 'SCALAR',
                            'name': 'String',
                            'ofType': None
                        }
                    },
                    {
                        'description': None,
                        'name': 'observations',
                        'type': {
                            'kind': 'OBJECT',
                            'name': 'ModelObservationConnection',
                            'ofType': None
                        }
                    },
                    {
                        'description': None,
                        'name': 'id',
                        'type': {
                            'kind': 'NON_NULL',
                            'name': None,
                            'ofType': {
                                'kind': 'SCALAR',
                                'name': 'ID',
                                'ofType': None
                            }
                        }
                    },
                    {
                        'description': None,
                        'name': 'createdAt',
                        'type': {
                            'kind': 'NON_NULL',
                            'name': None,
                            'ofType': {
                                'kind': 'SCALAR',
                                'name': 'AWSDateTime',
                                'ofType': None
                            }
                        }
                    },
                    {
                        'description': None,
                        'name': 'updatedAt',
                        'type': {
                            'kind': 'NON_NULL',
                            'name': None,
                            'ofType': {
                                'kind': 'SCALAR',
                                'name': 'AWSDateTime',
                                'ofType': None
                            }
                        }
                    },
                    {
                        'description': None,
                        'name': 'owner',
                        'type': {
                            'kind': 'SCALAR',
                            'name': 'String',
                            'ofType': None
                        }
                    }
                ],
                'kind': 'OBJECT',
                'name': 'Group'
            }
        }
    }

    parser = ModelFieldParser()
    model_info = parser.parse_model_structure(introspection_result)
    print(model_info)

if __name__ == "__main__":
    main()