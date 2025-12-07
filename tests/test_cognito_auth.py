"""Tests for CognitoAuthProvider class"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pycognito.exceptions import ForceChangePasswordException
from pycognito import MFAChallengeException
from botocore.exceptions import NoCredentialsError, ProfileNotFound, NoRegionError, ClientError

from amplify_excel_migrator.auth import CognitoAuthProvider


@pytest.fixture
def auth_params():
    """Standard authentication parameters"""
    return {
        "user_pool_id": "us-east-1_testpool",
        "client_id": "test-client-id",
        "region": "us-east-1",
        "admin_group_name": "ADMINS",
    }


@pytest.fixture
def cognito_provider(auth_params):
    """Create CognitoAuthProvider instance"""
    return CognitoAuthProvider(**auth_params)


@pytest.fixture
def mock_id_token():
    """Mock ID token with ADMINS group"""
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiY29nbml0bzpncm91cHMiOlsiQURNSU5TIl19.test"


class TestCognitoAuthProviderInitialization:
    """Test CognitoAuthProvider initialization"""

    def test_initialization(self, cognito_provider, auth_params):
        """Test basic initialization"""
        assert cognito_provider.user_pool_id == auth_params["user_pool_id"]
        assert cognito_provider.client_id == auth_params["client_id"]
        assert cognito_provider.region == auth_params["region"]
        assert cognito_provider.admin_group_name == auth_params["admin_group_name"]
        assert cognito_provider.cognito_client is None
        assert cognito_provider.boto_cognito_admin_client is None
        assert cognito_provider._id_token is None
        assert cognito_provider._mfa_tokens is None

    def test_custom_admin_group(self, auth_params):
        """Test initialization with custom admin group"""
        auth_params["admin_group_name"] = "CUSTOM_ADMINS"
        provider = CognitoAuthProvider(**auth_params)
        assert provider.admin_group_name == "CUSTOM_ADMINS"


class TestStandardAuthentication:
    """Test standard Cognito authentication"""

    @patch("amplify_excel_migrator.auth.cognito_auth.Cognito")
    @patch("amplify_excel_migrator.auth.cognito_auth.jwt.decode")
    def test_successful_authentication(self, mock_jwt_decode, mock_cognito_class, cognito_provider, mock_id_token):
        """Test successful authentication"""
        mock_cognito = Mock()
        mock_cognito.id_token = mock_id_token
        mock_cognito_class.return_value = mock_cognito
        mock_jwt_decode.return_value = {"cognito:groups": ["ADMINS"]}

        result = cognito_provider.authenticate("test@example.com", "password123")

        assert result is True
        assert cognito_provider._id_token == mock_id_token
        mock_cognito.authenticate.assert_called_once_with(password="password123")

    @patch("amplify_excel_migrator.auth.cognito_auth.Cognito")
    @patch("amplify_excel_migrator.auth.cognito_auth.jwt.decode")
    def test_authentication_not_in_admin_group(self, mock_jwt_decode, mock_cognito_class, cognito_provider):
        """Test authentication fails when user not in admin group"""
        mock_cognito = Mock()
        mock_cognito.id_token = "test_token"
        mock_cognito_class.return_value = mock_cognito
        mock_jwt_decode.return_value = {"cognito:groups": ["USERS"]}

        result = cognito_provider.authenticate("test@example.com", "password123")
        assert result is False

    @patch("amplify_excel_migrator.auth.cognito_auth.Cognito")
    @patch("amplify_excel_migrator.auth.cognito_auth.input")
    def test_authentication_with_mfa_challenge(self, mock_input, mock_cognito_class, cognito_provider, mock_id_token):
        """Test authentication with MFA challenge"""
        mock_cognito = Mock()
        mock_cognito_class.return_value = mock_cognito

        mfa_tokens = {"ChallengeName": "SMS_MFA", "Session": "test-session"}
        mfa_exception = MFAChallengeException("MFA required", mfa_tokens)

        mock_cognito.authenticate.side_effect = [mfa_exception, None]
        mock_cognito.id_token = mock_id_token
        mock_input.return_value = "123456"

        with patch.object(cognito_provider, "_complete_mfa_challenge", return_value=True):
            with patch.object(cognito_provider, "_check_user_in_admins_group"):
                result = cognito_provider.authenticate("test@example.com", "password123")

        assert result is True

    @patch("amplify_excel_migrator.auth.cognito_auth.Cognito")
    @patch("amplify_excel_migrator.auth.cognito_auth.input")
    def test_authentication_with_password_change(self, mock_input, mock_cognito_class, cognito_provider, mock_id_token):
        """Test authentication with force password change"""
        mock_cognito = Mock()
        mock_cognito_class.return_value = mock_cognito

        mock_cognito.authenticate.side_effect = [ForceChangePasswordException(), None]
        mock_cognito.id_token = mock_id_token
        mock_input.side_effect = ["newpassword123", "newpassword123"]

        with patch.object(cognito_provider, "_check_user_in_admins_group"):
            result = cognito_provider.authenticate("test@example.com", "oldpassword")

        assert result is True
        mock_cognito.new_password_challenge.assert_called_once()

    @patch("amplify_excel_migrator.auth.cognito_auth.Cognito")
    @patch("amplify_excel_migrator.auth.cognito_auth.input")
    def test_authentication_password_mismatch(self, mock_input, mock_cognito_class, cognito_provider):
        """Test authentication fails when new passwords don't match"""
        mock_cognito = Mock()
        mock_cognito_class.return_value = mock_cognito
        mock_cognito.authenticate.side_effect = ForceChangePasswordException()
        mock_input.side_effect = ["newpassword", "differentpassword"]

        result = cognito_provider.authenticate("test@example.com", "oldpassword")

        assert result is False

    @patch("amplify_excel_migrator.auth.cognito_auth.Cognito")
    def test_authentication_general_error(self, mock_cognito_class, cognito_provider):
        """Test authentication handles general errors"""
        mock_cognito = Mock()
        mock_cognito_class.return_value = mock_cognito
        mock_cognito.authenticate.side_effect = Exception("Network error")

        result = cognito_provider.authenticate("test@example.com", "password123")

        assert result is False


