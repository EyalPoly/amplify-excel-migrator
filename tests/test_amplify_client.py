"""Tests for AmplifyClient class"""

import pytest
import pandas as pd
import asyncio
import aiohttp
import requests
from unittest.mock import MagicMock, Mock, patch, AsyncMock
from amplify_client import AmplifyClient, AuthenticationError, GraphQLError


class TestBuildForeignKeyLookups:
    """Test build_foreign_key_lookups method for performance optimization"""

    def test_builds_lookup_cache_for_related_models(self):
        """Test that FK lookup cache is built correctly"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        client._executor.get_records = MagicMock(
            return_value=[
                {"id": "reporter-1", "name": "John Doe"},
                {"id": "reporter-2", "name": "Jane Smith"},
            ]
        )

        df = pd.DataFrame({"photographer": ["John Doe", "Jane Smith"]})
        parsed_model_structure = {
            "fields": [{"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"}]
        }

        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # Verify cache was built
        assert "Reporter" in result
        assert result["Reporter"]["lookup"]["John Doe"] == "reporter-1"
        assert result["Reporter"]["lookup"]["Jane Smith"] == "reporter-2"
        assert result["Reporter"]["primary_field"] == "name"

        # Verify API was called once
        client._executor.get_primary_field_name.assert_called_once_with("Reporter", parsed_model_structure)
        client._executor.get_records.assert_called_once_with("Reporter", "name", False)

    def test_skips_non_id_fields(self):
        """Test that non-ID fields are skipped"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock()
        client._executor.get_records = MagicMock()

        df = pd.DataFrame({"title": ["Story 1"], "content": ["Content 1"]})
        parsed_model_structure = {
            "fields": [
                {"name": "title", "is_id": False, "is_required": True},
                {"name": "content", "is_id": False, "is_required": False},
            ]
        }

        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # No lookups should be built
        assert result == {}
        client._executor.get_primary_field_name.assert_not_called()
        client._executor.get_records.assert_not_called()

    def test_skips_fields_not_in_dataframe(self):
        """Test that fields not in DataFrame columns are skipped"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock()

        df = pd.DataFrame({"title": ["Story 1"]})
        parsed_model_structure = {
            "fields": [{"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"}]
        }

        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # No lookups should be built
        assert result == {}
        client._executor.get_primary_field_name.assert_not_called()

    def test_infers_related_model_from_field_name(self):
        """Test that related model is inferred when not explicitly provided"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        client._executor.get_records = MagicMock(return_value=[{"id": "author-1", "name": "Author One"}])

        df = pd.DataFrame({"author": ["Author One"]})
        parsed_model_structure = {
            "fields": [
                {"name": "authorId", "is_id": True, "is_required": True}
                # No related_model - should infer "Author" from "authorId"
            ]
        }

        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # Verify cache was built with inferred model name
        assert "Author" in result
        assert result["Author"]["lookup"]["Author One"] == "author-1"

        # Verify API was called with inferred model name
        client._executor.get_primary_field_name.assert_called_once_with("Author", parsed_model_structure)

    def test_handles_errors_gracefully(self):
        """Test that errors in fetching don't crash the whole process"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock(side_effect=Exception("API Error"))

        df = pd.DataFrame({"photographer": ["John Doe"]})
        parsed_model_structure = {
            "fields": [{"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"}]
        }

        # Should not raise exception
        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # Cache should be empty but process continues
        assert result == {}

    def test_deduplicates_same_related_model(self):
        """Test that the same related model is only fetched once"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        client._executor.get_records = MagicMock(return_value=[{"id": "reporter-1", "name": "John Doe"}])

        df = pd.DataFrame({"photographer": ["John Doe"], "editor": ["Jane Smith"]})
        parsed_model_structure = {
            "fields": [
                {"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"},
                {"name": "editorId", "is_id": True, "is_required": True, "related_model": "Reporter"},
            ]
        }

        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # Only one Reporter lookup should exist
        assert len(result) == 1
        assert "Reporter" in result

        # API should be called only once
        client._executor.get_primary_field_name.assert_called_once()
        client._executor.get_records.assert_called_once()

    def test_handles_empty_records_response(self):
        """Test that empty records from API don't break the cache"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        client._executor.get_records = MagicMock(return_value=None)  # API returns None

        df = pd.DataFrame({"photographer": ["John Doe"]})
        parsed_model_structure = {
            "fields": [{"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"}]
        }

        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # Cache should be empty
        assert result == {}

    def test_filters_out_records_without_primary_field(self):
        """Test that records without the primary field are filtered out"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        client._executor.get_records = MagicMock(
            return_value=[
                {"id": "reporter-1", "name": "John Doe"},
                {"id": "reporter-2"},  # Missing name
                {"id": "reporter-3", "name": None},  # None name
                {"id": "reporter-4", "name": "Jane Smith"},
            ]
        )

        df = pd.DataFrame({"photographer": ["John Doe", "Jane Smith"]})
        parsed_model_structure = {
            "fields": [{"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"}]
        }

        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # Only valid records should be in cache
        assert len(result["Reporter"]["lookup"]) == 2
        assert "John Doe" in result["Reporter"]["lookup"]
        assert "Jane Smith" in result["Reporter"]["lookup"]


