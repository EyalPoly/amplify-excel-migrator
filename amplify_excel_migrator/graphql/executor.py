"""Query executor for high-level GraphQL operations."""

import asyncio
import logging
from typing import Dict, Any, Optional, List

import aiohttp

from .client import GraphQLClient
from .query_builder import QueryBuilder
from .mutation_builder import MutationBuilder
from amplify_excel_migrator.schema import SchemaIntrospector

logger = logging.getLogger(__name__)


class QueryExecutor:
    def __init__(self, client: GraphQLClient, batch_size: int = 20):
        self.client = client
        self.batch_size = batch_size
        self.records_cache: Dict[str, List[Dict]] = {}
        self.schema = SchemaIntrospector(client)

    def get_model_structure(self, model_type: str) -> Dict[str, Any]:
        return self.schema.get_model_structure(model_type)

    def get_all_types(self) -> list[Dict[str, Any]]:
        return self.schema.get_all_types()

    def get_primary_field_name(self, model_name: str, parsed_model_structure: Dict[str, Any]) -> tuple[str, bool, str]:
        return self.schema.get_primary_field_name(model_name, parsed_model_structure)

    def _get_list_query_name(self, model_name: str) -> Optional[str]:
        return self.schema.get_list_query_name(model_name)

    def list_records_by_secondary_index(
        self,
        model_name: str,
        secondary_index: str,
        value: Optional[str] = None,
        fields: Optional[List[str]] = None,
        field_type: str = "String",
    ) -> Optional[List[Dict]]:
        if fields is None:
            fields = ["id", secondary_index]

        all_items = []
        next_token = None

        if not value:
            query = QueryBuilder.build_list_query(model_name, fields=fields)
            query_name = self._get_list_query_name(model_name)

            while True:
                variables = QueryBuilder.build_variables_for_list(next_token=next_token)
                result = self.client.request(query, variables)

                if result and "data" in result:
                    data = result["data"].get(query_name, {})
                    items = data.get("items", [])
                    all_items.extend(items)
                    next_token = data.get("nextToken")

                    if not next_token:
                        break
                else:
                    break
        else:
            query = QueryBuilder.build_secondary_index_query(
                model_name, secondary_index, fields=fields, field_type=field_type
            )
            query_name = f"list{model_name}By{secondary_index[0].upper() + secondary_index[1:]}"

            while True:
                variables = {secondary_index: value, "limit": 1000, "nextToken": next_token}
                result = self.client.request(query, variables)

                if result and "data" in result:
                    data = result["data"].get(query_name, {})
                    items = data.get("items", [])
                    all_items.extend(items)
                    next_token = data.get("nextToken")

                    if not next_token:
                        break
                else:
                    break

        return all_items if all_items else None

    def list_records_by_field(
        self, model_name: str, field_name: str, value: Optional[str] = None, fields: Optional[List[str]] = None
    ) -> Optional[List[Dict]]:
        if fields is None:
            fields = ["id", field_name]

        all_items = []
        next_token = None
        query_name = self._get_list_query_name(model_name)

        if not value:
            query = QueryBuilder.build_list_query(model_name, fields=fields)

            while True:
                variables = QueryBuilder.build_variables_for_list(next_token=next_token)
                result = self.client.request(query, variables)

                if result and "data" in result:
                    data = result["data"].get(query_name, {})
                    items = data.get("items", [])
                    all_items.extend(items)
                    next_token = data.get("nextToken")

                    if not next_token:
                        break
                else:
                    break
        else:
            query = QueryBuilder.build_list_query_with_filter(model_name, fields=fields)
            filter_input = QueryBuilder.build_filter_equals(field_name, value)

            while True:
                variables = {"filter": filter_input, "limit": 1000, "nextToken": next_token}
                result = self.client.request(query, variables)

                if result and "data" in result:
                    data = result["data"].get(query_name, {})
                    items = data.get("items", [])
                    all_items.extend(items)
                    next_token = data.get("nextToken")

                    if not next_token:
                        break
                else:
                    break

        return all_items if all_items else None

    def get_record_by_id(self, model_name: str, record_id: str, fields: Optional[List[str]] = None) -> Optional[Dict]:
        if fields is None:
            fields = ["id"]

        query = QueryBuilder.build_get_by_id_query(model_name, fields=fields)
        query_name = f"get{model_name}"

        result = self.client.request(query, {"id": record_id})

        if result and "data" in result:
            return result["data"].get(query_name)

        return None

    def get_records(
        self,
        model_name: str,
        primary_field: Optional[str] = None,
        is_secondary_index: Optional[bool] = None,
        fields: Optional[List[str]] = None,
    ) -> Optional[List[Dict]]:
        if model_name in self.records_cache:
            return self.records_cache[model_name]

        if not primary_field:
            return None

        if is_secondary_index:
            records = self.list_records_by_secondary_index(model_name, primary_field, fields=fields)
        else:
            records = self.list_records_by_field(model_name, primary_field, fields=fields)

        if records:
            self.records_cache[model_name] = records
            logger.debug(f"💾 Cached {len(records)} records for {model_name}")

        return records

    def get_record(
        self,
        model_name: str,
        parsed_model_structure: Optional[Dict[str, Any]] = None,
        value: Optional[str] = None,
        record_id: Optional[str] = None,
        primary_field: Optional[str] = None,
        is_secondary_index: Optional[bool] = None,
        fields: Optional[List[str]] = None,
    ) -> Optional[Dict]:
        if record_id:
            return self.get_record_by_id(model_name, record_id)

        if not primary_field:
            if not parsed_model_structure:
                logger.error("Parsed model structure required if primary_field not provided")
                return None
            primary_field, is_secondary_index, _ = self.get_primary_field_name(model_name, parsed_model_structure)

        records = self.get_records(model_name, primary_field, is_secondary_index, fields)
        if not records:
            return None

        return next((record for record in records if record.get(primary_field) == value), None)

    async def create_record_async(
        self, session: aiohttp.ClientSession, data: Dict, model_name: str, primary_field: str
    ) -> Optional[Dict]:
        mutation = MutationBuilder.build_create_mutation(model_name, return_fields=["id", primary_field])
        variables = MutationBuilder.build_create_variables(data)

        context = f"{model_name}: {primary_field}={data.get(primary_field)}"
        result = await self.client.request_async(session, mutation, variables, context)

        if result and "data" in result:
            created = result["data"].get(f"create{model_name}")
            if created:
                logger.info(f'Created {model_name} with {primary_field}="{data[primary_field]}" (ID: {created["id"]})')
            return created
        else:
            logger.error(f'Failed to create {model_name} with {primary_field}="{data[primary_field]}"')

        return None

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
        context = f"{model_name}: {primary_field}={value}"

        if is_secondary_index:
            query = QueryBuilder.build_secondary_index_query(
                model_name, primary_field, fields=["id"], field_type=field_type, with_pagination=False
            )
            variables = {primary_field: value}
            query_name = f"list{model_name}By{primary_field[0].upper() + primary_field[1:]}"

            result = await self.client.request_async(session, query, variables, context)
            if result and "data" in result:
                items = result["data"].get(query_name, {}).get("items", [])
                if len(items) > 0:
                    logger.warning(f'Record with {primary_field}="{value}" already exists in {model_name}')
                    return None
        else:
            query_name = self._get_list_query_name(model_name)
            query = QueryBuilder.build_list_query_with_filter(model_name, fields=["id"], with_pagination=False)
            filter_input = QueryBuilder.build_filter_equals(primary_field, value)
            variables = {"filter": filter_input}

            result = await self.client.request_async(session, query, variables, context)
            if result and "data" in result:
                items = result["data"].get(query_name, {}).get("items", [])
                if len(items) > 0:
                    logger.error(f'Record with {primary_field}="{value}" already exists in {model_name}')
                    return None

        return record

    async def upload_batch_async(
        self,
        batch: List[Dict],
        model_name: str,
        primary_field: str,
        is_secondary_index: bool,
        field_type: str = "String",
    ) -> tuple[int, int, List[Dict]]:
        async with aiohttp.ClientSession() as session:
            duplicate_checks = [
                self.check_record_exists_async(
                    session, model_name, primary_field, record[primary_field], is_secondary_index, record, field_type
                )
                for record in batch
            ]
            check_results = await asyncio.gather(*duplicate_checks, return_exceptions=True)

            filtered_batch = []
            failed_records = []

            for i, result in enumerate(check_results):
                if isinstance(result, Exception):
                    error_msg = str(result)
                    failed_records.append(
                        {
                            "primary_field": primary_field,
                            "primary_field_value": batch[i].get(primary_field, "Unknown"),
                            "error": f"Duplicate check error: {error_msg}",
                        }
                    )
                    logger.error(f"Error checking duplicate: {result}")
                elif result is not None:
                    filtered_batch.append(result)

            if not filtered_batch:
                return 0, len(batch), failed_records

            create_tasks = [
                self.create_record_async(session, record, model_name, primary_field) for record in filtered_batch
            ]
            results = await asyncio.gather(*create_tasks, return_exceptions=True)

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    error_msg = str(result)
                    failed_records.append(
                        {
                            "primary_field": primary_field,
                            "primary_field_value": filtered_batch[i].get(primary_field, "Unknown"),
                            "error": error_msg,
                        }
                    )
                elif not result:
                    failed_records.append(
                        {
                            "primary_field": primary_field,
                            "primary_field_value": filtered_batch[i].get(primary_field, "Unknown"),
                            "error": "Creation failed - no response",
                        }
                    )

            success_count = sum(1 for r in results if r and not isinstance(r, Exception))
            error_count = len(batch) - success_count

            return success_count, error_count, failed_records

    def upload(
        self, records: List[Dict], model_name: str, parsed_model_structure: Dict[str, Any]
    ) -> tuple[int, int, List[Dict]]:
        logger.info("Uploading to Amplify backend...")

        success_count = 0
        error_count = 0
        all_failed_records = []
        num_of_batches = (len(records) + self.batch_size - 1) // self.batch_size

        primary_field, is_secondary_index, field_type = self.get_primary_field_name(model_name, parsed_model_structure)
        if not primary_field:
            logger.error(f"Aborting upload for model {model_name}")
            return 0, len(records), []

        for i in range(0, len(records), self.batch_size):
            batch = records[i : i + self.batch_size]
            logger.info(f"Uploading batch {i // self.batch_size + 1} / {num_of_batches} ({len(batch)} items)...")

            batch_success, batch_error, batch_failed_records = asyncio.run(
                self.upload_batch_async(batch, model_name, primary_field, is_secondary_index, field_type)
            )
            success_count += batch_success
            error_count += batch_error
            all_failed_records.extend(batch_failed_records)

            logger.info(
                f"Processed batch {i // self.batch_size + 1} of model {model_name}: {success_count} success, {error_count} errors"
            )

        return success_count, error_count, all_failed_records

    def build_foreign_key_lookups(self, df, parsed_model_structure: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
        """
        Build a cache of foreign key lookups for all ID fields in the DataFrame.

        This pre-fetches all related records to avoid N+1 query problems during row processing.

        Args:
            df: pandas DataFrame containing the data to be processed
            parsed_model_structure: Parsed model structure containing field information

        Returns:
            Dictionary mapping model names to lookup dictionaries and primary fields
        """
        fk_lookup_cache = {}

        for field in parsed_model_structure["fields"]:
            if not field["is_id"]:
                continue

            field_name = field["name"][:-2]

            if field_name not in df.columns:
                continue

            if "related_model" in field:
                related_model = field["related_model"]
            else:
                related_model = field_name[0].upper() + field_name[1:]

            if related_model in fk_lookup_cache:
                continue

            try:
                primary_field, is_secondary_index, _ = self.get_primary_field_name(
                    related_model, parsed_model_structure
                )
                records = self.get_records(related_model, primary_field, is_secondary_index)

                if records:
                    lookup = {
                        str(record.get(primary_field)): record.get("id")
                        for record in records
                        if record.get(primary_field)
                    }
                    fk_lookup_cache[related_model] = {"lookup": lookup, "primary_field": primary_field}
                    logger.debug(f"  📦 Cached {len(lookup)} {related_model} records")
            except Exception as e:
                logger.warning(f"  ⚠️  Could not pre-fetch {related_model}: {e}")

        return fk_lookup_cache