class TestAdminAuthentication:
    """Test admin authentication"""

    @patch("amplify_excel_migrator.auth.cognito_auth.boto3.client")
    @patch("amplify_excel_migrator.auth.cognito_auth.jwt.decode")
    def test_successful_admin_authentication(self, mock_jwt_decode, mock_boto_client, cognito_provider, mock_id_token):
        """Test successful admin authentication"""
        mock_cognito_admin = Mock()
        mock_boto_client.return_value = mock_cognito_admin
        mock_jwt_decode.return_value = {"cognito:groups": ["ADMINS"]}

        mock_cognito_admin.admin_initiate_auth.return_value = {
            "AuthenticationResult": {"IdToken": mock_id_token, "AccessToken": "access_token"}
        }

        result = cognito_provider.authenticate_admin("test@example.com", "password123")

        assert result is True
        assert cognito_provider._id_token == mock_id_token
        mock_cognito_admin.admin_initiate_auth.assert_called_once()

    @patch("amplify_excel_migrator.auth.cognito_auth.boto3.Session")
    def test_admin_authentication_with_profile(self, mock_session_class, cognito_provider, mock_id_token):
        """Test admin authentication with AWS profile"""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_cognito_admin = Mock()
        mock_session.client.return_value = mock_cognito_admin

        mock_cognito_admin.admin_initiate_auth.return_value = {"AuthenticationResult": {"IdToken": mock_id_token}}

        with patch("amplify_excel_migrator.auth.cognito_auth.jwt.decode") as mock_jwt:
            mock_jwt.return_value = {"cognito:groups": ["ADMINS"]}
            result = cognito_provider.authenticate_admin("test@example.com", "password", aws_profile="my-profile")

        assert result is True
        mock_session_class.assert_called_once_with(profile_name="my-profile")

    @patch("amplify_excel_migrator.auth.cognito_auth.boto3.client")
    def test_admin_authentication_no_credentials(self, mock_boto_client, cognito_provider):
        """Test admin authentication fails with no AWS credentials"""
        mock_boto_client.side_effect = NoCredentialsError()

        result = cognito_provider.authenticate_admin("test@example.com", "password123")
        assert result is False

    @patch("amplify_excel_migrator.auth.cognito_auth.boto3.Session")
    def test_admin_authentication_profile_not_found(self, mock_session_class, cognito_provider):
        """Test admin authentication fails with invalid profile"""
        mock_session_class.side_effect = ProfileNotFound(profile="invalid")

        result = cognito_provider.authenticate_admin("test@example.com", "password", aws_profile="invalid")
        assert result is False

    @patch("amplify_excel_migrator.auth.cognito_auth.boto3.client")
    def test_admin_authentication_no_region(self, mock_boto_client, cognito_provider):
        """Test admin authentication fails with no region"""
        mock_boto_client.side_effect = NoRegionError()

        result = cognito_provider.authenticate_admin("test@example.com", "password123")
        assert result is False

    @patch("amplify_excel_migrator.auth.cognito_auth.boto3.client")
    def test_admin_authentication_client_error(self, mock_boto_client, cognito_provider):
        """Test admin authentication handles AWS client errors"""
        error_response = {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}
        mock_boto_client.side_effect = ClientError(error_response, "admin_initiate_auth")

        result = cognito_provider.authenticate_admin("test@example.com", "password123")
        assert result is False

    @patch("amplify_excel_migrator.auth.cognito_auth.boto3.client")
    def test_admin_authentication_no_result(self, mock_boto_client, cognito_provider):
        """Test admin authentication fails when no AuthenticationResult"""
        mock_cognito_admin = Mock()
        mock_boto_client.return_value = mock_cognito_admin
        mock_cognito_admin.admin_initiate_auth.return_value = {"ChallengeName": "MFA_SETUP"}

        with patch.object(cognito_provider, "_check_for_mfa_challenges", return_value=False):
            result = cognito_provider.authenticate_admin("test@example.com", "password123")

        assert result is False


