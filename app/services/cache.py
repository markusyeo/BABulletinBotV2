from typing import Dict, Optional


class CacheStore:
    """Simple in-memory cache used by the bot."""

    def __init__(self) -> None:
        self._file_id_cache: Dict[str, str] = {}
        self._direct_link_cache: Dict[str, str] = {}
        self._url_to_file_id_cache: Dict[str, str] = {}
        self._drive_id_cache: Dict[str, str] = {}

    def get_file_id_for_name(self, name: str) -> Optional[str]:
        return self._file_id_cache.get(name)

    def set_file_id_for_name(self, name: str, file_id: str) -> None:
        self._file_id_cache[name] = file_id

    def get_file_id_for_url(self, url: str) -> Optional[str]:
        return self._url_to_file_id_cache.get(url)

    def set_file_id_for_url(self, url: str, file_id: str) -> None:
        self._url_to_file_id_cache[url] = file_id

    def get_direct_link(self, url: str) -> Optional[str]:
        return self._direct_link_cache.get(url)

    def set_direct_link(self, url: str, direct_link: str) -> None:
        self._direct_link_cache[url] = direct_link

    def get_file_id_for_drive_id(self, drive_id: str) -> Optional[str]:
        return self._drive_id_cache.get(drive_id)

    def set_file_id_for_drive_id(self, drive_id: str, file_id: str) -> None:
        self._drive_id_cache[drive_id] = file_id

    def clear_all(self) -> None:
        self._file_id_cache.clear()
        self._direct_link_cache.clear()
        self._url_to_file_id_cache.clear()
        self._drive_id_cache.clear()


CACHE = CacheStore()
