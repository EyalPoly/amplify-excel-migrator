"""Tests for GraphQLClient class"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import aiohttp
import requests
from amplify_excel_migrator.graphql.client import GraphQLClient, AuthenticationError, GraphQLError


@pytest.fixture
def mock_auth_provider():
    """Create a mock authentication provider"""
    auth = MagicMock()
    auth.is_authenticated.return_value = True
    auth.get_id_token.return_value = "test-token"
    return auth


@pytest.fixture
def client(mock_auth_provider):
    """Create a GraphQLClient with mock auth provider"""
    return GraphQLClient(api_endpoint="https://test.api.com/graphql", auth_provider=mock_auth_provider)


@pytest.fixture
def unauthenticated_client():
    """Create a GraphQLClient without auth provider"""
    return GraphQLClient(api_endpoint="https://test.api.com/graphql")


class TestGraphQLClientInit:
    """Test GraphQLClient initialization"""

    def test_initializes_with_endpoint(self):
        client = GraphQLClient(api_endpoint="https://test.com/graphql")
        assert client.api_endpoint == "https://test.com/graphql"
        assert client.auth_provider is None

    def test_initializes_with_auth_provider(self, mock_auth_provider):
        client = GraphQLClient(api_endpoint="https://test.com/graphql", auth_provider=mock_auth_provider)
        assert client.api_endpoint == "https://test.com/graphql"
        assert client.auth_provider == mock_auth_provider


class TestRequest:
    """Test synchronous request method"""

    def test_raises_error_when_not_authenticated(self, unauthenticated_client):
        with pytest.raises(AuthenticationError, match="Not authenticated"):
            unauthenticated_client.request("{ test }")

    def test_raises_error_when_auth_provider_not_authenticated(self):
        auth = MagicMock()
        auth.is_authenticated.return_value = False
        client = GraphQLClient(api_endpoint="https://test.com/graphql", auth_provider=auth)

        with pytest.raises(AuthenticationError, match="Not authenticated"):
            client.request("{ test }")

    @patch("amplify_excel_migrator.graphql.client.requests.post")
    def test_makes_successful_request(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"getUser": {"id": "123"}}}
        mock_post.return_value = mock_response

        result = client.request("{ getUser { id } }")

        assert result == {"data": {"getUser": {"id": "123"}}}
        mock_post.assert_called_once_with(
            "https://test.api.com/graphql",
            headers={"Authorization": "test-token", "Content-Type": "application/json"},
            json={"query": "{ getUser { id } }", "variables": {}},
        )

    @patch("amplify_excel_migrator.graphql.client.requests.post")
    def test_includes_variables_in_request(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"getUser": {"id": "123"}}}
        mock_post.return_value = mock_response

        result = client.request("query GetUser($id: ID!) { getUser(id: $id) { id } }", variables={"id": "123"})

        assert result == {"data": {"getUser": {"id": "123"}}}
        called_json = mock_post.call_args[1]["json"]
        assert called_json["variables"] == {"id": "123"}

    @patch("amplify_excel_migrator.graphql.client.requests.post")
    def test_returns_none_when_errors_in_response(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"errors": [{"message": "Field not found"}]}
        mock_post.return_value = mock_response

        result = client.request("{ invalidField }")
        assert result is None

    @patch("amplify_excel_migrator.graphql.client.requests.post")
    def test_returns_none_with_context_in_error_message(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"errors": [{"message": "Error"}]}
        mock_post.return_value = mock_response

        result = client.request("{ test }", context="User Query")
        assert result is None

    @patch("amplify_excel_migrator.graphql.client.requests.post")
    def test_returns_none_on_non_200_status(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        result = client.request("{ test }")

        assert result is None

    @patch("amplify_excel_migrator.graphql.client.requests.post")
    def test_exits_on_connection_error(self, mock_post, client):
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

        with pytest.raises(SystemExit):
            client.request("{ test }")

    @patch("amplify_excel_migrator.graphql.client.requests.post")
    def test_returns_none_on_timeout(self, mock_post, client):
        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

        result = client.request("{ test }")

        assert result is None

    @patch("amplify_excel_migrator.graphql.client.requests.post")
    def test_returns_none_on_http_error(self, mock_post, client):
        mock_post.side_effect = requests.exceptions.HTTPError("HTTP Error")

        result = client.request("{ test }")

        assert result is None

    @patch("amplify_excel_migrator.graphql.client.requests.post")
    def test_returns_none_on_request_exception(self, mock_post, client):
        mock_post.side_effect = requests.exceptions.RequestException("Generic error")

        result = client.request("{ test }")

        assert result is None


class TestRequestAsync:
    """Test asynchronous request method"""

    @pytest.mark.asyncio
    async def test_raises_error_when_not_authenticated(self, unauthenticated_client):
        async with aiohttp.ClientSession() as session:
            with pytest.raises(AuthenticationError, match="Not authenticated"):
                await unauthenticated_client.request_async(session, "{ test }")

    @pytest.mark.asyncio
    async def test_raises_error_when_auth_provider_not_authenticated(self):
        auth = MagicMock()
        auth.is_authenticated.return_value = False
        client = GraphQLClient(api_endpoint="https://test.com/graphql", auth_provider=auth)

        async with aiohttp.ClientSession() as session:
            with pytest.raises(AuthenticationError, match="Not authenticated"):
                await client.request_async(session, "{ test }")

    @pytest.mark.asyncio
    async def test_makes_successful_async_request(self, client):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"data": {"getUser": {"id": "123"}}})

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.post.return_value.__aexit__ = AsyncMock()

        result = await client.request_async(mock_session, "{ getUser { id } }")

        assert result == {"data": {"getUser": {"id": "123"}}}
        mock_session.post.assert_called_once_with(
            "https://test.api.com/graphql",
            headers={"Authorization": "test-token", "Content-Type": "application/json"},
            json={"query": "{ getUser { id } }", "variables": {}},
        )

    @pytest.mark.asyncio
    async def test_includes_variables_in_async_request(self, client):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"data": {"getUser": {"id": "123"}}})

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.post.return_value.__aexit__ = AsyncMock()

        result = await client.request_async(
            mock_session, "query GetUser($id: ID!) { getUser(id: $id) { id } }", variables={"id": "123"}
        )

        assert result == {"data": {"getUser": {"id": "123"}}}
        called_json = mock_session.post.call_args[1]["json"]
        assert called_json["variables"] == {"id": "123"}

    @pytest.mark.asyncio
    async def test_raises_graphql_error_on_errors_in_async_response(self, client):
        async def mock_json():
            return {"errors": [{"message": "Field not found"}]}

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = mock_json

        class MockAsyncContextManager:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                pass

        mock_session = MagicMock()
        mock_session.post.return_value = MockAsyncContextManager()

        with pytest.raises(GraphQLError):
            await client.request_async(mock_session, "{ invalidField }")

    @pytest.mark.asyncio
    async def test_includes_context_in_async_error_message(self, client):
        async def mock_json():
            return {"errors": [{"message": "Error"}]}

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = mock_json

        class MockAsyncContextManager:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                pass

        mock_session = MagicMock()
        mock_session.post.return_value = MockAsyncContextManager()

        with pytest.raises(GraphQLError):
            await client.request_async(mock_session, "{ test }", context="User Query")

    @pytest.mark.asyncio
    async def test_raises_client_error_on_non_200_status(self, client):
        async def mock_text():
            return "Internal Server Error"

        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.text = mock_text

        class MockAsyncContextManager:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                pass

        mock_session = MagicMock()
        mock_session.post.return_value = MockAsyncContextManager()

        with pytest.raises(aiohttp.ClientError):
            await client.request_async(mock_session, "{ test }")

    @pytest.mark.asyncio
    async def test_raises_timeout_error_on_async_timeout(self, client):
        mock_session = MagicMock()
        mock_session.post = MagicMock()
        mock_session.post.return_value.__aenter__ = AsyncMock(side_effect=aiohttp.ServerTimeoutError("Timeout"))
        mock_session.post.return_value.__aexit__ = AsyncMock()

        with pytest.raises(aiohttp.ServerTimeoutError, match="Request timeout"):
            await client.request_async(mock_session, "{ test }")

    @pytest.mark.asyncio
    async def test_raises_connection_error_on_async_connection_error(self, client):
        mock_session = MagicMock()
        mock_session.post = MagicMock()
        mock_session.post.return_value.__aenter__ = AsyncMock(
            side_effect=aiohttp.ClientConnectionError("Connection failed")
        )
        mock_session.post.return_value.__aexit__ = AsyncMock()

        with pytest.raises(aiohttp.ClientConnectionError, match="Connection error"):
            await client.request_async(mock_session, "{ test }")

    @pytest.mark.asyncio
    async def test_raises_response_error_on_async_response_error(self, client):
        error = aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=400, message="Bad Request")

        mock_session = MagicMock()
        mock_session.post = MagicMock()
        mock_session.post.return_value.__aenter__ = AsyncMock(side_effect=error)
        mock_session.post.return_value.__aexit__ = AsyncMock()

        with pytest.raises(aiohttp.ClientResponseError, match="HTTP response error"):
            await client.request_async(mock_session, "{ test }")

    @pytest.mark.asyncio
    async def test_raises_generic_client_error(self, client):
        mock_session = MagicMock()
        mock_session.post = MagicMock()
        mock_session.post.return_value.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Generic error"))
        mock_session.post.return_value.__aexit__ = AsyncMock()

        with pytest.raises(aiohttp.ClientError, match="Client error"):
            await client.request_async(mock_session, "{ test }")


class TestExceptionClasses:
    """Test custom exception classes"""

    def test_authentication_error_is_exception(self):
        error = AuthenticationError("Not authenticated")
        assert isinstance(error, Exception)
        assert str(error) == "Not authenticated"

    def test_graphql_error_is_exception(self):
        error = GraphQLError("GraphQL error occurred")
        assert isinstance(error, Exception)
        assert str(error) == "GraphQL error occurred"
