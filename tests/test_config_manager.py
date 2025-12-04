"""Tests for ConfigManager class"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
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
def temp_config_manager(tmp_path):
    """Create ConfigManager with temporary config file"""
    config_file = tmp_path / "test_config.json"
    return ConfigManager(str(config_file))


class TestConfigManagerInitialization:
    """Test ConfigManager initialization"""

    def test_default_initialization(self):
        """Test ConfigManager with default config path"""
        manager = ConfigManager()
        assert manager.config_path == Path.home() / ".amplify-migrator" / "config.json"
        assert manager._config == {}

    def test_custom_path_initialization(self, tmp_path):
        """Test ConfigManager with custom config path"""
        custom_path = tmp_path / "custom_config.json"
        manager = ConfigManager(str(custom_path))
        assert manager.config_path == custom_path
        assert manager._config == {}


class TestConfigManagerLoad:
    """Test ConfigManager.load() method"""

    def test_load_existing_config(self, temp_config_manager, sample_config):
        """Test loading existing config file"""
        temp_config_manager.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_config_manager.config_path, "w") as f:
            json.dump(sample_config, f)

        result = temp_config_manager.load()
        assert result == sample_config
        assert temp_config_manager._config == sample_config

    def test_load_nonexistent_config(self, temp_config_manager):
        """Test loading when config file doesn't exist"""
        result = temp_config_manager.load()
        assert result == {}
        assert temp_config_manager._config == {}

    def test_load_corrupted_json(self, temp_config_manager):
        """Test loading corrupted JSON file"""
        temp_config_manager.config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_config_manager.config_path.write_text("invalid json {")

        result = temp_config_manager.load()
        assert result == {}


class TestConfigManagerSave:
    """Test ConfigManager.save() method"""

    def test_save_config(self, temp_config_manager, sample_config):
        """Test saving configuration"""
        temp_config_manager.save(sample_config)

        assert temp_config_manager.config_path.exists()
        with open(temp_config_manager.config_path) as f:
            loaded = json.load(f)
            assert loaded == sample_config

    def test_save_creates_directory(self, tmp_path):
        """Test that save creates parent directories"""
        config_file = tmp_path / "nested" / "dir" / "config.json"
        manager = ConfigManager(str(config_file))

        assert not config_file.parent.exists()
        manager.save({"key": "value"})
        assert config_file.parent.exists()
        assert config_file.exists()

    def test_save_excludes_sensitive_keys(self, temp_config_manager):
        """Test that sensitive keys are not saved"""
        config_with_secrets = {
            "username": "test@example.com",
            "password": "secret123",
            "ADMIN_PASSWORD": "admin_secret",
            "api_endpoint": "https://api.example.com",
        }

        temp_config_manager.save(config_with_secrets)

        with open(temp_config_manager.config_path) as f:
            loaded = json.load(f)
            assert "password" not in loaded
            assert "ADMIN_PASSWORD" not in loaded
            assert "username" in loaded
            assert "api_endpoint" in loaded

    def test_save_updates_internal_config(self, temp_config_manager, sample_config):
        """Test that save updates the internal _config"""
        temp_config_manager.save(sample_config)
        # Note: internal _config excludes sensitive keys
        expected = {k: v for k, v in sample_config.items() if k not in ConfigManager.SENSITIVE_KEYS}
        assert temp_config_manager._config == expected


class TestConfigManagerGet:
    """Test ConfigManager.get() method"""

    def test_get_existing_key(self, temp_config_manager, sample_config):
        """Test getting existing key"""
        temp_config_manager._config = sample_config
        result = temp_config_manager.get("excel_path")
        assert result == "test_data.xlsx"

    def test_get_missing_key_with_default(self, temp_config_manager):
        """Test getting missing key with default value"""
        temp_config_manager._config = {}
        result = temp_config_manager.get("missing_key", "default_value")
        assert result == "default_value"

    def test_get_missing_key_without_default(self, temp_config_manager):
        """Test getting missing key without default"""
        temp_config_manager._config = {}
        result = temp_config_manager.get("missing_key")
        assert result is None

    def test_get_loads_config_if_empty(self, temp_config_manager, sample_config):
        """Test that get() loads config if _config is empty"""
        temp_config_manager.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_config_manager.config_path, "w") as f:
            json.dump(sample_config, f)

        temp_config_manager._config = {}
        result = temp_config_manager.get("excel_path")
        assert result == "test_data.xlsx"


