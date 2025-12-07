"""
Amplify GraphQL Client - Facade for backward compatibility.

This module provides a backward-compatible interface that delegates to the new
GraphQLClient and QueryExecutor classes.
"""

import logging
from typing import Dict, Any, Optional, List

import aiohttp

from amplify_excel_migrator.graphql import GraphQLClient, QueryExecutor, AuthenticationError, GraphQLError
from amplify_excel_migrator.auth import AuthenticationProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class AmplifyClient:
    """
    Facade for Amplify GraphQL API operations.

    This class maintains backward compatibility while delegating to
    GraphQLClient and QueryExecutor for actual operations.
    """

    def __init__(self, api_endpoint: str, auth_provider: Optional[AuthenticationProvider] = None):
        """
        Initialize the client.

        Args:
            api_endpoint: Amplify GraphQL endpoint
            auth_provider: Authentication provider instance
        """
        self.api_endpoint = api_endpoint
        self._auth_provider = auth_provider

        self._client = GraphQLClient(api_endpoint, auth_provider)
        self._executor = QueryExecutor(self._client, batch_size=20)

        self.batch_size = self._executor.batch_size
        self.records_cache = self._executor.records_cache

    @property
    def auth_provider(self) -> Optional[AuthenticationProvider]:
        """Get the authentication provider."""
        return self._auth_provider

    @auth_provider.setter
    def auth_provider(self, value: Optional[AuthenticationProvider]):
        """Set the authentication provider and update internal clients."""
        self._auth_provider = value
        self._client.auth_provider = value

    def _request(self, query: str, variables: Optional[Dict] = None, context: Optional[str] = None) -> Any:
        """
        Make a GraphQL request using the ID token.

        Args:
            query: GraphQL query or mutation
            variables: Variables for the query
            context: Optional context string to include in error messages

        Returns:
            Response data
        """
        return self._client.request(query, variables, context)

    async def _request_async(
        self,
        session: aiohttp.ClientSession,
        query: str,
        variables: Optional[Dict] = None,
        context: Optional[str] = None,
    ) -> Any:
        """
        Async version of _request for parallel GraphQL requests.

        Args:
            session: aiohttp ClientSession
            query: GraphQL query or mutation
            variables: Variables for the query
            context: Optional context string to include in error messages

        Returns:
            Response data
        """
        return await self._client.request_async(session, query, variables, context)

    async def create_record_async(
        self, session: aiohttp.ClientSession, data: Dict, model_name: str, primary_field: str
    ) -> Optional[Dict]:
        """Create a single record asynchronously."""
        return await self._executor.create_record_async(session, data, model_name, primary_field)

    async def check_record_exists_async(
        self,
        session: aiohttp.ClientSession,
        model_name: str,
        primary_field: str,
        value: str,
        is_secondary_index: bool,
        record: Dict,
        field_type: str = "String",
    ) -> Optional[Dict]:
        """Check if a record already exists asynchronously."""
        return await self._executor.check_record_exists_async(
            session, model_name, primary_field, value, is_secondary_index, record, field_type
        )

    async def upload_batch_async(
        self,
        batch: List[Dict],
        model_name: str,
        primary_field: str,
        is_secondary_index: bool,
        field_type: str = "String",
    ) -> tuple[int, int, List[Dict]]:
        """Upload a batch of records asynchronously."""
        return await self._executor.upload_batch_async(batch, model_name, primary_field, is_secondary_index, field_type)

    def get_model_structure(self, model_type: str) -> Dict[str, Any]:
        """Get the GraphQL schema structure for a model type."""
        return self._executor.get_model_structure(model_type)

    def get_primary_field_name(self, model_name: str, parsed_model_structure: Dict[str, Any]) -> tuple[str, bool, str]:
        """Determine the primary field for a model."""
        return self._executor.get_primary_field_name(model_name, parsed_model_structure)

    def _get_secondary_index(self, model_name: str) -> str:
        """Find secondary index for a model."""
        return self._executor._get_secondary_index(model_name)

    def _get_list_query_name(self, model_name: str) -> Optional[str]:
        """Determine the correct list query name for a model."""
        return self._executor._get_list_query_name(model_name)

    def upload(
        self, records: List[Dict], model_name: str, parsed_model_structure: Dict[str, Any]
    ) -> tuple[int, int, List[Dict]]:
        """Upload multiple records in batches."""
        return self._executor.upload(records, model_name, parsed_model_structure)

    def list_records_by_secondary_index(
        self,
        model_name: str,
        secondary_index: str,
        value: Optional[str] = None,
        fields: Optional[List] = None,
        field_type: str = "String",
    ) -> Optional[List[Dict]]:
        """List records using a secondary index."""
        return self._executor.list_records_by_secondary_index(model_name, secondary_index, value, fields, field_type)

    def list_records_by_field(
        self, model_name: str, field_name: str, value: Optional[str] = None, fields: Optional[List] = None
    ) -> Optional[List[Dict]]:
        """List records filtered by a field value."""
        return self._executor.list_records_by_field(model_name, field_name, value, fields)

    def get_record_by_id(self, model_name: str, record_id: str, fields: Optional[List] = None) -> Optional[Dict]:
        """Get a single record by ID."""
        return self._executor.get_record_by_id(model_name, record_id, fields)

    def get_records(
        self,
        model_name: str,
        primary_field: Optional[str] = None,
        is_secondary_index: Optional[bool] = None,
        fields: Optional[List] = None,
    ) -> Optional[List[Dict]]:
        """Get all records for a model with caching."""
        return self._executor.get_records(model_name, primary_field, is_secondary_index, fields)

    def get_record(
        self,
        model_name: str,
        parsed_model_structure: Optional[Dict[str, Any]] = None,
        value: Optional[str] = None,
        record_id: Optional[str] = None,
        primary_field: Optional[str] = None,
        is_secondary_index: Optional[bool] = None,
        fields: Optional[List] = None,
    ) -> Optional[Dict]:
        """Get a single record by ID or by primary field value."""
        return self._executor.get_record(
            model_name, parsed_model_structure, value, record_id, primary_field, is_secondary_index, fields
        )

    def build_foreign_key_lookups(self, df, parsed_model_structure: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
        """Build a cache of foreign key lookups for all ID fields in the DataFrame."""
        return self._executor.build_foreign_key_lookups(df, parsed_model_structure)
