"""Configuration management for Amplify Excel Migrator."""

import json
import logging
from getpass import getpass
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages configuration loading, saving, and user prompts."""

    DEFAULT_CONFIG_DIR = Path.home() / ".amplify-migrator"
    DEFAULT_CONFIG_FILE = "config.json"

    SENSITIVE_KEYS = {"password", "ADMIN_PASSWORD"}

    def __init__(self, config_path: Optional[str] = None):
        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = self.DEFAULT_CONFIG_DIR / self.DEFAULT_CONFIG_FILE

        self._config: Dict[str, Any] = {}

    def load(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            logger.debug(f"Config file not found at {self.config_path}")
            return {}

        try:
            with open(self.config_path, "r") as f:
                self._config = json.load(f)
                logger.debug(f"Loaded configuration from {self.config_path}")
                return self._config
        except Exception as e:
            logger.warning(f"Failed to load cached config: {e}")
            return {}

    def save(self, config: Dict[str, Any]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        sanitized_config = {k: v for k, v in config.items() if k not in self.SENSITIVE_KEYS}

        with open(self.config_path, "w") as f:
            json.dump(sanitized_config, f, indent=2)

        self._config = sanitized_config
        logger.info(f"✅ Configuration saved to {self.config_path}")

    def get(self, key: str, default: Any = None) -> Any:
        if not self._config:
            self.load()
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if not self._config:
            self.load()
        self._config[key] = value

    def update(self, updates: Dict[str, Any]) -> None:
        if not self._config:
            self.load()
        self._config.update(updates)
        self.save(self._config)

    def prompt_for_value(self, prompt_text: str, default: str = "", secret: bool = False) -> str:
        if default:
            display_prompt = f"{prompt_text} [{default}]: "
        else:
            display_prompt = f"{prompt_text}: "

        if secret:
            value = getpass(display_prompt)
        else:
            value = input(display_prompt)

        return value.strip() if value.strip() else default

    def get_or_prompt(self, key: str, prompt_text: str, default: str = "", secret: bool = False) -> str:
        if not self._config:
            self.load()

        if key in self._config:
            return self._config[key]

        return self.prompt_for_value(prompt_text, default, secret)

    def exists(self) -> bool:
        return self.config_path.exists()

    def clear(self) -> None:
        self._config = {}
        if self.config_path.exists():
            self.config_path.unlink()
            logger.info(f"Configuration cleared from {self.config_path}")
