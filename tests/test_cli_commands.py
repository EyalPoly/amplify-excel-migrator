"""Tests for CLI commands"""

import json
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from amplify_excel_migrator.cli.commands import (
    cmd_show,
    cmd_config,
    cmd_migrate,
)
from amplify_excel_migrator.core import ConfigManager


@pytest.fixture
def sample_config():
    """Sample configuration for testing"""
    return {
        "excel_path": "test_data.xlsx",
        "api_endpoint": "https://test.appsync-api.us-east-1.amazonaws.com/graphql",
        "region": "us-east-1",
        "user_pool_id": "us-east-1_testpool",
        "client_id": "test-client-id",
        "username": "test@example.com",
    }


@pytest.fixture
def mock_config_manager(tmp_path):
    """Create a mock ConfigManager for testing"""
    test_config_file = tmp_path / "config.json"

    def init_mock(self, config_path=None):
        self.config_path = test_config_file
        self._config = {}

    return init_mock


class TestCmdShow:
    """Test 'show' command"""

    def test_show_with_no_config(self, capsys, mock_config_manager):
        """Test show command with no config file"""
        with patch.object(ConfigManager, "__init__", mock_config_manager):
            cmd_show()

        captured = capsys.readouterr()
        assert "❌ No configuration found!" in captured.out
        assert "amplify-migrator config" in captured.out

    def test_show_with_existing_config(self, capsys, tmp_path, sample_config):
        """Test show command with existing config"""
        test_config_file = tmp_path / "config.json"
        test_config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(test_config_file, "w") as f:
            json.dump(sample_config, f)

        def init_mock(self, config_path=None):
            self.config_path = test_config_file
            self._config = {}

        with patch.object(ConfigManager, "__init__", init_mock):
            cmd_show()

        captured = capsys.readouterr()
        assert "test_data.xlsx" in captured.out
        assert "test@example.com" in captured.out
        assert "us-east-1" in captured.out
        assert "test-client-id" in captured.out

    def test_show_displays_config_location(self, capsys, tmp_path, sample_config):
        """Test that show command displays config file location"""
        test_config_file = tmp_path / "config.json"
        test_config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(test_config_file, "w") as f:
            json.dump(sample_config, f)

        def init_mock(self, config_path=None):
            self.config_path = test_config_file
            self._config = {}

        with patch.object(ConfigManager, "__init__", init_mock):
            cmd_show()

        captured = capsys.readouterr()
        assert str(test_config_file) in captured.out


class TestCmdConfig:
    """Test 'config' command"""

    def test_config_prompts_for_all_values(self, tmp_path):
        """Test that config command prompts for all required values"""
        test_config_file = tmp_path / "config.json"

        def init_mock(self, config_path=None):
            self.config_path = test_config_file
            self._config = {}

        # Mock all input prompts
        inputs = [
            "test.xlsx",
            "https://test.appsync-api.us-east-1.amazonaws.com/graphql",
            "us-east-1",
            "us-east-1_test",
            "test-client",
            "admin@test.com",
        ]

        with patch.object(ConfigManager, "__init__", init_mock):
            with patch("builtins.input", side_effect=inputs):
                cmd_config()

        # Verify config was saved
        assert test_config_file.exists()
        with open(test_config_file) as f:
            saved_config = json.load(f)
            assert saved_config["excel_path"] == "test.xlsx"
            assert saved_config["username"] == "admin@test.com"

    def test_config_saves_to_correct_location(self, capsys, tmp_path):
        """Test that config is saved to the correct location"""
        test_config_file = tmp_path / "config.json"

        def init_mock(self, config_path=None):
            self.config_path = test_config_file
            self._config = {}

        inputs = ["test.xlsx", "https://test.com", "us-east-1", "pool", "client", "user"]

        with patch.object(ConfigManager, "__init__", init_mock):
            with patch("builtins.input", side_effect=inputs):
                cmd_config()

        captured = capsys.readouterr()
        assert "✅ Configuration saved successfully!" in captured.out
        assert "amplify-migrator migrate" in captured.out

    def test_config_uses_cached_values_as_defaults(self, tmp_path, sample_config):
        """Test that config command shows cached values as defaults"""
        test_config_file = tmp_path / "config.json"
        test_config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(test_config_file, "w") as f:
            json.dump(sample_config, f)

        def init_mock(self, config_path=None):
            self.config_path = test_config_file
            self._config = {}

        # Press enter to accept all defaults (from cached config)
        inputs = ["", "", "", "", "", ""]  # Empty strings use cached values

        with patch.object(ConfigManager, "__init__", init_mock):
            with patch("builtins.input", side_effect=inputs):
                cmd_config()

        with open(test_config_file) as f:
            saved_config = json.load(f)
            assert saved_config["excel_path"] == "test_data.xlsx"
            assert saved_config["region"] == "us-east-1"


