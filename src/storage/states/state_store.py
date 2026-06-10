import os
import json
import asyncio
from pathlib import Path
from typing import Any
from collections.abc import Mapping


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self._state: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._loaded = False

    async def load(self) -> None:
        """
        Public warmup method.
        Loads the JSON file into this process's memory cache.
        """
        await self._load()

    async def _load(self) -> None:
        async with self._lock:
            if self._loaded:
                return

            self.path.parent.mkdir(parents=True, exist_ok=True)

            if self.path.exists():
                text = await asyncio.to_thread(
                    self.path.read_text,
                    encoding="utf-8",
                )
                self._state = json.loads(text) if text.strip() else {}
            else:
                self._state = {}

            self._loaded = True

    async def get(self, key: str, default: Any = None) -> Any:
        await self._load()
        return self._state.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        await self._load()

        async with self._lock:
            self._state[key] = value
            await self._save_locked()

    async def update(self, values: dict[str, Any]) -> None:
        if not isinstance(values, dict):
            raise TypeError("values must be a dict")

        await self._load()

        async with self._lock:
            if not isinstance(self._state, dict):
                self._state = {}

            self.deep_merge_dict(self._state, values)
            await self._save_locked()

    async def all(self) -> dict[str, Any]:
        """
        Returns a shallow copy of the in-memory state.
        """
        await self._load()
        return dict(self._state)

    async def _save_locked(self) -> None:
        """
        Caller must hold self._lock.
        Saves the current in-memory cache to disk.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = self.path.with_suffix(".json.tmp")
        text = json.dumps(self._state, indent=2, sort_keys=True)

        await asyncio.to_thread(
            tmp_path.write_text,
            text,
            encoding="utf-8",
        )

        await asyncio.to_thread(tmp_path.replace, self.path)

    def deep_merge_dict(self, target: dict[str, Any], updates: dict[str, Any]) -> None:
        """
        Recursively merge updates into target.

        Existing nested dicts are preserved.
        Missing nested dicts are created.
        Non-dict values are overwritten.
        """
        for key, value in updates.items():
            if isinstance(value, Mapping) and isinstance(target.get(key), dict):
                self.deep_merge_dict(target[key], dict(value))
            else:
                target[key] = value

    async def get_path(self, path: list[str], default: Any = None) -> Any:
        """
        Example:
        last_run_at = await reporting_state.get_path(
            ["acenda", "orders", "incremental", "last_run_at"]
        )
        """
        if not path:
            return default

        await self._load()

        current: Any = self._state

        for key in path:
            if not isinstance(current, dict):
                return default

            if key not in current:
                return default

            current = current[key]

        return current

    async def set_path(self, path: list[str], value: Any) -> None:
        """
        Example:
        await reporting_state.set_path(
            ["acenda", "orders", "incremental", "last_run_at"],
            "2026-06-04T12:00:00Z",
        )
        """

        if not path:
            raise ValueError("path cannot be empty")

        await self._load()

        async with self._lock:
            if not isinstance(self._state, dict):
                self._state = {}

            current = self._state

            for key in path[:-1]:
                existing = current.get(key)

                if not isinstance(existing, dict):
                    existing = {}
                    current[key] = existing

                current = existing

            current[path[-1]] = value
            await self._save_locked()


class StatePaths:
    def __init__(self, root: Path | str | None = None) -> None:
        if root is not None:
            self.root = Path(root)
        else:
            self.root = Path(os.getenv("LAKE_ROOT", "/tmp/bokser_app_state"))

    @property
    def sos_state(self) -> Path:
        return self.root / "raw" / "sos_inventory" / "_state" / "sos_query_state.json"

    @property
    def acenda_state(self) -> Path:
        return self.root / "raw" / "acenda" / "_state" / "acenda_query_state.json"

    @property
    def reporting(self) -> Path:
        return self.root / "reporting_state.json"


# Global paths object
state_paths = StatePaths()


# Global StateStore instances.
# These stay alive for the lifetime of the Python worker process.
sos_state = StateStore(state_paths.sos_state)
acenda_state = StateStore(state_paths.acenda_state)
reporting_state = StateStore(state_paths.reporting)


# Optional convenience registry
state_stores: dict[str, StateStore] = {
    "sos": sos_state,
    "acenda": acenda_state,
    "reporting": reporting_state,
}


async def warmup_state_files() -> None:
    """
    Call this once when the worker starts.

    This loads all state JSON files into memory so future get/set/update calls
    use the in-process cache.
    """
    await asyncio.gather(
        sos_state.load(),
        acenda_state.load(),
        reporting_state.load(),
    )