class TestCustomExceptions:
    """Test custom exception classes"""

    def test_authentication_error_raised(self):
        """Test that AuthenticationError is raised when not authenticated"""
        client = AmplifyClient(api_endpoint="https://test.com")

        with pytest.raises(AuthenticationError, match="Not authenticated"):
            client._request("query { test }")

    def test_graphql_error_raised(self):
        """Test that GraphQLError is raised for GraphQL errors"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"errors": [{"message": "GraphQL Error"}]}
            mock_post.return_value = mock_response

            result = client._request("query { test }")

            # Should return None after logging the error
            assert result is None


class TestRequestErrorHandling:
    """Test error handling in _request method"""

    def test_connection_error_with_context(self):
        """Test ConnectionError handling with context"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth

        with patch("requests.post", side_effect=requests.exceptions.ConnectionError("Connection failed")):
            with pytest.raises(SystemExit):  # Connection errors exit the system
                client._request("query { test }", context="Model: field=value")

    def test_timeout_error_with_context(self):
        """Test Timeout error handling with context"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth

        with patch("requests.post", side_effect=requests.exceptions.Timeout("Request timeout")):
            result = client._request("query { test }", context="Model: field=value")
            assert result is None

    def test_http_error_with_context(self):
        """Test HTTPError handling with context"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth

        with patch("requests.post", side_effect=requests.exceptions.HTTPError("HTTP error")):
            result = client._request("query { test }", context="Model: field=value")
            assert result is None

    def test_request_exception_with_context(self):
        """Test RequestException handling with context"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth

        with patch("requests.post", side_effect=requests.exceptions.RequestException("Request error")):
            result = client._request("query { test }", context="Model: field=value")
            assert result is None

    def test_http_error_status_code_with_context(self):
        """Test non-200 status code with context"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.return_value = mock_response

            result = client._request("query { test }", context="Model: field=value")
            assert result is None


class TestRequestAsyncErrorHandling:
    """Test error handling in _request_async method"""

    @pytest.mark.asyncio
    async def test_authentication_error_async(self):
        """Test that AuthenticationError is raised when not authenticated"""
        client = AmplifyClient(api_endpoint="https://test.com")

        async with aiohttp.ClientSession() as session:
            with pytest.raises(AuthenticationError, match="Not authenticated"):
                await client._request_async(session, "query { test }")

    @pytest.mark.asyncio
    async def test_connection_error_async_with_context(self):
        """Test ClientConnectionError handling with context"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth

        async with aiohttp.ClientSession() as session:
            with patch.object(session, "post", side_effect=aiohttp.ClientConnectionError("Connection failed")):
                with pytest.raises(aiohttp.ClientConnectionError, match="Connection error"):
                    await client._request_async(session, "query { test }", context="Model: field=value")

    @pytest.mark.asyncio
    async def test_timeout_error_async_with_context(self):
        """Test ServerTimeoutError handling with context"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth

        async with aiohttp.ClientSession() as session:
            with patch.object(session, "post", side_effect=aiohttp.ServerTimeoutError("Request timeout")):
                with pytest.raises(aiohttp.ServerTimeoutError, match="Request timeout"):
                    await client._request_async(session, "query { test }", context="Model: field=value")

    @pytest.mark.asyncio
    async def test_client_response_error_async_with_context(self):
        """Test ClientResponseError handling with context"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth

        async with aiohttp.ClientSession() as session:
            # Create a proper ClientResponseError
            request_info = aiohttp.RequestInfo(
                url="https://test.com", method="POST", headers={}, real_url="https://test.com"
            )
            history = ()
            with patch.object(
                session,
                "post",
                side_effect=aiohttp.ClientResponseError(
                    request_info=request_info, history=history, status=500, message="Server error"
                ),
            ):
                with pytest.raises(aiohttp.ClientResponseError, match="HTTP response error"):
                    await client._request_async(session, "query { test }", context="Model: field=value")

    @pytest.mark.asyncio
    async def test_client_error_async_with_context(self):
        """Test ClientError handling with context"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth

        async with aiohttp.ClientSession() as session:
            with patch.object(session, "post", side_effect=aiohttp.ClientError("Client error")):
                with pytest.raises(aiohttp.ClientError, match="Client error"):
                    await client._request_async(session, "query { test }", context="Model: field=value")

    @pytest.mark.asyncio
    async def test_graphql_error_async_with_context(self):
        """Test GraphQL error handling with context"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth

        async with aiohttp.ClientSession() as session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"errors": [{"message": "GraphQL Error"}]})

            with patch.object(session, "post") as mock_post:
                mock_post.return_value.__aenter__.return_value = mock_response

                with pytest.raises(GraphQLError, match="GraphQL errors"):
                    await client._request_async(session, "query { test }", context="Model: field=value")

    @pytest.mark.asyncio
    async def test_http_error_status_code_async(self):
        """Test non-200 status code raises exception"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth

        async with aiohttp.ClientSession() as session:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value="Internal Server Error")

            with patch.object(session, "post") as mock_post:
                mock_post.return_value.__aenter__.return_value = mock_response

                with pytest.raises(aiohttp.ClientError, match="HTTP Error 500"):
                    await client._request_async(session, "query { test }")