class TestCmdMigrate:
    """Test 'migrate' command"""

    def test_migrate_fails_without_config(self, capsys, tmp_path):
        """Test that migrate command fails when no config exists"""
        test_config_file = tmp_path / "config.json"

        def init_mock(self, config_path=None):
            self.config_path = test_config_file
            self._config = {}

        with patch.object(ConfigManager, "__init__", init_mock):
            with pytest.raises(SystemExit) as exc_info:
                cmd_migrate()

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "❌ No configuration found!" in captured.out
        assert "amplify-migrator config" in captured.out

    def test_migrate_uses_cached_config(self, tmp_path, sample_config):
        """Test that migrate command uses cached configuration"""
        test_config_file = tmp_path / "config.json"
        test_config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(test_config_file, "w") as f:
            json.dump(sample_config, f)

        def init_mock(self, config_path=None):
            self.config_path = test_config_file
            self._config = {}

        # Mock the entire migration process
        with patch.object(ConfigManager, "__init__", init_mock):
            with patch("amplify_excel_migrator.auth.CognitoAuthProvider") as mock_auth_provider_class:
                with patch("amplify_excel_migrator.cli.commands.ExcelReader") as mock_excel_reader_class:
                    with patch("amplify_excel_migrator.cli.commands.MigrationOrchestrator") as mock_orchestrator_class:
                        with patch("amplify_excel_migrator.core.config.getpass", return_value="password123"):
                            mock_auth_instance = MagicMock()
                            mock_auth_instance.authenticate.return_value = True
                            mock_auth_provider_class.return_value = mock_auth_instance

                            mock_excel_reader_instance = MagicMock()
                            mock_excel_reader_class.return_value = mock_excel_reader_instance

                            mock_orchestrator_instance = MagicMock()
                            mock_orchestrator_class.return_value = mock_orchestrator_instance

                            cmd_migrate()

                            # Verify auth provider was initialized with cached values
                            mock_auth_provider_class.assert_called_once()
                            call_args = mock_auth_provider_class.call_args
                            assert call_args[1]["user_pool_id"] == "us-east-1_testpool"
                            assert call_args[1]["client_id"] == "test-client-id"
                            assert call_args[1]["region"] == "us-east-1"

                            # Verify authenticate was called
                            mock_auth_instance.authenticate.assert_called_once_with("test@example.com", "password123")

                            # Verify orchestrator was called
                            mock_orchestrator_instance.run.assert_called_once()

    def test_migrate_prompts_for_password(self, tmp_path, sample_config):
        """Test that migrate command always prompts for password"""
        test_config_file = tmp_path / "config.json"
        test_config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(test_config_file, "w") as f:
            json.dump(sample_config, f)

        def init_mock(self, config_path=None):
            self.config_path = test_config_file
            self._config = {}

        with patch.object(ConfigManager, "__init__", init_mock):
            with patch("amplify_excel_migrator.auth.CognitoAuthProvider") as mock_auth_provider_class:
                with patch("amplify_excel_migrator.cli.commands.ExcelReader") as mock_excel_reader_class:
                    with patch("amplify_excel_migrator.cli.commands.MigrationOrchestrator") as mock_orchestrator_class:
                        with patch(
                            "amplify_excel_migrator.core.config.getpass", return_value="secret_password"
                        ) as mock_getpass:
                            mock_auth_instance = MagicMock()
                            mock_auth_instance.authenticate.return_value = True
                            mock_auth_provider_class.return_value = mock_auth_instance

                            mock_excel_reader_instance = MagicMock()
                            mock_excel_reader_class.return_value = mock_excel_reader_instance

                            mock_orchestrator_instance = MagicMock()
                            mock_orchestrator_class.return_value = mock_orchestrator_instance

                            cmd_migrate()

                            # Verify getpass was called (for password prompt)
                            mock_getpass.assert_called()

    def test_migrate_stops_if_authentication_fails(self, tmp_path, sample_config):
        """Test that migrate stops if authentication fails"""
        test_config_file = tmp_path / "config.json"
        test_config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(test_config_file, "w") as f:
            json.dump(sample_config, f)

        def init_mock(self, config_path=None):
            self.config_path = test_config_file
            self._config = {}

        with patch.object(ConfigManager, "__init__", init_mock):
            with patch("amplify_excel_migrator.auth.CognitoAuthProvider") as mock_auth_provider_class:
                with patch("amplify_excel_migrator.cli.commands.MigrationOrchestrator") as mock_orchestrator_class:
                    with patch("amplify_excel_migrator.core.config.getpass", return_value="wrong_password"):
                        mock_auth_instance = MagicMock()
                        mock_auth_instance.authenticate.return_value = False  # Authentication fails
                        mock_auth_provider_class.return_value = mock_auth_instance

                        mock_orchestrator_instance = MagicMock()
                        mock_orchestrator_class.return_value = mock_orchestrator_instance

                        cmd_migrate()

                        # Verify run() was NOT called
                        mock_orchestrator_instance.run.assert_not_called()
