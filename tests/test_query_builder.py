"""Tests for QueryBuilder class"""

import pytest
from amplify_excel_migrator.graphql import QueryBuilder


class TestBuildListQuery:
    """Test QueryBuilder.build_list_query() method"""

    def test_basic_list_query_with_pagination(self):
        """Test basic list query with pagination enabled"""
        query = QueryBuilder.build_list_query("User", fields=["id", "name", "email"])

        assert "query ListUsers" in query
        assert "$limit: Int" in query
        assert "$nextToken: String" in query
        assert "listUsers(limit: $limit, nextToken: $nextToken)" in query
        assert "items {" in query
        assert "id" in query
        assert "name" in query
        assert "email" in query
        assert "nextToken" in query

    def test_list_query_without_pagination(self):
        """Test list query without pagination"""
        query = QueryBuilder.build_list_query("Product", fields=["id", "title"], with_pagination=False)

        assert "query ListProducts" in query
        assert "$limit: Int" in query
        assert "$nextToken: String" not in query
        assert "listProducts(limit: $limit)" in query
        assert "nextToken" not in query  # Should not appear in response
        assert "id" in query
        assert "title" in query

    def test_list_query_default_fields(self):
        """Test list query with default fields (only id)"""
        query = QueryBuilder.build_list_query("Post")

        assert "query ListPosts" in query
        assert "id" in query
        assert "listPosts" in query

    def test_list_query_multiple_fields(self):
        """Test list query with multiple fields"""
        fields = ["id", "title", "content", "authorID", "createdAt"]
        query = QueryBuilder.build_list_query("Article", fields=fields)

        for field in fields:
            assert field in query


class TestBuildListQueryWithFilter:
    """Test QueryBuilder.build_list_query_with_filter() method"""

    def test_filtered_query_with_pagination(self):
        """Test filtered list query with pagination"""
        query = QueryBuilder.build_list_query_with_filter("User", fields=["id", "name"])

        assert "query ListUsers" in query
        assert "$filter: ModelUserFilterInput" in query
        assert "$limit: Int" in query
        assert "$nextToken: String" in query
        assert "listUsers(filter: $filter, limit: $limit, nextToken: $nextToken)" in query
        assert "items {" in query
        assert "nextToken" in query

    def test_filtered_query_without_pagination(self):
        """Test filtered list query without pagination"""
        query = QueryBuilder.build_list_query_with_filter("Product", fields=["id"], with_pagination=False)

        assert "query ListProducts" in query
        assert "$filter: ModelProductFilterInput" in query
        assert "$limit: Int" in query
        assert "$nextToken: String" not in query
        assert "listProducts(filter: $filter, limit: $limit)" in query
        assert "nextToken" not in query

    def test_filtered_query_default_fields(self):
        """Test filtered query with default fields"""
        query = QueryBuilder.build_list_query_with_filter("Comment")

        assert "query ListComments" in query
        assert "$filter: ModelCommentFilterInput" in query
        assert "id" in query


class TestBuildSecondaryIndexQuery:
    """Test QueryBuilder.build_secondary_index_query() method"""

    def test_secondary_index_query_with_pagination(self):
        """Test secondary index query with pagination"""
        query = QueryBuilder.build_secondary_index_query(
            "User", "email", fields=["id", "email", "name"], field_type="String"
        )

        assert "query listUserByEmail" in query
        assert "$email: String!" in query
        assert "$limit: Int" in query
        assert "$nextToken: String" in query
        assert "listUserByEmail(email: $email, limit: $limit, nextToken: $nextToken)" in query
        assert "id" in query
        assert "email" in query
        assert "name" in query
        assert "nextToken" in query

    def test_secondary_index_query_without_pagination(self):
        """Test secondary index query without pagination"""
        query = QueryBuilder.build_secondary_index_query(
            "Product", "sku", fields=["id", "sku"], field_type="String", with_pagination=False
        )

        assert "query listProductBySku" in query
        assert "$sku: String!" in query
        assert "$limit: Int" not in query
        assert "$nextToken: String" not in query
        assert "listProductBySku(sku: $sku)" in query
        assert "nextToken" not in query

    def test_secondary_index_query_different_field_types(self):
        """Test secondary index query with different field types"""
        # String type
        query_string = QueryBuilder.build_secondary_index_query("Order", "customerId", field_type="String")
        assert "$customerId: String!" in query_string

        # Int type
        query_int = QueryBuilder.build_secondary_index_query("Order", "orderNumber", field_type="Int")
        assert "$orderNumber: Int!" in query_int

        # ID type
        query_id = QueryBuilder.build_secondary_index_query("Comment", "postID", field_type="ID")
        assert "$postID: ID!" in query_id

    def test_secondary_index_query_capitalization(self):
        """Test that secondary index query name is properly capitalized"""
        query = QueryBuilder.build_secondary_index_query("User", "username", field_type="String")

        # Should capitalize first letter of field name
        assert "listUserByUsername" in query

    def test_secondary_index_query_default_fields(self):
        """Test secondary index query with default fields"""
        query = QueryBuilder.build_secondary_index_query("Product", "category", field_type="String")

        # Default should include id and the index field
        assert "id" in query
        assert "category" in query