class TestMFAChallenge:
    """Test MFA challenge handling"""

    def test_complete_sms_mfa_challenge(self, cognito_provider):
        """Test completing SMS MFA challenge"""
        mock_cognito = Mock()
        cognito_provider.cognito_client = mock_cognito
        cognito_provider._mfa_tokens = {"ChallengeName": "SMS_MFA", "Session": "test-session"}

        result = cognito_provider._complete_mfa_challenge("123456")

        assert result is True
        mock_cognito.respond_to_sms_mfa_challenge.assert_called_once_with(
            code="123456", mfa_tokens=cognito_provider._mfa_tokens
        )

    def test_complete_software_token_mfa_challenge(self, cognito_provider):
        """Test completing Software Token MFA challenge"""
        mock_cognito = Mock()
        cognito_provider.cognito_client = mock_cognito
        cognito_provider._mfa_tokens = {"ChallengeName": "SOFTWARE_TOKEN_MFA", "Session": "test-session"}

        result = cognito_provider._complete_mfa_challenge("123456")

        assert result is True
        mock_cognito.respond_to_software_token_mfa_challenge.assert_called_once_with(
            code="123456", mfa_tokens=cognito_provider._mfa_tokens
        )

    def test_complete_mfa_no_tokens(self, cognito_provider):
        """Test MFA challenge fails when no tokens"""
        result = cognito_provider._complete_mfa_challenge("123456")

        assert result is False

    def test_complete_mfa_challenge_error(self, cognito_provider):
        """Test MFA challenge handles errors"""
        mock_cognito = Mock()
        cognito_provider.cognito_client = mock_cognito
        cognito_provider._mfa_tokens = {"ChallengeName": "SMS_MFA"}
        mock_cognito.respond_to_sms_mfa_challenge.side_effect = Exception("Invalid code")

        result = cognito_provider._complete_mfa_challenge("999999")

        assert result is False


