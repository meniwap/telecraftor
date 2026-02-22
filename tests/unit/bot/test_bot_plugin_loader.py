from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from telecraft.bot.plugins import PluginLoader
from telecraft.bot.router import Router


def test_plugin_loader__load_path__returns_expected_shape() -> None:
    async def _case() -> int:
        router = Router()
        loader = PluginLoader(router=router)
        with TemporaryDirectory() as td:
            plugin_path = Path(td) / "plugin_a.py"
            plugin_path.write_text(
                "def setup(router):\n"
                "    router._plugin_value = 1\n"
                "def teardown(router):\n"
                "    router._plugin_value = 2\n",
                encoding="utf-8",
                newline="\n",
            )
            await loader.load_path(plugin_path, module_name="tc_plugin_a")
            loaded_value = int(getattr(router, "_plugin_value", 0))
            await loader.unload("tc_plugin_a")
            unloaded_value = int(getattr(router, "_plugin_value", 0))
            return loaded_value * 10 + unloaded_value

    assert asyncio.run(_case()) == 12


def test_plugin_loader__reload__returns_expected_shape() -> None:
    async def _case() -> int:
        router = Router()
        loader = PluginLoader(router=router)
        with TemporaryDirectory() as td:
            plugin_path = Path(td) / "plugin_b.py"
            plugin_path.write_text(
                "def setup(router):\n"
                "    router._plugin_reload_value = 3\n",
                encoding="utf-8",
                newline="\n",
            )
            await loader.load_path(plugin_path, module_name="tc_plugin_b")
            first = int(getattr(router, "_plugin_reload_value", 0))

            plugin_path.write_text(
                "def setup(router):\n"
                "    router._plugin_reload_value = 7\n",
                encoding="utf-8",
                newline="\n",
            )
            await loader.reload("tc_plugin_b")
            second = int(getattr(router, "_plugin_reload_value", 0))
            await loader.unload("tc_plugin_b")
            return first * 10 + second

    assert asyncio.run(_case()) == 37
