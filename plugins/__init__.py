"""插件系统"""
from typing import Dict, List, Optional
import importlib
import yaml
from pathlib import Path


class PluginManager:
    """插件管理器"""
    def __init__(self):
        self._plugins: Dict[str, Any] = {}
        self._loaded = False

    def load_plugins(self, config_path: str = "data/config/plugins.yaml"):
        if self._loaded:
            return
        path = Path(config_path)
        if not path.exists():
            self._loaded = True
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                plugin_list = yaml.safe_load(f) or []
            for plugin_info in plugin_list:
                name = plugin_info.get("name", "")
                enabled = plugin_info.get("enabled", True)
                if name and enabled:
                    self._load_single(name)
        except Exception as e:
            print(f"加载插件配置失败: {e}")
        self._loaded = True

    def _load_single(self, name: str):
        try:
            mod = importlib.import_module(f"plugins.{name}")
            self._plugins[name] = mod
        except ImportError as e:
            print(f"插件 {name} 加载失败: {e}")

    def get_plugin(self, name: str):
        return self._plugins.get(name)

    def shutdown_all(self):
        for name, plugin in self._plugins.items():
            if hasattr(plugin, 'shutdown'):
                try:
                    plugin.shutdown()
                except Exception:
                    pass


_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager


def ensure_plugins_loaded(config=None):
    mgr = get_plugin_manager()
    mgr.load_plugins()