class TestCheckForMFAChallenges:
    """Test _check_for_mfa_challenges method"""

    @patch("amplify_excel_migrator.auth.cognito_auth.input")
    def test_sms_mfa_challenge(self, mock_input, cognito_provider):
        """Test handling SMS MFA challenge"""
        mock_admin_client = Mock()
        cognito_provider.boto_cognito_admin_client = mock_admin_client
        mock_input.return_value = "123456"

        response = {"ChallengeName": "SMS_MFA", "Session": "test-session"}

        cognito_provider._check_for_mfa_challenges(response, "test@example.com")

        mock_admin_client.admin_respond_to_auth_challenge.assert_called_once()

    @patch("amplify_excel_migrator.auth.cognito_auth.getpass")
    def test_new_password_required_challenge(self, mock_getpass, cognito_provider):
        """Test handling NEW_PASSWORD_REQUIRED challenge"""
        mock_admin_client = Mock()
        cognito_provider.boto_cognito_admin_client = mock_admin_client
        mock_getpass.return_value = "newpassword123"

        response = {"ChallengeName": "NEW_PASSWORD_REQUIRED", "Session": "test-session"}

        cognito_provider._check_for_mfa_challenges(response, "test@example.com")

        mock_admin_client.admin_respond_to_auth_challenge.assert_called_once()

    def test_mfa_setup_challenge(self, cognito_provider):
        """Test handling MFA_SETUP challenge"""
        response = {"ChallengeName": "MFA_SETUP"}

        result = cognito_provider._check_for_mfa_challenges(response, "test@example.com")

        assert result is False


class TestCheckUserInAdminsGroup:
    """Test _check_user_in_admins_group method"""

    @patch("amplify_excel_migrator.auth.cognito_auth.jwt.decode")
    def test_user_in_admin_group(self, mock_jwt_decode, cognito_provider):
        """Test user is in admin group"""
        mock_jwt_decode.return_value = {"cognito:groups": ["ADMINS", "USERS"]}

        cognito_provider._check_user_in_admins_group("test_token")

    @patch("amplify_excel_migrator.auth.cognito_auth.jwt.decode")
    def test_user_not_in_admin_group(self, mock_jwt_decode, cognito_provider):
        """Test user is not in admin group"""
        mock_jwt_decode.return_value = {"cognito:groups": ["USERS"]}

        with pytest.raises(PermissionError, match="User is not in ADMINS group"):
            cognito_provider._check_user_in_admins_group("test_token")

    @patch("amplify_excel_migrator.auth.cognito_auth.jwt.decode")
    def test_user_no_groups(self, mock_jwt_decode, cognito_provider):
        """Test user has no groups"""
        mock_jwt_decode.return_value = {}

        with pytest.raises(PermissionError, match="User is not in ADMINS group"):
            cognito_provider._check_user_in_admins_group("test_token")


class TestProviderInterface:
    """Test AuthenticationProvider interface implementation"""

    def test_get_id_token_not_authenticated(self, cognito_provider):
        """Test get_id_token returns None when not authenticated"""
        assert cognito_provider.get_id_token() is None

    def test_get_id_token_authenticated(self, cognito_provider, mock_id_token):
        """Test get_id_token returns token when authenticated"""
        cognito_provider._id_token = mock_id_token
        assert cognito_provider.get_id_token() == mock_id_token

    def test_is_authenticated_false(self, cognito_provider):
        """Test is_authenticated returns False when not authenticated"""
        assert cognito_provider.is_authenticated() is False

    def test_is_authenticated_true(self, cognito_provider, mock_id_token):
        """Test is_authenticated returns True when authenticated"""
        cognito_provider._id_token = mock_id_token
        assert cognito_provider.is_authenticated() is True