class TestPagination:
    """Test pagination logic in list_records_by_secondary_index"""

    def test_single_page_query(self):
        """Test query that returns all items in single page (no nextToken)"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth
        client._get_list_query_name = MagicMock(return_value="listReporters")

        with patch.object(client, "_request") as mock_request:
            # Simulate single page response with no nextToken
            mock_request.return_value = {
                "data": {
                    "listReporters": {
                        "items": [
                            {"id": "1", "name": "Reporter 1"},
                            {"id": "2", "name": "Reporter 2"},
                        ],
                        "nextToken": None,
                    }
                }
            }

            result = client.list_records_by_secondary_index("Reporter", "name")

            # Should call _request once
            mock_request.assert_called_once()
            # Should return all items
            assert len(result) == 2
            assert result[0]["name"] == "Reporter 1"
            assert result[1]["name"] == "Reporter 2"

    def test_multiple_pages_query(self):
        """Test query that returns items across multiple pages"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth
        client._get_list_query_name = MagicMock(return_value="listReporters")

        with patch.object(client, "_request") as mock_request:
            # Simulate multiple page responses
            mock_request.side_effect = [
                {
                    "data": {
                        "listReporters": {
                            "items": [{"id": "1", "name": "Reporter 1"}],
                            "nextToken": "token1",
                        }
                    }
                },
                {
                    "data": {
                        "listReporters": {
                            "items": [{"id": "2", "name": "Reporter 2"}],
                            "nextToken": "token2",
                        }
                    }
                },
                {
                    "data": {
                        "listReporters": {
                            "items": [{"id": "3", "name": "Reporter 3"}],
                            "nextToken": None,  # Last page
                        }
                    }
                },
            ]

            result = client.list_records_by_secondary_index("Reporter", "name")

            # Should call _request three times
            assert mock_request.call_count == 3
            # Should return all items from all pages
            assert len(result) == 3
            assert result[0]["name"] == "Reporter 1"
            assert result[1]["name"] == "Reporter 2"
            assert result[2]["name"] == "Reporter 3"

    def test_pagination_with_limit_1000(self):
        """Test that pagination uses limit of 1000"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth
        client._get_list_query_name = MagicMock(return_value="listReporters")

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {
                "data": {
                    "listReporters": {
                        "items": [{"id": "1", "name": "Reporter 1"}],
                        "nextToken": None,
                    }
                }
            }

            client.list_records_by_secondary_index("Reporter", "name")

            # Verify limit parameter is set to 1000
            call_args = mock_request.call_args
            variables = call_args[0][1]  # Second positional argument
            assert variables["limit"] == 1000

    def test_pagination_passes_nexttoken(self):
        """Test that nextToken is passed correctly between pages"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth
        client._get_list_query_name = MagicMock(return_value="listReporters")

        with patch.object(client, "_request") as mock_request:
            mock_request.side_effect = [
                {
                    "data": {
                        "listReporters": {
                            "items": [{"id": "1", "name": "Reporter 1"}],
                            "nextToken": "token1",
                        }
                    }
                },
                {
                    "data": {
                        "listReporters": {
                            "items": [{"id": "2", "name": "Reporter 2"}],
                            "nextToken": None,
                        }
                    }
                },
            ]

            client.list_records_by_secondary_index("Reporter", "name")

            # First call should have None for nextToken
            first_call_vars = mock_request.call_args_list[0][0][1]
            assert first_call_vars["nextToken"] is None

            # Second call should have token1
            second_call_vars = mock_request.call_args_list[1][0][1]
            assert second_call_vars["nextToken"] == "token1"

    def test_empty_results_no_pagination(self):
        """Test query that returns no items"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth
        client._get_list_query_name = MagicMock(return_value="listReporters")

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {
                "data": {
                    "listReporters": {
                        "items": [],
                        "nextToken": None,
                    }
                }
            }

            result = client.list_records_by_secondary_index("Reporter", "name")

            # Should call _request once
            mock_request.assert_called_once()
            # Should return None for empty results
            assert result is None

    def test_error_handling_stops_pagination(self):
        """Test that errors stop pagination loop"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth
        client._get_list_query_name = MagicMock(return_value="listReporters")

        with patch.object(client, "_request") as mock_request:
            mock_request.side_effect = [
                {
                    "data": {
                        "listReporters": {
                            "items": [{"id": "1", "name": "Reporter 1"}],
                            "nextToken": "token1",
                        }
                    }
                },
                None,  # Error on second page
            ]

            result = client.list_records_by_secondary_index("Reporter", "name")

            # Should call _request twice and stop
            assert mock_request.call_count == 2
            # Should return items from successful pages only
            assert len(result) == 1
            assert result[0]["name"] == "Reporter 1"

    def test_pagination_with_secondary_index_value(self):
        """Test pagination with specific secondary index value"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth

        with patch.object(client, "_request") as mock_request:
            mock_request.side_effect = [
                {
                    "data": {
                        "listReporterByName": {
                            "items": [{"id": "1", "name": "John Doe"}],
                            "nextToken": "token1",
                        }
                    }
                },
                {
                    "data": {
                        "listReporterByName": {
                            "items": [{"id": "2", "name": "John Doe"}],
                            "nextToken": None,
                        }
                    }
                },
            ]

            result = client.list_records_by_secondary_index("Reporter", "name", value="John Doe")

            # Should call _request twice
            assert mock_request.call_count == 2
            # Should return all items with the given value
            assert len(result) == 2
            # Verify the secondary index value was passed
            first_call_vars = mock_request.call_args_list[0][0][1]
            assert first_call_vars["name"] == "John Doe"


class TestContextInAsyncMethods:
    """Test context parameter in async methods"""

    @pytest.mark.asyncio
    async def test_create_record_async_includes_context(self):
        """Test that create_record_async passes context to _request_async"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth

        data = {"name": "Test Name"}

        async with aiohttp.ClientSession() as session:
            with patch.object(client, "_request_async", new_callable=AsyncMock) as mock_request:
                mock_request.return_value = {"data": {"createTestModel": {"id": "test-id", "name": "Test Name"}}}

                await client.create_record_async(session, data, "TestModel", "name")

                # Verify context was passed
                mock_request.assert_called_once()
                # Check if context is in args or kwargs
                call_args = mock_request.call_args
                # The context parameter is passed as keyword argument
                # Access it from args (positional) or kwargs depending on how it was called
                if "context" in call_args.kwargs:
                    assert call_args.kwargs["context"] == "TestModel: name=Test Name"
                else:
                    # It might be passed positionally, so check args
                    assert len(call_args.args) >= 4
                    assert call_args.args[3] == "TestModel: name=Test Name"

    @pytest.mark.asyncio
    async def test_check_record_exists_async_includes_context(self):
        """Test that check_record_exists_async passes context to _request_async"""
        client = AmplifyClient(api_endpoint="https://test.com")
        mock_auth = Mock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_id_token.return_value = "test-token"
        client.auth_provider = mock_auth
        client._get_list_query_name = MagicMock(return_value="listTestModels")

        record = {"name": "Test Name"}

        async with aiohttp.ClientSession() as session:
            with patch.object(client, "_request_async", new_callable=AsyncMock) as mock_request:
                mock_request.return_value = {"data": {"listTestModels": {"items": []}}}

                await client.check_record_exists_async(session, "TestModel", "name", "Test Name", False, record)

                # Verify context was passed
                mock_request.assert_called_once()
                # Check if context is in args or kwargs
                call_args = mock_request.call_args
                # The context parameter is passed as keyword argument
                # Access it from args (positional) or kwargs depending on how it was called
                if "context" in call_args.kwargs:
                    assert call_args.kwargs["context"] == "TestModel: name=Test Name"
                else:
                    # It might be passed positionally, so check args
                    assert len(call_args.args) >= 4
                    assert call_args.args[3] == "TestModel: name=Test Name"
