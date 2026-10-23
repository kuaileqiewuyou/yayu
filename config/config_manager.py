"""配置管理器：加载、保存和管理应用配置（单例模式）。"""
import yaml
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import uuid5, NAMESPACE_URL

from config.atomic_io import atomic_write_text
from config.default_character import load_default_character
from config.schema import AppConfig, ApiConfig, SystemConfig, Character, Background
from core.mcp.config import MCPServerConfig, dump_mcp_server_configs, load_mcp_server_configs


class ConfigManager:
    """全局配置管理器（单例）。"""
    _instance: Optional["ConfigManager"] = None
    _config: Optional[AppConfig] = None

    _API_CONFIG_PATH = Path("data/config/api.yaml")
    _API_LOCAL_CONFIG_PATH = Path("data/config/api.local.yaml")
    _CHARACTERS_CONFIG_PATH = Path("data/config/characters.yaml")
    _SYSTEM_CONFIG_PATH = Path("data/config/system_config.yaml")
    _BACKGROUND_CONFIG_PATH = Path("data/config/background.yaml")
    _MCP_CONFIG_PATH = Path("data/config/mcp.yaml")

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_all_configs()
        return cls._instance

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            self._load_all_configs()
            if self._config is None:
                raise RuntimeError("配置加载失败")
        return self._config

    def _load_yaml(self, file_path: Path) -> Any:
        if not file_path.exists():
            return {}
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return {} if data is None else data

    def _merge_api_overlay(self, base_data: Any, local_data: Any) -> Any:
        """Merge api.local.yaml over api.yaml, preserving provider subkeys in dict fields."""
        if not isinstance(base_data, dict) or not isinstance(local_data, dict):
            return base_data

        merged = dict(base_data)
        for key, local_value in local_data.items():
            base_value = merged.get(key)
            if isinstance(base_value, dict) and isinstance(local_value, dict):
                merged[key] = {**base_value, **local_value}
            else:
                merged[key] = local_value
        return merged

    def _load_all_configs(self) -> None:
        try:
            api_data = self._merge_api_overlay(
                self._load_yaml(self._API_CONFIG_PATH),
                self._load_yaml(self._API_LOCAL_CONFIG_PATH),
            )
            characters_data = self._load_yaml(self._CHARACTERS_CONFIG_PATH)
            system_data = self._load_yaml(self._SYSTEM_CONFIG_PATH)
            background_data = self._load_yaml(self._BACKGROUND_CONFIG_PATH)
            mcp_servers = load_mcp_server_configs(self._MCP_CONFIG_PATH)

            api_config = ApiConfig.model_validate(api_data if api_data else {})
            system_config = SystemConfig.model_validate(system_data if system_data else {})

            if characters_data == {}:
                # Missing/blank configuration gets the starter. A saved [] is an
                # intentional deletion and must not resurrect the character.
                characters = [load_default_character()]
            else:
                if not isinstance(characters_data, list):
                    characters_data = []
                characters = [Character.model_validate({
                    **c, "memory_id": c.get("memory_id") or uuid5(
                        NAMESPACE_URL, f"galgame-character:{self._CHARACTERS_CONFIG_PATH.resolve()}:{index}:{c.get('name', '')}"
                    ).hex,
                }) for index, c in enumerate(characters_data)]

            used_character_ids: set[str] = set()
            for index, character in enumerate(characters):
                identity = character.memory_id.strip()
                if not identity or identity in used_character_ids:
                    identity = uuid5(NAMESPACE_URL,
                        f"galgame-character-dedup:{self._CHARACTERS_CONFIG_PATH.resolve()}:{index}:{character.memory_id}:{character.name}"
                    ).hex
                    while identity in used_character_ids:
                        identity = uuid5(NAMESPACE_URL, identity + ":duplicate").hex
                character.memory_id = identity
                used_character_ids.add(identity)

            if not isinstance(background_data, list):
                background_data = []
            backgrounds = [Background.model_validate(b) for b in background_data]

            self._config = AppConfig(
                api_config=api_config,
                system_config=system_config,
                characters=characters,
                backgrounds=backgrounds,
                mcp_servers=mcp_servers,
            )
        except Exception as e:
            print(f"配置加载错误: {e}")
            self._config = AppConfig()

    def _api_save_path(self) -> Path:
        return self._API_LOCAL_CONFIG_PATH

    def save_api_config(self) -> None:
        path = self._api_save_path()
        data = self._config.api_config.model_dump()
        atomic_write_text(path, yaml.dump(data, allow_unicode=True, default_flow_style=False))

    def save_system_config(self) -> None:
        data = self._config.system_config.model_dump()
        atomic_write_text(self._SYSTEM_CONFIG_PATH, yaml.dump(data, allow_unicode=True, default_flow_style=False))

    def save_characters(self) -> None:
        data = [c.model_dump() for c in self._config.characters]
        atomic_write_text(self._CHARACTERS_CONFIG_PATH, yaml.dump(data, allow_unicode=True, default_flow_style=False))

    def save_backgrounds(self) -> None:
        data = [b.model_dump() for b in self._config.backgrounds]
        atomic_write_text(self._BACKGROUND_CONFIG_PATH, yaml.dump(data, allow_unicode=True, default_flow_style=False))

    def save_mcp_servers(self) -> None:
        dump_mcp_server_configs(self._config.mcp_servers, self._MCP_CONFIG_PATH)

    @contextmanager
    def persistence_transaction(self, *, character_selection_only: bool = False):
        """Restore every settings file if grouped persistence fails."""
        paths = [
            self._api_save_path(),
            self._CHARACTERS_CONFIG_PATH,
            self._SYSTEM_CONFIG_PATH,
            self._MCP_CONFIG_PATH,
            self._BACKGROUND_CONFIG_PATH,
        ]
        if character_selection_only:
            paths = [self._CHARACTERS_CONFIG_PATH, self._SYSTEM_CONFIG_PATH]
        resource_roots = [
            self._CHARACTERS_CONFIG_PATH.parent.parent / "sprites",
            self._CHARACTERS_CONFIG_PATH.parent.parent / "avatars",
        ]
        if character_selection_only:
            resource_roots = []
        resource_snapshots = {
            root: {
                path: path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            } if root.exists() else {}
            for root in resource_roots
        }
        snapshots = {
            path: path.read_bytes() if path.exists() else None
            for path in paths
        }
        try:
            yield
        except Exception:
            for root, resource_snapshot in resource_snapshots.items():
                current_resource_files = {
                    path
                    for path in root.rglob("*")
                    if path.is_file()
                } if root.exists() else set()
                for path in current_resource_files - resource_snapshot.keys():
                    path.unlink(missing_ok=True)
                for path, content in resource_snapshot.items():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
            for path, content in snapshots.items():
                if content is None:
                    path.unlink(missing_ok=True)
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            raise

    def character_selection_transaction(self):
        """Changing the active role touches two YAML files, never asset trees."""
        return self.persistence_transaction(character_selection_only=True)

    def get_llm_api_config(self):
        """返回 (provider, model, base_url, api_key)"""
        cfg = self._config.api_config
        provider = cfg.llm_provider
        model = cfg.llm_model.get(provider, "")
        api_key = cfg.llm_api_key.get(provider, "")
        base_url = cfg.llm_base_url
        return provider, model, base_url, api_key

    def get_character_by_name(self, name: str) -> Optional[Character]:
        for c in self._config.characters:
            if c.name == name:
                return c
        return None

    def get_character_by_id(self, character_id: str) -> Optional[Character]:
        return next((character for character in self.characters if character.memory_id == character_id), None)

    @property
    def current_character_index(self) -> int:
        """Resolve the saved identity after renames and list reordering."""
        active_id = self.system_config.active_character_id
        return next((index for index, character in enumerate(self.characters)
                     if character.memory_id == active_id), 0)

    @property
    def current_character(self) -> Optional[Character]:
        characters = self.characters
        return characters[self.current_character_index] if characters else None

    @property
    def api_config(self) -> ApiConfig:
        return self.config.api_config

    @property
    def system_config(self) -> SystemConfig:
        return self.config.system_config

    @property
    def characters(self) -> list:
        return self.config.characters

    @property
    def backgrounds(self) -> list:
        return self.config.backgrounds

    @property
    def mcp_servers(self) -> list:
        return self.config.mcp_servers

    def set_mcp_servers(self, servers: list[MCPServerConfig]) -> None:
        self.config.mcp_servers = servers

    def merged_llm_factory_kwargs(self) -> Dict[str, Any]:
        """返回创建 LLM 适配器所需的参数字典。"""
        provider, model, base_url, api_key = self.get_llm_api_config()
        return {
            "llm_provider": provider,
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
        }

    @property
    def skills_root(self) -> Path:
        return Path(self.system_config.skills_root)

    @classmethod
    def reset(cls):
        """重置单例（用于测试）。"""
        cls._instance = None
        cls._config = None
