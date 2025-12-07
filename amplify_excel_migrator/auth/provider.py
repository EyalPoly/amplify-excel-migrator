"""Abstract authentication provider interface."""

from abc import ABC, abstractmethod
from typing import Optional


class AuthenticationProvider(ABC):
    """Abstract base class for authentication providers."""

    @abstractmethod
    def authenticate(self, username: str, password: str) -> bool:
        """
        Authenticate a user with username and password.

        Args:
            username: User's username or email
            password: User's password

        Returns:
            True if authentication successful, False otherwise
        """
        pass

    @abstractmethod
    def get_id_token(self) -> Optional[str]:
        """
        Get the ID token from the last successful authentication.

        Returns:
            ID token string if authenticated, None otherwise
        """
        pass

    @abstractmethod
    def is_authenticated(self) -> bool:
        """
        Check if the provider is currently authenticated.

        Returns:
            True if authenticated, False otherwise
        """
        pass
