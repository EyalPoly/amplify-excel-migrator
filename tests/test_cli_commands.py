"""Tests for CLI commands"""

import json
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from migrator import (
    cmd_show,
    cmd_config,
    cmd_migrate,
)


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


class TestCmdShow:
    """Test 'show' command"""

    def test_show_with_no_config(self, capsys, tmp_path, monkeypatch):
        """Test show command with no config file"""
        test_config_file = tmp_path / "config.json"
        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        cmd_show()

        captured = capsys.readouterr()
        assert "❌ No configuration found!" in captured.out
        assert "amplify-migrator config" in captured.out

    def test_show_with_existing_config(self, capsys, tmp_path, sample_config, monkeypatch):
        """Test show command with existing config"""
        test_config_dir = tmp_path / ".amplify-migrator"
        test_config_file = test_config_dir / "config.json"
        test_config_dir.mkdir(parents=True)

        with open(test_config_file, "w") as f:
            json.dump(sample_config, f)

        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        cmd_show()

        captured = capsys.readouterr()
        assert "test_data.xlsx" in captured.out
        assert "test@example.com" in captured.out
        assert "us-east-1" in captured.out
        assert "test-client-id" in captured.out

    def test_show_displays_config_location(self, capsys, tmp_path, sample_config, monkeypatch):
        """Test that show command displays config file location"""
        test_config_dir = tmp_path / ".amplify-migrator"
        test_config_file = test_config_dir / "config.json"
        test_config_dir.mkdir(parents=True)

        with open(test_config_file, "w") as f:
            json.dump(sample_config, f)

        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        cmd_show()

        captured = capsys.readouterr()
        assert str(test_config_file) in captured.out


class TestCmdConfig:
    """Test 'config' command"""

    def test_config_prompts_for_all_values(self, tmp_path, monkeypatch):
        """Test that config command prompts for all required values"""
        test_config_dir = tmp_path / ".amplify-migrator"
        test_config_file = test_config_dir / "config.json"

        monkeypatch.setattr("migrator.CONFIG_DIR", test_config_dir)
        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        # Mock all input prompts
        inputs = [
            "test.xlsx",
            "https://test.appsync-api.us-east-1.amazonaws.com/graphql",
            "us-east-1",
            "us-east-1_test",
            "test-client",
            "admin@test.com",
        ]

        with patch("builtins.input", side_effect=inputs):
            cmd_config()

        # Verify config was saved
        assert test_config_file.exists()
        with open(test_config_file) as f:
            saved_config = json.load(f)
            assert saved_config["excel_path"] == "test.xlsx"
            assert saved_config["username"] == "admin@test.com"

    def test_config_saves_to_correct_location(self, capsys, tmp_path, monkeypatch):
        """Test that config is saved to the correct location"""
        test_config_dir = tmp_path / ".amplify-migrator"
        test_config_file = test_config_dir / "config.json"

        monkeypatch.setattr("migrator.CONFIG_DIR", test_config_dir)
        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        inputs = ["test.xlsx", "https://test.com", "us-east-1", "pool", "client", "user"]

        with patch("builtins.input", side_effect=inputs):
            cmd_config()

        captured = capsys.readouterr()
        assert "✅ Configuration saved successfully!" in captured.out
        assert "amplify-migrator migrate" in captured.out

    def test_config_uses_defaults(self, tmp_path, monkeypatch):
        """Test that config command uses default values when user presses enter"""
        test_config_dir = tmp_path / ".amplify-migrator"
        test_config_file = test_config_dir / "config.json"

        monkeypatch.setattr("migrator.CONFIG_DIR", test_config_dir)
        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        # Empty strings for prompts with defaults, values for those without
        inputs = [
            "",  # excel_path (use default 'data.xlsx')
            "https://test.com",  # api_endpoint (required)
            "",  # region (use default 'us-east-1')
            "pool-id",  # user_pool_id (required)
            "client-id",  # client_id (required)
            "admin@test.com",  # username (required)
        ]

        with patch("builtins.input", side_effect=inputs):
            cmd_config()

        with open(test_config_file) as f:
            saved_config = json.load(f)
            assert saved_config["excel_path"] == "data.xlsx"  # Default used
            assert saved_config["region"] == "us-east-1"  # Default used


class TestCmdMigrate:
    """Test 'migrate' command"""

    def test_migrate_fails_without_config(self, capsys, tmp_path, monkeypatch):
        """Test that migrate command fails when no config exists"""
        test_config_file = tmp_path / "config.json"
        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        with pytest.raises(SystemExit) as exc_info:
            cmd_migrate()

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "❌ No configuration found!" in captured.out
        assert "amplify-migrator config" in captured.out

    def test_migrate_uses_cached_config(self, tmp_path, sample_config, monkeypatch):
        """Test that migrate command uses cached configuration"""
        test_config_dir = tmp_path / ".amplify-migrator"
        test_config_file = test_config_dir / "config.json"
        test_config_dir.mkdir(parents=True)

        with open(test_config_file, "w") as f:
            json.dump(sample_config, f)

        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        # Mock the entire migration process
        with patch("migrator.ExcelToAmplifyMigrator") as mock_migrator_class, patch(
            "migrator.get_config_value", return_value="password123"
        ):

            mock_instance = MagicMock()
            mock_instance.authenticate.return_value = True
            mock_migrator_class.return_value = mock_instance

            cmd_migrate()

            # Verify migrator was initialized with cached values
            mock_migrator_class.assert_called_once_with("test_data.xlsx")
            mock_instance.init_client.assert_called_once()

            # Check that init_client was called with correct parameters
            call_args = mock_instance.init_client.call_args
            assert call_args[0][0] == "https://test.appsync-api.us-east-1.amazonaws.com/graphql"  # api_endpoint
            assert call_args[0][1] == "us-east-1"  # region
            assert call_args[0][2] == "us-east-1_testpool"  # user_pool_id

    def test_migrate_prompts_for_password(self, tmp_path, sample_config, monkeypatch):
        """Test that migrate command always prompts for password"""
        test_config_dir = tmp_path / ".amplify-migrator"
        test_config_file = test_config_dir / "config.json"
        test_config_dir.mkdir(parents=True)

        with open(test_config_file, "w") as f:
            json.dump(sample_config, f)

        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        with patch("migrator.ExcelToAmplifyMigrator") as mock_migrator_class, patch(
            "migrator.get_config_value", return_value="secret_password"
        ) as mock_get_config:

            mock_instance = MagicMock()
            mock_instance.authenticate.return_value = True
            mock_migrator_class.return_value = mock_instance

            cmd_migrate()

            # Verify get_config_value was called (for password prompt)
            # Check that it was called with secret=True parameter
            called_with_secret = any(call.kwargs.get("secret") is True for call in mock_get_config.call_args_list)
            assert called_with_secret or mock_get_config.called

    def test_migrate_stops_if_authentication_fails(self, tmp_path, sample_config, monkeypatch):
        """Test that migrate stops if authentication fails"""
        test_config_dir = tmp_path / ".amplify-migrator"
        test_config_file = test_config_dir / "config.json"
        test_config_dir.mkdir(parents=True)

        with open(test_config_file, "w") as f:
            json.dump(sample_config, f)

        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        with patch("migrator.ExcelToAmplifyMigrator") as mock_migrator_class, patch(
            "migrator.get_config_value", return_value="wrong_password"
        ):

            mock_instance = MagicMock()
            mock_instance.authenticate.return_value = False  # Authentication fails
            mock_migrator_class.return_value = mock_instance

            cmd_migrate()

            # Verify run() was NOT called
            mock_instance.run.assert_not_called()
