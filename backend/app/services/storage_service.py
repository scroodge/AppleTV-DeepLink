"""Storage service for pyatv credentials."""
import json
import logging
from typing import Optional, Dict, Any
from pyatv import storage
from pyatv.storage.file_storage import FileStorage
import os

logger = logging.getLogger(__name__)


class DatabaseStorage:
    """Custom storage adapter that stores credentials in database."""
    
    def __init__(self, credentials_json: Optional[str] = None):
        """Initialize with credentials from database JSON string."""
        self._credentials = {}
        if credentials_json:
            try:
                self._credentials = json.loads(credentials_json)
            except json.JSONDecodeError:
                logger.warning("Failed to parse credentials JSON")
                self._credentials = {}
    
    def save(self, identifier: str, credentials: Dict[str, Any]) -> None:
        """Save credentials for a device. Merges with existing so we keep both AirPlay and Companion."""
        existing = self._credentials.get(identifier)
        # Legacy: existing may be a single string (one protocol); treat as generic 'credentials'
        if isinstance(existing, str):
            existing = {"credentials": existing}
        if isinstance(credentials, dict):
            merged = {**(existing or {}), **credentials}
            self._credentials[identifier] = merged
            logger.debug(f"Merged and saved credentials for {identifier} (keys: {list(merged.keys())})")
        else:
            self._credentials[identifier] = credentials
            logger.debug(f"Saved credentials for {identifier}")
    
    def load(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Load credentials for a device."""
        return self._credentials.get(identifier)
    
    def remove(self, identifier: str) -> None:
        """Remove credentials for a device."""
        if identifier in self._credentials:
            del self._credentials[identifier]
            logger.debug(f"Removed credentials for {identifier}")
    
    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """Get all stored credentials."""
        return self._credentials.copy()
    
    def to_json(self) -> str:
        """Serialize credentials to JSON string for database storage."""
        return json.dumps(self._credentials)


def create_storage_from_db(credentials_json: Optional[str]) -> DatabaseStorage:
    """Create a DatabaseStorage instance from database JSON."""
    return DatabaseStorage(credentials_json)
