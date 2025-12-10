"""Amplify Excel Migrator - Migrate Excel data to AWS Amplify GraphQL API."""

__version__ = "1.2.5"

from amplify_excel_migrator.client import AmplifyClient
from amplify_excel_migrator.migration import MigrationOrchestrator
from amplify_excel_migrator.auth import AuthenticationProvider, CognitoAuthProvider
from amplify_excel_migrator.core import ConfigManager

__all__ = [
    "AmplifyClient",
    "MigrationOrchestrator",
    "AuthenticationProvider",
    "CognitoAuthProvider",
    "ConfigManager",
    "__version__",
]
