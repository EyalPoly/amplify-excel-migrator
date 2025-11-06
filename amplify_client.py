import asyncio
import logging
import sys
import time
from functools import wraps
from getpass import getpass
from typing import Dict, Any

import aiohttp
import boto3
import requests
import jwt
import inflect
from botocore.exceptions import NoCredentialsError, ProfileNotFound, NoRegionError, ClientError
from pycognito import Cognito, MFAChallengeException
from pycognito.exceptions import ForceChangePasswordException

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# Performance timing decorator
def timing_decorator(func):
    """Decorator to measure and log function execution time"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        elapsed = end - start
        logger.info(f"⏱️  {func.__name__} took {elapsed:.4f}s")
        return result

    return wrapper


class AmplifyClient:
    """
    Client for Amplify GraphQL using ADMIN_USER_PASSWORD_AUTH flow
    """

    def __init__(self, api_endpoint: str, user_pool_id: str, region: str, client_id: str):
        """
        Initialize the client

        Args:
            api_endpoint: Amplify GraphQL endpoint
            user_pool_id: Cognito User Pool ID
            region: AWS region
            client_id: Cognito App Client ID
        """

        self.api_endpoint = api_endpoint
        self.user_pool_id = user_pool_id
        self.region = region
        self.client_id = client_id

        self.batch_size = 10
        self.cognito_client = None
        self.boto_cognito_admin_client = None
        self.id_token = None
        self.mfa_tokens = None
        self.admin_group_name = "ADMINS"

        self.records_cache = {}

    def init_cognito_client(self, is_aws_admin: bool, username: str = None, aws_profile: str = None):
        try:
            if is_aws_admin:
                if aws_profile:
                    session = boto3.Session(profile_name=aws_profile)
                    self.boto_cognito_admin_client = session.client("cognito-idp", region_name=self.region)
                else:
                    # Use default AWS credentials (from ~/.aws/credentials, env vars, or IAM role)
                    self.boto_cognito_admin_client = boto3.client("cognito-idp", region_name=self.region)

            else:
                self.cognito_client = Cognito(
                    user_pool_id=self.user_pool_id,
                    client_id=self.client_id,
                    user_pool_region=self.region,
                    username=username,
                )

        except NoCredentialsError:
            logger.error("AWS credentials not found. Please configure AWS credentials.")
            logger.error("Options: 1) AWS CLI: 'aws configure', 2) Environment variables, 3) Pass credentials directly")
            raise RuntimeError(
                "Failed to initialize client: No AWS credentials found. "
                "Run 'aws configure' or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables."
            )

        except ProfileNotFound:
            logger.error(f"AWS profile '{aws_profile}' not found")
            raise RuntimeError(
                f"Failed to initialize client: AWS profile '{aws_profile}' not found. "
                f"Available profiles can be found in ~/.aws/credentials"
            )

        except NoRegionError:
            logger.error("No AWS region specified")
            raise RuntimeError(
                f"Failed to initialize client: No AWS region specified. "
                f"Provide region parameter or set AWS_DEFAULT_REGION environment variable."
            )

        except ValueError as e:
            logger.error(f"Invalid parameter: {e}")
            raise

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"AWS Client Error [{error_code}]: {error_msg}")
            raise RuntimeError(f"Failed to initialize client: AWS error [{error_code}]: {error_msg}")

        except Exception as e:
            logger.error(f"Error during client initialization: {e}")
            raise RuntimeError(f"Failed to initialize client: {e}")

    def authenticate(self, username: str, password: str, mfa_code: str = None) -> bool:
        try:
            if not self.cognito_client:
                self.init_cognito_client(is_aws_admin=False, username=username)

            if mfa_code and self.mfa_tokens:
                if not self._complete_mfa_challenge(mfa_code):
                    return False
            else:
                self.cognito_client.authenticate(password=password)

            self.id_token = self.cognito_client.id_token

            self._check_user_in_admins_group(self.id_token)

            logger.info("✅ Authentication successful")
            return True

        except MFAChallengeException as e:
            logger.warning("MFA required")
            if hasattr(e, "get_tokens"):
                self.mfa_tokens = e.get_tokens()

                mfa_code = input("Enter MFA code: ").strip()
                if mfa_code:
                    return self.authenticate(username, password, mfa_code)
                else:
                    logger.error("MFA code required but not provided")
                    return False
            else:
                logger.error("MFA challenge received but no session tokens available")
                return False

        except ForceChangePasswordException:
            logger.warning("Password change required")
            new_password = input("Your password has expired. Enter new password: ").strip()
            confirm_password = input("Confirm new password: ").strip()
            if new_password != confirm_password:
                logger.error("Passwords do not match")
                return False

            try:
                self.cognito_client.new_password_challenge(password, new_password)
                return self.authenticate(username, new_password)

            except Exception as e:
                logger.error(f"Failed to change password: {e}")
                return False

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def aws_admin_authenticate(self, username: str, password: str) -> bool:
        """
        Requires AWS credentials with cognito-idp:ListUserPoolClients permission
        """
        try:
            if not self.boto_cognito_admin_client:
                self.init_cognito_client(is_aws_admin=True)

            print(f"Authenticating {username} using ADMIN_USER_PASSWORD_AUTH flow...")

            response = self.boto_cognito_admin_client.admin_initiate_auth(
                UserPoolId=self.user_pool_id,
                ClientId=self.client_id,
                AuthFlow="ADMIN_USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": username, "PASSWORD": password},
            )

            self._check_for_mfa_challenges(response, username)

            if "AuthenticationResult" in response:
                self.id_token = response["AuthenticationResult"]["IdToken"]
            else:
                logger.error("❌ Authentication failed: No AuthenticationResult in response")
                return False

            self._check_user_in_admins_group(self.id_token)

            print(f"✅ Authentication successful")
            return True

        except self.cognito_client.exceptions.NotAuthorizedException as e:
            logger.error(f"❌ Authentication failed: {e}")
            return False

        except self.cognito_client.exceptions.UserNotFoundException:
            logger.error(f"❌ User not found: {username}")
            return False

        except Exception as e:
            logger.error(f"❌ Error during authentication: {e}")
            return False

    def _complete_mfa_challenge(self, mfa_code: str) -> bool:
        try:
            if not self.mfa_tokens:
                logger.error("No MFA session tokens available")
                return False

            challenge_name = self.mfa_tokens.get("ChallengeName", "SMS_MFA")

            if "SOFTWARE_TOKEN" in challenge_name:
                self.cognito_client.respond_to_software_token_mfa_challenge(code=mfa_code, mfa_tokens=self.mfa_tokens)
            else:
                self.cognito_client.respond_to_sms_mfa_challenge(code=mfa_code, mfa_tokens=self.mfa_tokens)

            logger.info("✅ MFA challenge successful")
            return True

        except Exception as e:
            logger.error(f"MFA challenge failed: {e}")
            return False

    def _get_client_id(self) -> str:
        if self.client_id:
            return self.client_id

        try:
            if not self.boto_cognito_admin_client:
                self.boto_cognito_admin_client(is_aws_admin=True)
            response = self.boto_cognito_admin_client.list_user_pool_clients(UserPoolId=self.user_pool_id, MaxResults=1)

            if response["UserPoolClients"]:
                client_id = response["UserPoolClients"][0]["ClientId"]
                return client_id

            raise Exception("No User Pool clients found")

        except self.cognito_client.exceptions.ResourceNotFoundException:
            raise Exception(f"User Pool not found or AWS credentials lack permission")
        except Exception as e:
            raise Exception(f"Failed to get Client ID: {e}")

    def _check_for_mfa_challenges(self, response, username: str) -> bool:
        if "ChallengeName" in response:
            challenge = response["ChallengeName"]

            if challenge == "MFA_SETUP":
                logger.error("MFA setup required")
                return False

            elif challenge == "SMS_MFA" or challenge == "SOFTWARE_TOKEN_MFA":
                mfa_code = input("Enter MFA code: ")
                _ = self.cognito_client.admin_respond_to_auth_challenge(
                    UserPoolId=self.user_pool_id,
                    ClientId=self.client_id,
                    ChallengeName=challenge,
                    Session=response["Session"],
                    ChallengeResponses={
                        "USERNAME": username,
                        "SMS_MFA_CODE" if challenge == "SMS_MFA" else "SOFTWARE_TOKEN_MFA_CODE": mfa_code,
                    },
                )

            elif challenge == "NEW_PASSWORD_REQUIRED":
                new_password = getpass("Enter new password: ")
                _ = self.cognito_client.admin_respond_to_auth_challenge(
                    UserPoolId=self.user_pool_id,
                    ClientId=self.client_id,
                    ChallengeName=challenge,
                    Session=response["Session"],
                    ChallengeResponses={"USERNAME": username, "NEW_PASSWORD": new_password},
                )

        return False

    def _check_user_in_admins_group(self, id_token: str):
        print(jwt.__version__)

        claims = jwt.decode(id_token, options={"verify_signature": False})
        groups = claims.get("cognito:groups", [])

        if self.admin_group_name not in groups:
            raise PermissionError("User is not in ADMINS group")

    def _request(self, query: str, variables: Dict = None) -> Any | None:
        """
        Make a GraphQL request using the ID token

        Args:
            query: GraphQL query or mutation
            variables: Variables for the query

        Returns:
            Response data
        """
        if not self.id_token:
            raise Exception("Not authenticated. Call authenticate() first.")

        headers = {"Authorization": self.id_token, "Content-Type": "application/json"}

        payload = {"query": query, "variables": variables or {}}

        try:
            response = requests.post(self.api_endpoint, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()

                if "errors" in result:
                    logger.error(f"GraphQL errors: {result['errors']}")
                    return None

                return result
            else:
                logger.error(f"HTTP Error {response.status_code}: {response.text}")
                return None

        except Exception as e:
            if "NameResolutionError" in str(e):
                logger.error(
                    f"Connection error: Unable to resolve hostname. Check your internet connection or the API endpoint URL."
                )
                sys.exit(1)
            else:
                logger.error(f"Request error: {e}")
            return None

    async def _request_async(self, session: aiohttp.ClientSession, query: str, variables: Dict = None) -> Any | None:
        """
        Async version of _request for parallel GraphQL requests

        Args:
            session: aiohttp ClientSession
            query: GraphQL query or mutation
            variables: Variables for the query

        Returns:
            Response data
        """
        if not self.id_token:
            raise Exception("Not authenticated. Call authenticate() first.")

        headers = {"Authorization": self.id_token, "Content-Type": "application/json"}

        payload = {"query": query, "variables": variables or {}}

        try:
            async with session.post(self.api_endpoint, headers=headers, json=payload) as response:
                if response.status == 200:
                    result = await response.json()

                    if "errors" in result:
                        logger.error(f"GraphQL errors: {result['errors']}")
                        return None

                    return result
                else:
                    text = await response.text()
                    logger.error(f"HTTP Error {response.status}: {text}")
                    return None
        except Exception as e:
            logger.error(f"Request error: {e}")
            return None

    async def create_record_async(
        self, session: aiohttp.ClientSession, data: Dict, model_name: str, primary_field: str
    ) -> Dict | None:
        mutation = f"""
        mutation Create{model_name}($input: Create{model_name}Input!)  {{
            create{model_name}(input: $input) {{
                id
                {primary_field}
            }}
        }}
        """

        result = await self._request_async(session, mutation, {"input": data})

        if result and "data" in result:
            created = result["data"].get(f"create{model_name}")
            if created:
                logger.info(f'Created {model_name} with {primary_field}="{data[primary_field]}" (ID: {created["id"]})')
            return created

        return None

    async def check_record_exists_async(
        self,
        session: aiohttp.ClientSession,
        model_name: str,
        primary_field: str,
        value: str,
        is_secondary_index: bool,
        record: Dict,
    ) -> Dict | None:
        if is_secondary_index:
            query_name = f"list{model_name}By{primary_field[0].upper() + primary_field[1:]}"
            query = f"""
            query {query_name}(${primary_field}: String!) {{
              {query_name}({primary_field}: ${primary_field}) {{
                items {{
                    id
                }}
              }}
            }}
            """
            result = await self._request_async(session, query, {primary_field: value})
            if result and "data" in result:
                items = result["data"].get(query_name, {}).get("items", [])
                if len(items) > 0:
                    logger.error(f'Record with {primary_field}="{value}" already exists in {model_name}')
                    return None
        else:
            query_name = self._get_list_query_name(model_name)
            query = f"""
            query List{model_name}s($filter: Model{model_name}FilterInput) {{
              {query_name}(filter: $filter) {{
                items {{
                    id
                }}
              }}
            }}
            """
            filter_input = {primary_field: {"eq": value}}
            result = await self._request_async(session, query, {"filter": filter_input})
            if result and "data" in result:
                items = result["data"].get(query_name, {}).get("items", [])
                if len(items) > 0:
                    logger.error(f'Record with {primary_field}="{value}" already exists in {model_name}')
                    return None

        return record

    async def upload_batch_async(
        self, batch: list, model_name: str, primary_field: str, is_secondary_index: bool
    ) -> tuple[int, int]:
        async with aiohttp.ClientSession() as session:
            duplicate_checks = [
                self.check_record_exists_async(
                    session, model_name, primary_field, record[primary_field], is_secondary_index, record
                )
                for record in batch
            ]
            check_results = await asyncio.gather(*duplicate_checks, return_exceptions=True)

            filtered_batch = []
            for result in check_results:
                if isinstance(result, Exception):
                    logger.error(f"Error checking duplicate: {result}")
                elif result is not None:
                    filtered_batch.append(result)

            if not filtered_batch:
                return 0, len(batch)

            create_tasks = [
                self.create_record_async(session, record, model_name, primary_field) for record in filtered_batch
            ]
            results = await asyncio.gather(*create_tasks, return_exceptions=True)

            success_count = sum(1 for r in results if r and not isinstance(r, Exception))
            error_count = len(batch) - success_count

            return success_count, error_count

    def get_model_structure(self, model_type: str) -> Dict:
        query = f"""
        query GetModelType {{
          __type(name: "{model_type}") {{
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

        response = self._request(query)
        if response and "data" in response and "__type" in response["data"]:
            return response["data"]["__type"]

        return {}

    def get_primary_field_name(self, model_name: str, parsed_model_structure: Dict[str, Any]) -> tuple[str, bool]:
        secondary_index = self._get_secondary_index(model_name)
        if secondary_index:
            return secondary_index, True

        for field in parsed_model_structure["fields"]:
            if field["is_required"] and field["is_scalar"] and field["name"] != "id":
                return field["name"], False

        logger.error("No suitable primary field found (required scalar field other than id)")
        return "", False

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

    def _get_list_query_name(self, model_name: str) -> str | None:
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

            last_word_plural = str(p.plural(last_word.lower()))  # type: ignore[arg-type]
            last_word_plural_cap = last_word_plural[0].upper() + last_word_plural[1:] if last_word_plural else ""

            pascal_plural = f"{prefix}{last_word_plural_cap}"
            candidates.append(f"list{pascal_plural}")

        full_plural = str(p.plural(model_name.lower()))  # type: ignore[arg-type]
        full_plural_cap = full_plural[0].upper() + full_plural[1:] if full_plural else ""
        candidates.append(f"list{full_plural_cap}")

        for query in query_fields:
            query_name = query["name"]
            if query_name in candidates and "By" not in query_name:
                return query_name

        logger.error(f"No list query found for model {model_name}, tried: {candidates}")
        return None

    def upload(self, records: list, model_name: str, parsed_model_structure: Dict[str, Any]) -> tuple[int, int]:
        logger.info("Uploading to Amplify backend...")

        success_count = 0
        error_count = 0

        primary_field, is_secondary_index = self.get_primary_field_name(model_name, parsed_model_structure)
        if not primary_field:
            logger.error(f"Aborting upload for model {model_name}")
            return 0, len(records)

        for i in range(0, len(records), self.batch_size):
            batch = records[i : i + self.batch_size]
            logger.info(f"Uploading batch {i // self.batch_size + 1} ({len(batch)} items)...")

            batch_success, batch_error = asyncio.run(
                self.upload_batch_async(batch, model_name, primary_field, is_secondary_index)
            )
            success_count += batch_success
            error_count += batch_error

            logger.info(
                f"Processed batch {i // self.batch_size + 1} of model {model_name}: {success_count} success, {error_count} errors"
            )

        return success_count, error_count

    def list_records_by_secondary_index(
        self, model_name: str, secondary_index: str, value: str = None, fields: list = None
    ) -> Dict | None:
        if fields is None:
            fields = ["id", secondary_index]

        fields_str = "\n".join(fields)

        if not value:
            query_name = self._get_list_query_name(model_name)
            query = f"""
            query List{model_name}s {{
              {query_name} {{
                items {{
                    {fields_str}
                }}
              }}
            }}
            """
            result = self._request(query)
        else:
            query_name = f"list{model_name}By{secondary_index[0].upper() + secondary_index[1:]}"
            query = f"""
            query {query_name}(${secondary_index}: String!) {{
              {query_name}({secondary_index}: ${secondary_index}) {{
                items {{
                    {fields_str}
                }}
              }}
            }}
            """
            result = self._request(query, {secondary_index: value})

        if result and "data" in result:
            items = result["data"].get(query_name, {}).get("items", [])
            return items if items else None

        return None

    def list_records_by_field(
        self, model_name: str, field_name: str, value: str = None, fields: list = None
    ) -> Dict | None:
        if fields is None:
            fields = ["id", field_name]

        fields_str = "\n".join(fields)

        query_name = self._get_list_query_name(model_name)

        if not value:
            query = f"""
            query List{model_name}s {{
              {query_name} {{
                items {{
                    {fields_str}
                }}
              }}
            }}
            """
            result = self._request(query)
        else:
            query = f"""
            query List{model_name}s($filter: Model{model_name}FilterInput) {{
              {query_name}(filter: $filter) {{
                items {{
                    {fields_str}
                }}
              }}
            }}
            """
            filter_input = {field_name: {"eq": value}}
            result = self._request(query, {"filter": filter_input})

        if result and "data" in result:
            items = result["data"].get(query_name, {}).get("items", [])
            return items if items else None

        return None

    def get_record_by_id(self, model_name: str, record_id: str, fields: list = None) -> Dict | None:
        if fields is None:
            fields = ["id"]

        fields_str = "\n".join(fields)

        query_name = f"get{model_name}"
        query = f"""
        query Get{model_name}($id: ID!) {{
          {query_name}(id: $id) {{
            {fields_str}
          }}
        }}
        """

        result = self._request(query, {"id": record_id})

        if result and "data" in result:
            return result["data"].get(query_name)

        return None

    @timing_decorator
    def get_records(
        self,
        model_name: str,
        primary_field: str = None,
        is_secondary_index: bool = None,
        fields: list = None,
    ) -> list | None:
        if model_name in self.records_cache:
            logger.info(f"💾 Cache hit for {model_name}")
            return self.records_cache[model_name]

        logger.info(f"🌐 Fetching {model_name} records from API")
        if not primary_field:
            return None
        if is_secondary_index:
            records = self.list_records_by_secondary_index(model_name, primary_field, fields=fields)
        else:
            records = self.list_records_by_field(model_name, primary_field, fields=fields)

        if records:
            self.records_cache[model_name] = records
            logger.info(f"💾 Cached {len(records)} records for {model_name}")
        return records

    def get_record(
        self,
        model_name: str,
        parsed_model_structure: Dict[str, Any] = None,
        value: str = None,
        record_id: str = None,
        primary_field: str = None,
        is_secondary_index: bool = None,
        fields: list = None,
    ) -> Dict | None:
        if record_id:
            return self.get_record_by_id(model_name, record_id)

        if not primary_field:
            if not parsed_model_structure:
                logger.error("Parsed model structure required if primary_field not provided")
                return None
            primary_field, is_secondary_index = self.get_primary_field_name(model_name, parsed_model_structure)
        records = self.get_records(model_name, primary_field, is_secondary_index, fields)
        if not records:
            return None
        return next((record for record in records if record.get(primary_field) == value), None)

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
        import pandas as pd

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
                primary_field, is_secondary_index = self.get_primary_field_name(related_model, parsed_model_structure)
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