class TestConfigManagerSet:
    """Test ConfigManager.set() method"""

    def test_set_new_key(self, temp_config_manager):
        """Test setting a new key"""
        temp_config_manager._config = {}
        temp_config_manager.set("new_key", "new_value")
        assert temp_config_manager._config["new_key"] == "new_value"

    def test_set_existing_key(self, temp_config_manager, sample_config):
        """Test updating an existing key"""
        temp_config_manager._config = sample_config.copy()
        temp_config_manager.set("excel_path", "new_path.xlsx")
        assert temp_config_manager._config["excel_path"] == "new_path.xlsx"

    def test_set_loads_config_if_empty(self, temp_config_manager, sample_config):
        """Test that set() loads config if _config is empty"""
        temp_config_manager.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_config_manager.config_path, "w") as f:
            json.dump(sample_config, f)

        temp_config_manager._config = {}
        temp_config_manager.set("new_key", "new_value")
        assert "excel_path" in temp_config_manager._config  # From loaded config
        assert temp_config_manager._config["new_key"] == "new_value"


class TestConfigManagerUpdate:
    """Test ConfigManager.update() method"""

    def test_update_config(self, temp_config_manager, sample_config):
        """Test updating config with multiple values"""
        temp_config_manager._config = sample_config.copy()
        updates = {"excel_path": "updated.xlsx", "new_key": "new_value"}

        temp_config_manager.update(updates)

        assert temp_config_manager._config["excel_path"] == "updated.xlsx"
        assert temp_config_manager._config["new_key"] == "new_value"
        assert temp_config_manager.config_path.exists()

    def test_update_saves_to_file(self, temp_config_manager):
        """Test that update() persists changes to file"""
        temp_config_manager._config = {"old_key": "old_value"}
        temp_config_manager.update({"new_key": "new_value"})

        with open(temp_config_manager.config_path) as f:
            loaded = json.load(f)
            assert loaded["old_key"] == "old_value"
            assert loaded["new_key"] == "new_value"


class TestConfigManagerPromptForValue:
    """Test ConfigManager.prompt_for_value() method"""

    def test_prompt_with_default_empty_input(self, temp_config_manager):
        """Test prompt with default when user provides empty input"""
        with patch("builtins.input", return_value=""):
            result = temp_config_manager.prompt_for_value("Test prompt", "default_value")
            assert result == "default_value"

    def test_prompt_with_user_input(self, temp_config_manager):
        """Test prompt with user input"""
        with patch("builtins.input", return_value="user_value"):
            result = temp_config_manager.prompt_for_value("Test prompt", "default_value")
            assert result == "user_value"

    def test_prompt_without_default(self, temp_config_manager):
        """Test prompt without default"""
        with patch("builtins.input", return_value="custom_value"):
            result = temp_config_manager.prompt_for_value("Test prompt")
            assert result == "custom_value"

    def test_prompt_secret_input(self, temp_config_manager):
        """Test prompting for secret (password) input"""
        with patch("amplify_excel_migrator.core.config.getpass", return_value="secret123"):
            result = temp_config_manager.prompt_for_value("Password", secret=True)
            assert result == "secret123"

    def test_prompt_strips_whitespace(self, temp_config_manager):
        """Test that input is stripped of whitespace"""
        with patch("builtins.input", return_value="  value with spaces  "):
            result = temp_config_manager.prompt_for_value("Test prompt")
            assert result == "value with spaces"

    def test_prompt_displays_default_in_brackets(self, temp_config_manager):
        """Test that default is shown in brackets in prompt"""
        with patch("builtins.input", return_value="") as mock_input:
            temp_config_manager.prompt_for_value("Test prompt", "default123")
            mock_input.assert_called_once_with("Test prompt [default123]: ")


