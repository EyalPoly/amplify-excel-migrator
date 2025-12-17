"""GraphQL query string builder."""

from typing import List, Optional, Any, Dict


class QueryBuilder:
    """Builds GraphQL query strings for Amplify GraphQL API."""

    @staticmethod
    def build_list_query(
        model_name: str,
        fields: Optional[List[str]] = None,
        limit: int = 1000,
        with_pagination: bool = True,
    ) -> str:
        if fields is None:
            fields = ["id"]

        fields_str = "\n".join(f"            {field}" for field in fields)
        query_name = f"list{model_name}s"

        if with_pagination:
            query = f"""
query List{model_name}s($limit: Int, $nextToken: String) {{
  {query_name}(limit: $limit, nextToken: $nextToken) {{
    items {{
{fields_str}
    }}
    nextToken
  }}
}}
"""
        else:
            query = f"""
query List{model_name}s($limit: Int) {{
  {query_name}(limit: $limit) {{
    items {{
{fields_str}
    }}
  }}
}}
"""
        return query.strip()

    @staticmethod
    def build_list_query_with_filter(
        model_name: str,
        fields: Optional[List[str]] = None,
        limit: int = 1000,
        with_pagination: bool = True,
    ) -> str:
        if fields is None:
            fields = ["id"]

        fields_str = "\n".join(f"            {field}" for field in fields)
        query_name = f"list{model_name}s"

        if with_pagination:
            query = f"""
query List{model_name}s($filter: Model{model_name}FilterInput, $limit: Int, $nextToken: String) {{
  {query_name}(filter: $filter, limit: $limit, nextToken: $nextToken) {{
    items {{
{fields_str}
    }}
    nextToken
  }}
}}
"""
        else:
            query = f"""
query List{model_name}s($filter: Model{model_name}FilterInput, $limit: Int) {{
  {query_name}(filter: $filter, limit: $limit) {{
    items {{
{fields_str}
    }}
  }}
}}
"""
        return query.strip()

    @staticmethod
    def build_secondary_index_query(
        model_name: str,
        index_field: str,
        fields: Optional[List[str]] = None,
        field_type: str = "String",
        with_pagination: bool = True,
    ) -> str:
        if fields is None:
            fields = ["id", index_field]

        fields_str = "\n".join(f"            {field}" for field in fields)
        query_name = f"list{model_name}By{index_field[0].upper() + index_field[1:]}"

        if with_pagination:
            query = f"""
query {query_name}(${index_field}: {field_type}!, $limit: Int, $nextToken: String) {{
  {query_name}({index_field}: ${index_field}, limit: $limit, nextToken: $nextToken) {{
    items {{
{fields_str}
    }}
    nextToken
  }}
}}
"""
        else:
            query = f"""
query {query_name}(${index_field}: {field_type}!) {{
  {query_name}({index_field}: ${index_field}) {{
    items {{
{fields_str}
    }}
  }}
}}
"""
        return query.strip()

    @staticmethod
    def build_get_by_id_query(
        model_name: str,
        fields: Optional[List[str]] = None,
    ) -> str:
        if fields is None:
            fields = ["id"]

        fields_str = "\n".join(f"        {field}" for field in fields)

        query = f"""
query Get{model_name}($id: ID!) {{
  get{model_name}(id: $id) {{
{fields_str}
  }}
}}
"""
        return query.strip()

    @staticmethod
    def build_introspection_query(model_name: str) -> str:
        query = f"""
query IntrospectModel {{
  __type(name: "{model_name}") {{
    name
    fields {{
      name
      type {{
        name
        kind
        ofType {{
          name
          kind
        }}
      }}
    }}
  }}
}}
"""
        return query.strip()

    @staticmethod
    def build_schema_introspection_query() -> str:
        query = """
query IntrospectSchema {
  __schema {
    types {
      name
      kind
    }
  }
}
"""
        return query.strip()

    @staticmethod
    def build_variables_for_list(
        limit: int = 1000,
        next_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        variables = {"limit": limit}
        if next_token:
            variables["nextToken"] = next_token
        return variables

    @staticmethod
    def build_variables_for_filter(
        filter_dict: Dict[str, Any],
        limit: int = 1000,
        next_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        variables = {"filter": filter_dict, "limit": limit}
        if next_token:
            variables["nextToken"] = next_token
        return variables

    @staticmethod
    def build_variables_for_secondary_index(
        index_field: str,
        value: Any,
        limit: int = 1000,
        next_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        variables = {index_field: value, "limit": limit}
        if next_token:
            variables["nextToken"] = next_token
        return variables

    @staticmethod
    def build_filter_equals(field: str, value: Any) -> Dict[str, Any]:
        return {field: {"eq": value}}
