from __future__ import annotations

import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Literal, Optional

from .adapters.remote_sources import RemoteError, bing_images, nasa_images
from .adapters.optimizer import FRAME_RATES
from .service import AmbientService

_SCOPES = ("background", "radio")
_FOLDER_SCOPES = ("background", "music", "library")

Pool = Literal["quick", "jobs", "network", "lookup"]
_POOL_WORKERS: dict[str, int] = {"quick": 2, "jobs": 1, "network": 2, "lookup": 2}


class AmbientRpc:
    """Decky RPC surface of the Ambient domain, mixed into the Plugin class by main.py."""

    _ambient_service: Optional[AmbientService] = None
    _ambient_pools: Optional[dict[str, ThreadPoolExecutor]] = None
    _ambient_closed: bool = False
    _ambient_lock = threading.Lock()

    def _ambient_service_factory(self) -> AmbientService:
        import decky

        return AmbientService(
            state_dir=os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "ambient"),
            cache_dir=os.path.join(decky.DECKY_PLUGIN_RUNTIME_DIR, "ambient-cache"),
            home=decky.DECKY_USER_HOME,
        )

    def _ambient_get_service(self) -> AmbientService:
        with self._ambient_lock:
            if self._ambient_closed:
                raise RuntimeError("ambient_stopped")
            if self._ambient_service is None:
                self._ambient_service = self._ambient_service_factory()
            return self._ambient_service

    async def _ambient_call(self, fn: Callable[[AmbientService], Any], pool: Pool = "quick") -> Any:
        """Quick calls share two workers. Encodes, network fetches and game media lookups each get their
        own pool, so a slow download never holds back settings and a running encode never delays a trailer."""
        if self._ambient_closed:
            raise RuntimeError("ambient_stopped")
        with self._ambient_lock:
            if self._ambient_pools is None:
                self._ambient_pools = {name: ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"ambient-{name}") for name, workers in _POOL_WORKERS.items()}
            executor = self._ambient_pools[pool]
        return await asyncio.get_running_loop().run_in_executor(executor, lambda: fn(self._ambient_get_service()))

    def _ambient_stop(self) -> None:
        """Never blocks the event loop: the server and running jobs are closed on a helper thread."""
        with self._ambient_lock:
            self._ambient_closed = True
            service, self._ambient_service = self._ambient_service, None
            pools, self._ambient_pools = self._ambient_pools, None
        for executor in (pools or {}).values():
            executor.shutdown(wait=False, cancel_futures=True)
        if service is not None:
            threading.Thread(target=service.close, name="ambient-close", daemon=True).start()

    def ambient_diagnostics(self) -> dict[str, Any]:
        service = self._ambient_service
        if service is None:
            return {"mediaServer": "stopped", "started": False}
        return {"started": True, **service.diagnostics()}

    async def get_ambient_state(self) -> dict[str, Any]:
        return await self._ambient_call(lambda s: s.get_state())

    async def save_ambient_settings(self, settings: dict) -> dict[str, Any]:
        return await self._ambient_call(lambda s: s.save_settings(settings))

    async def cancel_ambient_jobs(self) -> bool:
        with self._ambient_lock:
            if self._ambient_closed or self._ambient_service is None:
                return False
            self._ambient_service.cancel_jobs()
        return True

    async def reconcile_ambient_cache(self) -> bool:
        return await self._ambient_call(lambda s: s.reconcile_games())

    async def scan_ambient_sources(self) -> dict[str, Any]:
        return await self._ambient_call(lambda s: s.scan())

    async def get_ambient_media_url(self, media_id: str) -> Optional[str]:
        if not isinstance(media_id, str):
            return None
        return await self._ambient_call(lambda s: s.media_url(media_id))

    async def get_ambient_game_media(self, appid: str, name: str, store: bool = True) -> dict[str, Any]:
        if not isinstance(appid, str) or not appid.isdigit() or len(appid) > 10 or not isinstance(name, str):
            return {"trailer": None, "theme": None}
        return await self._ambient_call(lambda s: s.game_media(appid, name[:120], store=store is not False), pool="lookup")

    async def set_ambient_game_volume(self, percent: int) -> dict[str, Any]:
        if isinstance(percent, bool) or not isinstance(percent, (int, float)):
            return {"supported": False, "streams": 0}
        return await self._ambient_call(lambda s: s.set_game_volume(int(percent)))

    async def get_ambient_video_page(self) -> Optional[str]:
        return await self._ambient_call(lambda s: s.video_page_url())

    async def add_ambient_folder(self, path: str, scope: str) -> Optional[dict[str, Any]]:
        if scope not in _FOLDER_SCOPES or not isinstance(path, str):
            return None

        def add(s: AmbientService) -> Optional[dict[str, Any]]:
            try:
                return s.add_folder(path, scope)  # type: ignore[arg-type]
            except ValueError:
                return None

        return await self._ambient_call(add)

    async def add_ambient_favorite(self, scope: str, url: str, name: str, art: str = "", subtitle: str = "") -> Optional[dict[str, Any]]:
        if scope not in _SCOPES or not all(isinstance(v, str) for v in (url, name, art, subtitle)):
            return None
        return await self._ambient_call(lambda s: s.add_favorite(scope, url, name, art, subtitle))  # type: ignore[arg-type]

    async def remove_ambient_item(self, scope: str, item_id: str) -> Optional[dict[str, Any]]:
        if scope not in (*_SCOPES, "music", "library") or not isinstance(item_id, str):
            return None
        return await self._ambient_call(lambda s: s.remove_item(scope, item_id))  # type: ignore[arg-type]

    async def add_ambient_playlist(self, url: str, name: str) -> Optional[dict[str, Any]]:
        if not isinstance(url, str) or not isinstance(name, str) or not url.lower().startswith(("https://", "http://")):
            return None
        return await self._ambient_call(lambda s: s.add_playlist(url, name), pool="network")

    async def remove_ambient_playlist(self, playlist_id: str) -> Optional[dict[str, Any]]:
        if not isinstance(playlist_id, str):
            return None
        return await self._ambient_call(lambda s: s.remove_playlist(playlist_id))

    async def get_ambient_playlist(self, playlist_id: str) -> Optional[dict[str, Any]]:
        if not isinstance(playlist_id, str):
            return None
        return await self._ambient_call(lambda s: s.playlist(playlist_id), pool="network")

    async def restore_ambient_suggested(self, scope: str, item_id: str = "") -> Optional[dict[str, Any]]:
        if scope not in _SCOPES or not isinstance(item_id, str) or (item_id and not item_id.startswith("suggested.")):
            return None
        return await self._ambient_call(lambda s: s.restore_suggested(scope, item_id))  # type: ignore[arg-type]

    async def get_ambient_remote_feed(self, source: str, market: str = "en-US") -> list[dict[str, str]]:
        if source == "nasa-apod":
            def nasa(s: AmbientService) -> list[dict[str, str]]:
                try:
                    return nasa_images(on_fallback=lambda: s.record_event("remote_error", "nasa:apod_unavailable:library_fallback"))
                except RemoteError as error:
                    s.record_event("remote_error", error.reason)
                    raise
            return await self._ambient_call(nasa, pool="network")
        if source == "bing-daily":
            safe_market = market if isinstance(market, str) and len(market) <= 8 else "en-US"
            return await self._ambient_call(lambda s: bing_images(market=safe_market), pool="network")
        return []

    async def cache_ambient_remote(self, url: str, collection: str = "") -> dict[str, Any]:
        if not isinstance(url, str):
            return {"error": "invalid_url"}

        def cache(s: AmbientService) -> dict[str, Any]:
            try:
                return s.cache_remote(url, collection if isinstance(collection, str) else "")
            except RemoteError as exc:
                return {"error": exc.reason}

        return await self._ambient_call(cache, pool="network")

    async def optimize_ambient_media(self, media_id: str, height: int, fps: int = 30) -> dict[str, Any]:
        if not isinstance(media_id, str) or not isinstance(height, int) or isinstance(height, bool) or fps not in FRAME_RATES:
            return {"error": "invalid_arguments"}
        return await self._ambient_call(lambda s: s.optimize_media(media_id, height, fps), pool="jobs")

    async def search_ambient_radio(self, name: str = "", country: str = "", tag: str = "") -> list[dict[str, Any]]:
        args = [a if isinstance(a, str) else "" for a in (name, country, tag)]
        return await self._ambient_call(lambda s: s.search_radio(*args), pool="network")

    async def get_ambient_radio_catalog(self) -> dict[str, Any]:
        return await self._ambient_call(lambda s: s.radio_catalog(), pool="network")

    async def discover_ambient_radio(self, filters: dict) -> list[dict[str, Any]]:
        if not isinstance(filters, dict):
            return []
        return await self._ambient_call(lambda s: s.discover_radio(filters), pool="network")

    async def get_ambient_suggested_stations(self) -> list[dict[str, Any]]:
        return await self._ambient_call(lambda s: s.suggested_stations(), pool="network")

    async def resolve_ambient_radio(self, station_id: str) -> Optional[dict[str, Any]]:
        if not isinstance(station_id, str):
            return None
        return await self._ambient_call(lambda s: s.resolve_radio(station_id), pool="network")

    async def start_ambient_share(self, texts: dict) -> dict[str, Any]:
        if not isinstance(texts, dict):
            return {"error": "invalid_arguments"}
        return await self._ambient_call(lambda s: s.start_share(texts))

    async def take_ambient_shared(self) -> dict[str, Any]:
        return await self._ambient_call(lambda s: s.take_shared())

    async def stop_ambient_share(self) -> bool:
        await self._ambient_call(lambda s: s.stop_share())
        return True

    async def record_ambient_event(self, kind: str, detail: str) -> bool:
        if not isinstance(kind, str) or not isinstance(detail, str):
            return False
        return await self._ambient_call(lambda s: s.record_event(kind, detail))
