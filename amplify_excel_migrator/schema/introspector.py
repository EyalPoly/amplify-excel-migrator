"""Schema introspection for GraphQL models."""

import logging
from typing import Dict, Any, Optional

import inflect

from amplify_excel_migrator.graphql import GraphQLClient
from amplify_excel_migrator.graphql.query_builder import QueryBuilder

logger = logging.getLogger(__name__)


class SchemaIntrospector:
    def __init__(self, client: GraphQLClient):
        self.client = client

    def get_model_structure(self, model_type: str) -> Dict[str, Any]:
        query = QueryBuilder.build_introspection_query(model_type)
        response = self.client.request(query)

        if response and "data" in response and "__type" in response["data"]:
            return response["data"]["__type"]

        return {}

    def get_all_types(self) -> list[Dict[str, Any]]:
        query = QueryBuilder.build_schema_introspection_query()
        response = self.client.request(query)

        if response and "data" in response and "__schema" in response["data"]:
            return response["data"]["__schema"].get("types", [])

        return []

    def get_primary_field_name(self, model_name: str, parsed_model_structure: Dict[str, Any]) -> tuple[str, bool, str]:
        secondary_index = self._get_secondary_index(model_name)
        if secondary_index:
            field_type = "String"
            for field in parsed_model_structure["fields"]:
                if field["name"] == secondary_index:
                    field_type = field["type"]
                    break
            return secondary_index, True, field_type

        for field in parsed_model_structure["fields"]:
            if field["is_required"] and field["is_scalar"] and field["name"] != "id":
                return field["name"], False, field["type"]

        logger.error("No suitable primary field found (required scalar field other than id)")
        return "", False, "String"

    def _get_secondary_index(self, model_name: str) -> str:
        query_structure = self.get_model_structure("Query")
        if not query_structure:
            logger.error("Query type not found in schema")
            return ""

        query_fields = query_structure["fields"]
        pattern = f"{model_name}By"

        for query in query_fields:
            query_name = query["name"]
            if pattern in query_name:
                pattern_index = query_name.index(pattern)
                field_name = query_name[pattern_index + len(pattern) :]
                return field_name[0].lower() + field_name[1:] if field_name else ""

        return ""

    def get_list_query_name(self, model_name: str) -> Optional[str]:
        query_structure = self.get_model_structure("Query")
        if not query_structure:
            logger.error("Query type not found in schema")
            return f"list{model_name}s"

        query_fields = query_structure["fields"]
        p = inflect.engine()

        candidates = [f"list{model_name}"]
        capitals = [i for i, c in enumerate(model_name) if c.isupper()]

        if len(capitals) > 1:
            last_word_start = capitals[-1]
            prefix = model_name[:last_word_start]
            last_word = model_name[last_word_start:]

            last_word_plural = str(p.plural(last_word.lower()))
            last_word_plural_cap = last_word_plural[0].upper() + last_word_plural[1:] if last_word_plural else ""

            pascal_plural = f"{prefix}{last_word_plural_cap}"
            candidates.append(f"list{pascal_plural}")

        full_plural = str(p.plural(model_name.lower()))
        full_plural_cap = full_plural[0].upper() + full_plural[1:] if full_plural else ""
        candidates.append(f"list{full_plural_cap}")

        for query in query_fields:
            query_name = query["name"]
            if query_name in candidates and "By" not in query_name:
                return query_name

        logger.error(f"No list query found for model {model_name}, tried: {candidates}")
        return None
