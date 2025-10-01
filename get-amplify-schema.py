"""
Get Amplify Schema Structure via GraphQL Introspection
This script retrieves all models, fields, and types from your Amplify API
"""

import requests
import json
from typing import Dict, List, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AmplifySchemaIntrospector:
    """Retrieve and analyze Amplify GraphQL schema"""
    
    def __init__(self, api_endpoint: str, api_key: str):
        self.api_endpoint = api_endpoint
        self.api_key = api_key
        self.headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json'
        }
    
    def get_full_schema(self) -> Dict:
        """Get the complete schema using introspection query"""
        
        introspection_query = """
        query IntrospectionQuery {
          __schema {
            types {
              name
              kind
              description
              fields {
                name
                type {
                  name
                  kind
                  ofType {
                    name
                    kind
                    ofType {
                      name
                      kind
                    }
                  }
                }
                description
              }
              inputFields {
                name
                type {
                  name
                  kind
                  ofType {
                    name
                    kind
                    ofType {
                      name
                      kind
                    }
                  }
                }
                defaultValue
              }
              possibleTypes {
                name
                kind
              }
              enumValues {
                name
                description
              }
            }
          }
        }
        """
        
        payload = {
            'query': introspection_query
        }
        
        try:
            response = requests.post(
                self.api_endpoint,
                headers=self.headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'errors' in result:
                    logger.error(f"GraphQL errors: {result['errors']}")
                    return {}
                return result['data']['__schema']
            else:
                logger.error(f"HTTP error {response.status_code}: {response.text}")
                return {}
                
        except Exception as e:
            logger.error(f"Failed to get schema: {e}")
            return {}
    
    def get_models_only(self) -> List[Dict]:
        """Get only the data models (exclude system types)"""
        
        schema = self.get_full_schema()
        if not schema:
            return []
        
        models = []
        
        for type_def in schema['types']:
            name = type_def['name']
            kind = type_def['kind']
            
            # Skip GraphQL internal types
            if name.startswith('__'):
                continue
            
            if kind == 'SCALAR' or name in ['String', 'Int', 'Float', 'Boolean', 'ID']:
                continue
            
            if name in ['Query', 'Mutation', 'Subscription']:
                continue
            
            if 'Connection' in name or 'Edge' in name or name.startswith('Model'):
                continue
            
            if kind == 'OBJECT' and type_def.get('fields'):
                models.append(type_def)
        
        return models
    
    def get_model_structure(self, model_name: str) -> Dict:

        query = f"""
        query GetModelType {{
          __type(name: "{model_name}") {{
            name
            kind
            description
            fields {{
              name
              type {{
                name
                kind
                ofType {{
                  name
                  kind
                  ofType {{
                    name
                    kind
                  }}
                }}
              }}
              description
            }}
          }}
        }}
        """
        
        payload = {'query': query}
        
        try:
            response = requests.post(
                self.api_endpoint,
                headers=self.headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'errors' not in result:
                    return result['data']['__type']
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get model {model_name}: {e}")
            return None
    
    def get_input_types(self) -> List[Dict]:
        """Get all input types (CreateInput, UpdateInput, etc.)"""
        
        schema = self.get_full_schema()
        if not schema:
            return []
        
        input_types = []
        
        for type_def in schema['types']:
            if type_def['kind'] == 'INPUT_OBJECT':
                # Filter for your model input types
                if 'Input' in type_def['name'] and not type_def['name'].startswith('Model'):
                    input_types.append(type_def)
        
        return input_types
    
    def get_enums(self) -> List[Dict]:

        schema = self.get_full_schema()
        if not schema:
            return []
        
        enums = []
        
        for type_def in schema['types']:
            if type_def['kind'] == 'ENUM' and not type_def['name'].startswith('__'):
                # Skip GraphQL built-in enums
                if type_def['name'] not in ['ModelSortDirection', 'ModelAttributeTypes']:
                    enums.append({
                        'name': type_def['name'],
                        'values': [v['name'] for v in (type_def.get('enumValues') or [])]
                    })
        
        return enums
    
    def print_model_summary(self, models: List[Dict]):
        """Print a readable summary of models"""
        
        for model in models:
            print(f"\n{'='*50}")
            print(f"Model: {model['name']}")
            print(f"{'='*50}")
            
            if model.get('fields'):
                for field in model['fields']:
                    field_type = self._get_field_type_name(field['type'])
                    print(f"  {field['name']}: {field_type}")
    
    def _get_field_type_name(self, type_info: Dict) -> str:
        """Extract readable type name from nested type structure"""
        
        if type_info.get('name'):
            return type_info['name']
        
        if type_info.get('ofType'):
            inner_type = self._get_field_type_name(type_info['ofType'])
            if type_info['kind'] == 'NON_NULL':
                return f"{inner_type}!"
            elif type_info['kind'] == 'LIST':
                return f"[{inner_type}]"
            
        return type_info.get('kind', 'Unknown')
    
    def export_schema_to_file(self, filename: str = 'amplify_schema.json'):
        """Export the complete schema to a JSON file"""
        
        schema = self.get_full_schema()
        if schema:
            with open(filename, 'w') as f:
                json.dump(schema, f, indent=2)
            logger.info(f"Schema exported to {filename}")
            return True
        return False
    
    def generate_typescript_interfaces(self, models: List[Dict]) -> str:
        """Generate TypeScript interfaces from models"""
        
        typescript_code = "// Generated TypeScript interfaces from Amplify Schema\n\n"
        
        for model in models:
            interface_name = model['name']
            typescript_code += f"export interface {interface_name} {{\n"
            
            if model.get('fields'):
                for field in model['fields']:
                    field_name = field['name']
                    field_type = self._convert_to_typescript_type(field['type'])
                    
                    # Check if field is required (NON_NULL)
                    is_required = field['type'].get('kind') == 'NON_NULL'
                    optional_mark = '' if is_required else '?'
                    
                    typescript_code += f"  {field_name}{optional_mark}: {field_type};\n"
            
            typescript_code += "}\n\n"
        
        return typescript_code
    
    def _convert_to_typescript_type(self, type_info: Dict) -> str:
        """Convert GraphQL type to TypeScript type"""
        
        type_mapping = {
            'String': 'string',
            'Int': 'number',
            'Float': 'number',
            'Boolean': 'boolean',
            'ID': 'string',
            'AWSDateTime': 'string',
            'AWSDate': 'string',
            'AWSTime': 'string',
            'AWSEmail': 'string',
            'AWSJSON': 'any',
            'AWSURL': 'string',
        }
        
        if type_info.get('name'):
            return type_mapping.get(type_info['name'], type_info['name'])
        
        if type_info.get('ofType'):
            inner_type = self._convert_to_typescript_type(type_info['ofType'])
            if type_info['kind'] == 'LIST':
                return f"{inner_type}[]"
            elif type_info['kind'] == 'NON_NULL':
                return inner_type
        
        return 'any'


def main():
    """Main function to demonstrate schema introspection"""
    
    print("""
    ╔════════════════════════════════════════╗
    ║   Amplify Schema Introspection Tool    ║
    ╚════════════════════════════════════════╝
    """)
    
    # Get API credentials
    print("\nEnter your Amplify API details (from amplify_outputs.json):")
    api_endpoint = input("API Endpoint: ").strip()
    api_key = input("API Key: ").strip()
    
    if not api_endpoint or not api_key:
        logger.error("API endpoint and key are required!")
        return
    
    # Create introspector
    introspector = AmplifySchemaIntrospector(api_endpoint, api_key)
    
    print("\nWhat would you like to do?")
    print("1. Get all models")
    print("2. Get specific model structure")
    print("3. Get all enums")
    print("4. Get input types")
    print("5. Export full schema to JSON")
    print("6. Generate TypeScript interfaces")
    print("7. Get everything")
    
    choice = input("\nChoice (1-7): ")
    
    if choice == '1' or choice == '7':
        print("\n=== DATA MODELS ===")
        models = introspector.get_models_only()
        introspector.print_model_summary(models)
    
    if choice == '2':
        model_name = input("Enter model name (e.g., Observation): ")
        model = introspector.get_model_structure(model_name)
        if model:
            print(json.dumps(model, indent=2))
        else:
            print(f"Model {model_name} not found")
    
    if choice == '3' or choice == '7':
        print("\n=== ENUMS ===")
        enums = introspector.get_enums()
        for enum in enums:
            print(f"\n{enum['name']}:")
            for value in enum['values']:
                print(f"  - {value}")
    
    if choice == '4' or choice == '7':
        print("\n=== INPUT TYPES ===")
        input_types = introspector.get_input_types()
        for input_type in input_types:
            print(f"\n{input_type['name']}:")
            if input_type.get('inputFields'):
                for field in input_type['inputFields']:
                    field_type = introspector._get_field_type_name(field['type'])
                    print(f"  {field['name']}: {field_type}")
    
    if choice == '5' or choice == '7':
        if introspector.export_schema_to_file():
            print("\n✅ Full schema exported to amplify_schema.json")
    
    if choice == '6' or choice == '7':
        models = introspector.get_models_only()
        typescript = introspector.generate_typescript_interfaces(models)
        
        with open('amplify_models.ts', 'w') as f:
            f.write(typescript)
        print("\n✅ TypeScript interfaces generated in amplify_models.ts")
    
    if choice == '7':
        print("\n✅ All data retrieved successfully!")


# Alternative: Simple function to just get the schema
def get_amplify_schema_simple(api_endpoint: str, api_key: str) -> Dict:
    """Simple function to get Amplify schema"""
    
    headers = {
        'x-api-key': api_key,
        'Content-Type': 'application/json'
    }
    
    # Basic introspection query
    query = """
    {
      __schema {
        types {
          name
          kind
          fields {
            name
            type {
              name
              kind
            }
          }
        }
      }
    }
    """
    
    response = requests.post(
        api_endpoint,
        headers=headers,
        json={'query': query}
    )
    
    if response.status_code == 200:
        return response.json()['data']['__schema']
    
    return None


if __name__ == "__main__":
    main()
