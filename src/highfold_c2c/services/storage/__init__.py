"""
SeaweedFS storage service.

Usage::

    from highfold_c2c.services.storage import get_storage

    storage = get_storage()
    await storage.upload_file(local_path, remote_key)
"""

from highfold_c2c.services.storage.seaweed_storage import SeaweedStorage

_storage_instance = None


def get_storage() -> SeaweedStorage:
    """Get the singleton SeaweedStorage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = SeaweedStorage()
    return _storage_instance
