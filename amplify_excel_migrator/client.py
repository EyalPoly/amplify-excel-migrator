import logging
from typing import Dict, Any, Optional, List

from amplify_excel_migrator.graphql import GraphQLClient, QueryExecutor
from amplify_excel_migrator.auth import AuthenticationProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class AmplifyClient:
    """
    Simplified client for Amplify GraphQL API operations.

    Provides a clean interface for schema introspection, foreign key lookup,
    and batch uploading. Delegates to GraphQLClient and QueryExecutor.
    """

    def __init__(self, api_endpoint: str, auth_provider: Optional[AuthenticationProvider] = None):
        self.api_endpoint = api_endpoint
        self._auth_provider = auth_provider

        self._client = GraphQLClient(api_endpoint, auth_provider)
        self._executor = QueryExecutor(self._client, batch_size=20)

    @property
    def auth_provider(self) -> Optional[AuthenticationProvider]:
        return self._auth_provider

    @auth_provider.setter
    def auth_provider(self, value: Optional[AuthenticationProvider]):
        self._auth_provider = value
        self._client.auth_provider = value

    def get_model_structure(self, model_type: str) -> Dict[str, Any]:
        return self._executor.get_model_structure(model_type)

    def get_all_types(self) -> list[Dict[str, Any]]:
        return self._executor.get_all_types()

    def get_primary_field_name(self, model_name: str, parsed_model_structure: Dict[str, Any]) -> tuple[str, bool, str]:
        return self._executor.get_primary_field_name(model_name, parsed_model_structure)

    def build_foreign_key_lookups(self, df, parsed_model_structure: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
        return self._executor.build_foreign_key_lookups(df, parsed_model_structure)

    def upload(
        self, records: List[Dict], model_name: str, parsed_model_structure: Dict[str, Any]
    ) -> tuple[int, int, List[Dict]]:
        return self._executor.upload(records, model_name, parsed_model_structure)
