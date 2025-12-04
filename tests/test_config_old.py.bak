"""Tests for configuration management"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch
from migrator import (
    get_config_value,
    save_config,
    load_cached_config,
    get_cached_or_prompt,
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


class TestGetConfigValue:
    """Test get_config_value function"""

    def test_with_default_empty_input(self):
        """Test getting config value with default when user provides empty input"""
        with patch("builtins.input", return_value=""):
            result = get_config_value("Test prompt", "default_value")
            assert result == "default_value"

    def test_with_user_input(self):
        """Test getting config value from user input"""
        with patch("builtins.input", return_value="user_value"):
            result = get_config_value("Test prompt", "default_value")
            assert result == "user_value"

    def test_without_default(self):
        """Test getting config value without default"""
        with patch("builtins.input", return_value="custom_value"):
            result = get_config_value("Test prompt")
            assert result == "custom_value"

    def test_secret_input(self):
        """Test getting secret input (password)"""
        with patch("migrator.getpass", return_value="secret123"):
            result = get_config_value("Password", secret=True)
            assert result == "secret123"

    def test_strips_whitespace(self):
        """Test that input is stripped of whitespace"""
        with patch("builtins.input", return_value="  value with spaces  "):
            result = get_config_value("Test prompt")
            assert result == "value with spaces"


class TestSaveConfig:
    """Test save_config function"""

    def test_saves_config_to_file(self, tmp_path, sample_config, monkeypatch):
        """Test saving configuration to file"""
        test_config_dir = tmp_path / ".amplify-migrator"
        test_config_file = test_config_dir / "config.json"

        monkeypatch.setattr("migrator.CONFIG_DIR", test_config_dir)
        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        save_config(sample_config)

        assert test_config_file.exists()
        with open(test_config_file) as f:
            loaded = json.load(f)
            assert loaded == sample_config

    def test_creates_directory_if_not_exists(self, tmp_path, sample_config, monkeypatch):
        """Test that save_config creates directory if it doesn't exist"""
        test_config_dir = tmp_path / ".amplify-migrator"
        test_config_file = test_config_dir / "config.json"

        monkeypatch.setattr("migrator.CONFIG_DIR", test_config_dir)
        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        assert not test_config_dir.exists()
        save_config(sample_config)
        assert test_config_dir.exists()

    def test_excludes_password_fields(self, tmp_path, monkeypatch):
        """Test that password fields are not saved"""
        test_config_dir = tmp_path / ".amplify-migrator"
        test_config_file = test_config_dir / "config.json"

        monkeypatch.setattr("migrator.CONFIG_DIR", test_config_dir)
        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        config_with_password = {
            "username": "test@example.com",
            "password": "secret123",
            "ADMIN_PASSWORD": "admin_secret",
        }

        save_config(config_with_password)

        with open(test_config_file) as f:
            loaded = json.load(f)
            assert "password" not in loaded
            assert "ADMIN_PASSWORD" not in loaded
            assert "username" in loaded


class TestLoadCachedConfig:
    """Test load_cached_config function"""

    def test_loads_existing_config(self, tmp_path, sample_config, monkeypatch):
        """Test loading existing cached config"""
        test_config_dir = tmp_path / ".amplify-migrator"
        test_config_file = test_config_dir / "config.json"
        test_config_dir.mkdir(parents=True)

        with open(test_config_file, "w") as f:
            json.dump(sample_config, f)

        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        result = load_cached_config()
        assert result == sample_config

    def test_returns_empty_dict_when_file_not_exists(self, tmp_path, monkeypatch):
        """Test loading config when file doesn't exist"""
        test_config_file = tmp_path / "nonexistent.json"
        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        result = load_cached_config()
        assert result == {}

    def test_handles_corrupted_json(self, tmp_path, monkeypatch, capsys):
        """Test handling corrupted JSON file"""
        test_config_file = tmp_path / "config.json"
        test_config_file.write_text("invalid json {")

        monkeypatch.setattr("migrator.CONFIG_FILE", test_config_file)

        result = load_cached_config()
        assert result == {}


class TestGetCachedOrPrompt:
    """Test get_cached_or_prompt function"""

    def test_returns_cached_value(self, sample_config):
        """Test getting value from cache"""
        result = get_cached_or_prompt("excel_path", "Excel path", sample_config)
        assert result == "test_data.xlsx"

    def test_prompts_when_not_in_cache(self):
        """Test getting value via prompt when not in cache"""
        with patch("builtins.input", return_value="new_value"):
            result = get_cached_or_prompt("missing_key", "Test prompt", {})
            assert result == "new_value"

    def test_uses_default_when_not_in_cache(self):
        """Test using default when key not in cache and empty input"""
        with patch("builtins.input", return_value=""):
            result = get_cached_or_prompt("missing_key", "Test prompt", {}, "default123")
            assert result == "default123"

    def test_cached_value_takes_precedence(self, sample_config):
        """Test that cached value takes precedence over prompting"""
        with patch("builtins.input", return_value="should_not_be_used"):
            result = get_cached_or_prompt("username", "Username", sample_config)
            assert result == "test@example.com"  # From cache, not prompt