class TestConfigManagerGetOrPrompt:
    """Test ConfigManager.get_or_prompt() method"""

    def test_get_or_prompt_returns_cached(self, temp_config_manager, sample_config):
        """Test that cached value is returned without prompting"""
        temp_config_manager._config = sample_config
        with patch("builtins.input", return_value="should_not_be_used"):
            result = temp_config_manager.get_or_prompt("excel_path", "Excel path")
            assert result == "test_data.xlsx"

    def test_get_or_prompt_prompts_when_missing(self, temp_config_manager):
        """Test that prompt is shown when key is missing"""
        temp_config_manager._config = {}
        with patch("builtins.input", return_value="new_value"):
            result = temp_config_manager.get_or_prompt("missing_key", "Test prompt")
            assert result == "new_value"

    def test_get_or_prompt_with_default(self, temp_config_manager):
        """Test get_or_prompt with default value"""
        temp_config_manager._config = {}
        with patch("builtins.input", return_value=""):
            result = temp_config_manager.get_or_prompt("missing_key", "Test prompt", "default123")
            assert result == "default123"

    def test_get_or_prompt_loads_config_if_empty(self, temp_config_manager, sample_config):
        """Test that get_or_prompt loads config if _config is empty"""
        temp_config_manager.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_config_manager.config_path, "w") as f:
            json.dump(sample_config, f)

        temp_config_manager._config = {}
        result = temp_config_manager.get_or_prompt("excel_path", "Excel path")
        assert result == "test_data.xlsx"


class TestConfigManagerExists:
    """Test ConfigManager.exists() method"""

    def test_exists_when_file_exists(self, temp_config_manager):
        """Test exists() returns True when config file exists"""
        temp_config_manager.config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_config_manager.config_path.touch()
        assert temp_config_manager.exists() is True

    def test_exists_when_file_not_exists(self, temp_config_manager):
        """Test exists() returns False when config file doesn't exist"""
        assert temp_config_manager.exists() is False


class TestConfigManagerClear:
    """Test ConfigManager.clear() method"""

    def test_clear_removes_file(self, temp_config_manager, sample_config):
        """Test that clear removes the config file"""
        temp_config_manager.save(sample_config)
        assert temp_config_manager.config_path.exists()

        temp_config_manager.clear()
        assert not temp_config_manager.config_path.exists()

    def test_clear_resets_internal_config(self, temp_config_manager, sample_config):
        """Test that clear resets internal _config"""
        temp_config_manager._config = sample_config
        temp_config_manager.clear()
        assert temp_config_manager._config == {}

    def test_clear_when_file_not_exists(self, temp_config_manager):
        """Test that clear doesn't fail when file doesn't exist"""
        assert not temp_config_manager.config_path.exists()
        temp_config_manager.clear()  # Should not raise
        assert temp_config_manager._config == {}


class TestConfigManagerIntegration:
    """Integration tests for ConfigManager"""

    def test_full_workflow(self, temp_config_manager, sample_config):
        """Test complete workflow: save, load, update, clear"""
        temp_config_manager.save(sample_config)
        assert temp_config_manager.exists()

        loaded = temp_config_manager.load()
        assert loaded["excel_path"] == "test_data.xlsx"

        temp_config_manager.update({"excel_path": "updated.xlsx"})
        assert temp_config_manager.get("excel_path") == "updated.xlsx"

        temp_config_manager.clear()
        assert not temp_config_manager.exists()
        assert temp_config_manager._config == {}

    def test_multiple_managers_same_file(self, tmp_path, sample_config):
        """Test multiple ConfigManager instances with same file"""
        config_file = tmp_path / "shared_config.json"

        manager1 = ConfigManager(str(config_file))
        manager1.save(sample_config)

        manager2 = ConfigManager(str(config_file))
        loaded = manager2.load()
        assert loaded == sample_config
