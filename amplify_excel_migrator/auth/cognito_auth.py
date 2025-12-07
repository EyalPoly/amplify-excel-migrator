"""AWS Cognito authentication provider implementation."""

import logging
from typing import Optional
from getpass import getpass

import boto3
import jwt
from botocore.exceptions import NoCredentialsError, ProfileNotFound, NoRegionError, ClientError
from pycognito import Cognito, MFAChallengeException
from pycognito.exceptions import ForceChangePasswordException

from .provider import AuthenticationProvider

logger = logging.getLogger(__name__)


class CognitoAuthProvider(AuthenticationProvider):
    """AWS Cognito authentication provider."""

    def __init__(
        self,
        user_pool_id: str,
        client_id: str,
        region: str,
        admin_group_name: str = "ADMINS",
    ):
        """
        Initialize the Cognito authentication provider.

        Args:
            user_pool_id: Cognito User Pool ID
            client_id: Cognito App Client ID
            region: AWS region
            admin_group_name: Name of the admin group to check membership
        """
        self.user_pool_id = user_pool_id
        self.client_id = client_id
        self.region = region
        self.admin_group_name = admin_group_name

        self.cognito_client: Optional[Cognito] = None
        self.boto_cognito_admin_client: Optional[any] = None
        self._id_token: Optional[str] = None
        self._mfa_tokens: Optional[dict] = None

    def authenticate(self, username: str, password: str, mfa_code: Optional[str] = None) -> bool:
        """
        Authenticate using standard Cognito user authentication.

        Args:
            username: User's username or email
            password: User's password
            mfa_code: Optional MFA code if MFA is enabled

        Returns:
            True if authentication successful, False otherwise
        """
        try:
            if not self.cognito_client:
                self._init_cognito_client(username)

            if mfa_code and self._mfa_tokens:
                if not self._complete_mfa_challenge(mfa_code):
                    return False
            else:
                self.cognito_client.authenticate(password=password)

            self._id_token = self.cognito_client.id_token

            self._check_user_in_admins_group(self._id_token)

            logger.info("✅ Authentication successful")
            return True

        except MFAChallengeException as e:
            logger.warning("MFA required")
            if hasattr(e, "get_tokens"):
                self._mfa_tokens = e.get_tokens()

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

    def authenticate_admin(self, username: str, password: str, aws_profile: Optional[str] = None) -> bool:
        """
        Authenticate using AWS admin credentials (ADMIN_USER_PASSWORD_AUTH flow).

        Requires AWS credentials with cognito-idp:ListUserPoolClients permission.

        Args:
            username: User's username or email
            password: User's password
            aws_profile: Optional AWS profile name

        Returns:
            True if authentication successful, False otherwise
        """
        try:
            if not self.boto_cognito_admin_client:
                self._init_boto_admin_client(aws_profile)

            logger.info(f"Authenticating {username} using ADMIN_USER_PASSWORD_AUTH flow...")

            response = self.boto_cognito_admin_client.admin_initiate_auth(
                UserPoolId=self.user_pool_id,
                ClientId=self.client_id,
                AuthFlow="ADMIN_USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": username, "PASSWORD": password},
            )

            self._check_for_mfa_challenges(response, username)

            if "AuthenticationResult" in response:
                self._id_token = response["AuthenticationResult"]["IdToken"]
            else:
                logger.error("❌ Authentication failed: No AuthenticationResult in response")
                return False

            self._check_user_in_admins_group(self._id_token)

            logger.info("✅ Authentication successful")
            return True

        except Exception as e:
            if hasattr(e, "response"):
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                if error_code == "NotAuthorizedException":
                    logger.error(f"❌ Authentication failed: {e}")
                elif error_code == "UserNotFoundException":
                    logger.error(f"❌ User not found: {username}")
                else:
                    logger.error(f"❌ Error during authentication: {e}")
            else:
                logger.error(f"❌ Error during authentication: {e}")
            return False

    def get_id_token(self) -> Optional[str]:
        """
        Get the ID token from the last successful authentication.

        Returns:
            ID token string if authenticated, None otherwise
        """
        return self._id_token

    def is_authenticated(self) -> bool:
        """
        Check if the provider is currently authenticated.

        Returns:
            True if authenticated, False otherwise
        """
        return self._id_token is not None

    def _init_cognito_client(self, username: str) -> None:
        """Initialize the standard Cognito client."""
        try:
            self.cognito_client = Cognito(
                user_pool_id=self.user_pool_id,
                client_id=self.client_id,
                user_pool_region=self.region,
                username=username,
            )
        except ValueError as e:
            logger.error(f"Invalid parameter: {e}")
            raise

    def _init_boto_admin_client(self, aws_profile: Optional[str] = None) -> None:
        """Initialize the boto3 Cognito admin client."""
        try:
            if aws_profile:
                session = boto3.Session(profile_name=aws_profile)
                self.boto_cognito_admin_client = session.client("cognito-idp", region_name=self.region)
            else:
                # Use default AWS credentials (from ~/.aws/credentials, env vars, or IAM role)
                self.boto_cognito_admin_client = boto3.client("cognito-idp", region_name=self.region)

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
                "Failed to initialize client: No AWS region specified. "
                "Provide region parameter or set AWS_DEFAULT_REGION environment variable."
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"AWS Client Error [{error_code}]: {error_msg}")
            raise RuntimeError(f"Failed to initialize client: AWS error [{error_code}]: {error_msg}")

        except Exception as e:
            logger.error(f"Error during client initialization: {e}")
            raise RuntimeError(f"Failed to initialize client: {e}")

    def _complete_mfa_challenge(self, mfa_code: str) -> bool:
        """Complete MFA challenge."""
        try:
            if not self._mfa_tokens:
                logger.error("No MFA session tokens available")
                return False

            challenge_name = self._mfa_tokens.get("ChallengeName", "SMS_MFA")

            if "SOFTWARE_TOKEN" in challenge_name:
                self.cognito_client.respond_to_software_token_mfa_challenge(code=mfa_code, mfa_tokens=self._mfa_tokens)
            else:
                self.cognito_client.respond_to_sms_mfa_challenge(code=mfa_code, mfa_tokens=self._mfa_tokens)

            logger.info("✅ MFA challenge successful")
            return True

        except Exception as e:
            logger.error(f"MFA challenge failed: {e}")
            return False

    def _check_for_mfa_challenges(self, response: dict, username: str) -> bool:
        """Check and handle MFA challenges in admin auth response."""
        if "ChallengeName" in response:
            challenge = response["ChallengeName"]

            if challenge == "MFA_SETUP":
                logger.error("MFA setup required")
                return False

            elif challenge == "SMS_MFA" or challenge == "SOFTWARE_TOKEN_MFA":
                mfa_code = input("Enter MFA code: ")
                _ = self.boto_cognito_admin_client.admin_respond_to_auth_challenge(
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
                _ = self.boto_cognito_admin_client.admin_respond_to_auth_challenge(
                    UserPoolId=self.user_pool_id,
                    ClientId=self.client_id,
                    ChallengeName=challenge,
                    Session=response["Session"],
                    ChallengeResponses={"USERNAME": username, "NEW_PASSWORD": new_password},
                )

        return False

    def _check_user_in_admins_group(self, id_token: str) -> None:
        """
        Check if user belongs to the admin group.

        Args:
            id_token: JWT ID token

        Raises:
            PermissionError: If user is not in admin group
        """
        claims = jwt.decode(id_token, options={"verify_signature": False})
        groups = claims.get("cognito:groups", [])

        if self.admin_group_name not in groups:
            raise PermissionError(f"User is not in {self.admin_group_name} group")