class TestBuildGetByIdQuery:
    """Test QueryBuilder.build_get_by_id_query() method"""

    def test_get_by_id_basic(self):
        """Test basic get by ID query"""
        query = QueryBuilder.build_get_by_id_query("User", fields=["id", "name", "email"])

        assert "query GetUser" in query
        assert "$id: ID!" in query
        assert "getUser(id: $id)" in query
        assert "id" in query
        assert "name" in query
        assert "email" in query

    def test_get_by_id_default_fields(self):
        """Test get by ID with default fields (only id)"""
        query = QueryBuilder.build_get_by_id_query("Product")

        assert "query GetProduct" in query
        assert "$id: ID!" in query
        assert "getProduct(id: $id)" in query
        assert "id" in query

    def test_get_by_id_single_field(self):
        """Test get by ID with single field"""
        query = QueryBuilder.build_get_by_id_query("Post", fields=["title"])

        assert "query GetPost" in query
        assert "title" in query

    def test_get_by_id_many_fields(self):
        """Test get by ID with many fields"""
        fields = ["id", "title", "content", "authorID", "createdAt", "updatedAt", "published"]
        query = QueryBuilder.build_get_by_id_query("Article", fields=fields)

        for field in fields:
            assert field in query


class TestBuildIntrospectionQuery:
    """Test QueryBuilder.build_introspection_query() method"""

    def test_introspection_query_structure(self):
        """Test introspection query has correct structure"""
        query = QueryBuilder.build_introspection_query("User")

        assert "query IntrospectModel" in query
        assert '__type(name: "User")' in query
        assert "name" in query
        assert "fields {" in query
        assert "type {" in query
        assert "kind" in query
        assert "ofType {" in query

    def test_introspection_query_different_models(self):
        """Test introspection query with different model names"""
        models = ["User", "Product", "Order", "Comment"]

        for model in models:
            query = QueryBuilder.build_introspection_query(model)
            assert f'__type(name: "{model}")' in query
            assert "query IntrospectModel" in query


class TestBuildVariablesForList:
    """Test QueryBuilder.build_variables_for_list() method"""

    def test_variables_with_limit_only(self):
        """Test variables with only limit"""
        variables = QueryBuilder.build_variables_for_list(limit=100)

        assert variables == {"limit": 100}

    def test_variables_with_limit_and_next_token(self):
        """Test variables with limit and next token"""
        variables = QueryBuilder.build_variables_for_list(limit=50, next_token="abc123")

        assert variables == {"limit": 50, "nextToken": "abc123"}

    def test_variables_default_limit(self):
        """Test variables with default limit"""
        variables = QueryBuilder.build_variables_for_list()

        assert variables == {"limit": 1000}

    def test_variables_next_token_none(self):
        """Test that None next_token is not included"""
        variables = QueryBuilder.build_variables_for_list(limit=100, next_token=None)

        assert "nextToken" not in variables
        assert variables == {"limit": 100}


class TestBuildVariablesForFilter:
    """Test QueryBuilder.build_variables_for_filter() method"""

    def test_variables_with_simple_filter(self):
        """Test variables with simple filter"""
        filter_dict = {"name": {"eq": "John"}}
        variables = QueryBuilder.build_variables_for_filter(filter_dict, limit=100)

        assert variables == {"filter": {"name": {"eq": "John"}}, "limit": 100}

    def test_variables_with_filter_and_next_token(self):
        """Test variables with filter and next token"""
        filter_dict = {"status": {"eq": "active"}}
        variables = QueryBuilder.build_variables_for_filter(filter_dict, limit=50, next_token="xyz789")

        assert variables == {"filter": {"status": {"eq": "active"}}, "limit": 50, "nextToken": "xyz789"}

    def test_variables_with_complex_filter(self):
        """Test variables with complex filter"""
        filter_dict = {"and": [{"age": {"gt": 18}}, {"status": {"eq": "active"}}]}
        variables = QueryBuilder.build_variables_for_filter(filter_dict)

        assert variables["filter"] == filter_dict
        assert variables["limit"] == 1000

    def test_variables_filter_none_next_token(self):
        """Test that None next_token is not included"""
        filter_dict = {"email": {"contains": "@example.com"}}
        variables = QueryBuilder.build_variables_for_filter(filter_dict, next_token=None)

        assert "nextToken" not in variables
        assert variables == {"filter": filter_dict, "limit": 1000}


