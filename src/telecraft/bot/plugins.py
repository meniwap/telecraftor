from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


class PluginLoader:
    def __init__(self, *, router: Any | None = None) -> None:
        self._router = router
        self._loaded: dict[str, ModuleType] = {}
        self._path_sources: dict[str, Path] = {}

    @property
    def loaded(self) -> dict[str, ModuleType]:
        return dict(self._loaded)

    async def _call_hook(self, module: ModuleType, hook_name: str, *, router: Any | None) -> None:
        hook = getattr(module, hook_name, None)
        if not callable(hook):
            return
        out = hook(router)
        if inspect.isawaitable(out):
            await out

    async def load_module(
        self,
        module_name: str,
        *,
        router: Any | None = None,
        force_reload: bool = False,
    ) -> ModuleType:
        r = self._router if router is None else router
        name = str(module_name)

        if force_reload and name in self._loaded:
            await self.unload(name, router=r)

        if name in self._loaded:
            return self._loaded[name]

        if force_reload and name in sys.modules:
            mod = importlib.reload(sys.modules[name])
        else:
            mod = importlib.import_module(name)
        await self._call_hook(mod, "setup", router=r)
        self._loaded[name] = mod
        self._path_sources.pop(name, None)
        return mod

    async def load_path(
        self,
        path: str | Path,
        *,
        module_name: str | None = None,
        router: Any | None = None,
        force_reload: bool = False,
    ) -> ModuleType:
        r = self._router if router is None else router
        p = Path(path).expanduser().resolve()
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Plugin file not found: {p}")

        name = module_name or f"telecraft_plugin_{p.stem}"
        if force_reload and name in self._loaded:
            await self.unload(name, router=r)
        if name in self._loaded:
            return self._loaded[name]

        module = ModuleType(name)
        module.__file__ = str(p)
        module.__package__ = name.rpartition(".")[0]
        sys.modules[name] = module
        source = p.read_text(encoding="utf-8")
        exec(compile(source, str(p), "exec"), module.__dict__)

        await self._call_hook(module, "setup", router=r)
        self._loaded[name] = module
        self._path_sources[name] = p
        return module

    async def unload(self, module_name: str, *, router: Any | None = None) -> None:
        r = self._router if router is None else router
        name = str(module_name)
        module = self._loaded.pop(name, None)
        self._path_sources.pop(name, None)
        if module is None:
            return
        await self._call_hook(module, "teardown", router=r)
        if name in sys.modules:
            del sys.modules[name]

    async def reload(self, module_name: str, *, router: Any | None = None) -> ModuleType:
        name = str(module_name)
        r = self._router if router is None else router
        path = self._path_sources.get(name)
        if path is not None:
            return await self.load_path(path, module_name=name, router=r, force_reload=True)
        return await self.load_module(name, router=r, force_reload=True)
