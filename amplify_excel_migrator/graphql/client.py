"""GraphQL HTTP client for making requests to GraphQL APIs."""

import logging
import sys
from typing import Dict, Any, Optional

import aiohttp
import requests

from amplify_excel_migrator.auth import AuthenticationProvider

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when authentication is required but not completed"""

    pass


class GraphQLError(Exception):
    """Raised when GraphQL query returns errors"""

    pass


class GraphQLClient:
    def __init__(self, api_endpoint: str, auth_provider: Optional[AuthenticationProvider] = None):
        self.api_endpoint = api_endpoint
        self.auth_provider = auth_provider

    def request(
        self, query: str, variables: Optional[Dict[str, Any]] = None, context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if not self.auth_provider or not self.auth_provider.is_authenticated():
            raise AuthenticationError("Not authenticated. Call authenticate() on the auth provider first.")

        id_token = self.auth_provider.get_id_token()
        headers = {"Authorization": id_token, "Content-Type": "application/json"}

        payload = {"query": query, "variables": variables or {}}

        context_msg = f" [{context}]" if context else ""

        try:
            response = requests.post(self.api_endpoint, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()

                if "errors" in result:
                    raise GraphQLError(f"GraphQL errors{context_msg}: {result['errors']}")

                return result
            else:
                logger.error(f"HTTP Error {response.status_code}{context_msg}: {response.text}")
                return None

        except requests.exceptions.ConnectionError:
            logger.error(
                f"Connection error{context_msg}: Unable to connect to API endpoint. Check your internet connection or the API endpoint URL."
            )
            sys.exit(1)

        except requests.exceptions.Timeout as e:
            logger.error(f"Request timeout{context_msg}: {e}")
            return None

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error{context_msg}: {e}")
            return None

        except GraphQLError as e:
            logger.error(str(e))
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Request error{context_msg}: {e}")
            return None

    async def request_async(
        self,
        session: aiohttp.ClientSession,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        context: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.auth_provider or not self.auth_provider.is_authenticated():
            raise AuthenticationError("Not authenticated. Call authenticate() on the auth provider first.")

        id_token = self.auth_provider.get_id_token()
        headers = {"Authorization": id_token, "Content-Type": "application/json"}

        payload = {"query": query, "variables": variables or {}}

        context_msg = f" [{context}]" if context else ""

        try:
            async with session.post(self.api_endpoint, headers=headers, json=payload) as response:
                if response.status == 200:
                    result = await response.json()

                    if "errors" in result:
                        raise GraphQLError(f"GraphQL errors{context_msg}: {result['errors']}")

                    return result
                else:
                    text = await response.text()
                    error_msg = f"HTTP Error {response.status}{context_msg}: {text}"
                    logger.error(error_msg)
                    raise aiohttp.ClientError(error_msg)

        except aiohttp.ServerTimeoutError as e:
            error_msg = f"Request timeout{context_msg}: {e}"
            logger.error(error_msg)
            raise aiohttp.ServerTimeoutError(error_msg)

        except aiohttp.ClientConnectionError as e:
            error_msg = f"Connection error{context_msg}: Unable to connect to API endpoint. {e}"
            logger.error(error_msg)
            raise aiohttp.ClientConnectionError(error_msg)

        except aiohttp.ClientResponseError as e:
            error_msg = f"HTTP response error{context_msg}: {e}"
            logger.error(error_msg)
            raise aiohttp.ClientResponseError(
                request_info=e.request_info, history=e.history, status=e.status, message=error_msg
            )

        except GraphQLError as e:
            logger.error(str(e))
            raise

        except aiohttp.ClientError as e:
            error_msg = f"Client error{context_msg}: {e}"
            logger.error(error_msg)
            raise aiohttp.ClientError(error_msg)