class TestBuildVariablesForSecondaryIndex:
    """Test QueryBuilder.build_variables_for_secondary_index() method"""

    def test_variables_with_index_value(self):
        """Test variables with index field and value"""
        variables = QueryBuilder.build_variables_for_secondary_index("email", "test@example.com", limit=100)

        assert variables == {"email": "test@example.com", "limit": 100}

    def test_variables_with_index_and_next_token(self):
        """Test variables with index field, value, and next token"""
        variables = QueryBuilder.build_variables_for_secondary_index("sku", "PROD-123", limit=50, next_token="token456")

        assert variables == {"sku": "PROD-123", "limit": 50, "nextToken": "token456"}

    def test_variables_default_limit(self):
        """Test variables with default limit"""
        variables = QueryBuilder.build_variables_for_secondary_index("username", "john_doe")

        assert variables == {"username": "john_doe", "limit": 1000}

    def test_variables_different_value_types(self):
        """Test variables with different value types"""
        # String value
        vars_string = QueryBuilder.build_variables_for_secondary_index("name", "Alice")
        assert vars_string["name"] == "Alice"

        # Integer value
        vars_int = QueryBuilder.build_variables_for_secondary_index("age", 25)
        assert vars_int["age"] == 25

        # Boolean value
        vars_bool = QueryBuilder.build_variables_for_secondary_index("isActive", True)
        assert vars_bool["isActive"] is True


class TestBuildFilterEquals:
    """Test QueryBuilder.build_filter_equals() method"""

    def test_filter_equals_string(self):
        """Test filter equals with string value"""
        filter_dict = QueryBuilder.build_filter_equals("name", "John")

        assert filter_dict == {"name": {"eq": "John"}}

    def test_filter_equals_number(self):
        """Test filter equals with number value"""
        filter_dict = QueryBuilder.build_filter_equals("age", 30)

        assert filter_dict == {"age": {"eq": 30}}

    def test_filter_equals_boolean(self):
        """Test filter equals with boolean value"""
        filter_dict = QueryBuilder.build_filter_equals("isActive", True)

        assert filter_dict == {"isActive": {"eq": True}}

    def test_filter_equals_none(self):
        """Test filter equals with None value"""
        filter_dict = QueryBuilder.build_filter_equals("deletedAt", None)

        assert filter_dict == {"deletedAt": {"eq": None}}


class TestQueryBuilderIntegration:
    """Integration tests for QueryBuilder"""

    def test_list_query_builds_valid_graphql(self):
        """Test that list query builds syntactically valid GraphQL"""
        query = QueryBuilder.build_list_query("User", fields=["id", "name"])

        # Should have matching braces
        assert query.count("{") == query.count("}")
        # Should have query keyword
        assert query.startswith("query ")

    def test_mutation_and_query_are_different(self):
        """Test that queries don't contain mutation keywords"""
        query = QueryBuilder.build_list_query("User")

        assert "mutation" not in query.lower()
        assert "query" in query.lower()

    def test_field_indentation_consistent(self):
        """Test that fields are properly indented in queries"""
        query = QueryBuilder.build_list_query("User", fields=["id", "name", "email"])

        # Fields should be indented (have leading spaces)
        lines = query.split("\n")
        field_lines = [line for line in lines if "id" in line or "name" in line or "email" in line]

        for line in field_lines:
            # Fields inside items should be indented
            if line.strip() in ["id", "name", "email"]:
                assert line.startswith("            ")  # 12 spaces for items fields

    def test_pagination_variables_match_query_signature(self):
        """Test that pagination variables match the query signature"""
        query_with_pagination = QueryBuilder.build_list_query("User", with_pagination=True)
        query_without_pagination = QueryBuilder.build_list_query("User", with_pagination=False)

        # With pagination should have both limit and nextToken
        assert "$limit: Int" in query_with_pagination
        assert "$nextToken: String" in query_with_pagination

        # Without pagination should only have limit
        assert "$limit: Int" in query_without_pagination
        assert "$nextToken: String" not in query_without_pagination
