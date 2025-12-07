"""GraphQL mutation string builder."""

from typing import Dict, Any, List, Optional, Tuple


class MutationBuilder:
    """Builds GraphQL mutation strings for Amplify GraphQL API."""

    @staticmethod
    def build_create_mutation(
        model_name: str,
        return_fields: Optional[List[str]] = None,
    ) -> str:
        if return_fields is None:
            return_fields = ["id"]

        fields_str = "\n".join(f"        {field}" for field in return_fields)

        mutation = f"""
mutation Create{model_name}($input: Create{model_name}Input!) {{
  create{model_name}(input: $input) {{
{fields_str}
  }}
}}
"""
        return mutation.strip()

    @staticmethod
    def build_update_mutation(
        model_name: str,
        return_fields: Optional[List[str]] = None,
    ) -> str:
        if return_fields is None:
            return_fields = ["id"]

        fields_str = "\n".join(f"        {field}" for field in return_fields)

        mutation = f"""
mutation Update{model_name}($input: Update{model_name}Input!) {{
  update{model_name}(input: $input) {{
{fields_str}
  }}
}}
"""
        return mutation.strip()

    @staticmethod
    def build_delete_mutation(
        model_name: str,
        return_fields: Optional[List[str]] = None,
    ) -> str:
        if return_fields is None:
            return_fields = ["id"]

        fields_str = "\n".join(f"        {field}" for field in return_fields)

        mutation = f"""
mutation Delete{model_name}($input: Delete{model_name}Input!) {{
  delete{model_name}(input: $input) {{
{fields_str}
  }}
}}
"""
        return mutation.strip()

    @staticmethod
    def build_create_variables(input_data: Dict[str, Any]) -> Dict[str, Any]:
        return {"input": input_data}

    @staticmethod
    def build_update_variables(
        record_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        input_data = {"id": record_id, **updates}
        return {"input": input_data}

    @staticmethod
    def build_delete_variables(record_id: str) -> Dict[str, Any]:
        return {"input": {"id": record_id}}
