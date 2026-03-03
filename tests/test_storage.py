"""Tests for SeaweedStorage and get_storage singleton."""

from unittest.mock import patch, MagicMock

import pytest


class TestSeaweedStorage:
    """Test SeaweedStorage initialization and URL construction."""

    def test_init(self):
        """Test storage initialization reads config correctly."""
        with patch("highfold_c2c.services.storage.seaweed_storage.storage_config") as mock_config:
            mock_config.filer_endpoint = "http://test:8888"
            mock_config.bucket = "test-bucket"
            mock_config.get_filer_base_url.return_value = "http://test:8888/buckets/test-bucket"

            from highfold_c2c.services.storage.seaweed_storage import SeaweedStorage

            storage = SeaweedStorage()
            assert storage.filer_endpoint == "http://test:8888"
            assert storage.bucket == "test-bucket"
            assert storage.base_url == "http://test:8888/buckets/test-bucket"

    def test_get_url(self):
        """Test URL construction from remote key."""
        with patch("highfold_c2c.services.storage.seaweed_storage.storage_config") as mock_config:
            mock_config.filer_endpoint = "http://test:8888"
            mock_config.bucket = "test-bucket"
            mock_config.get_filer_base_url.return_value = "http://test:8888/buckets/test-bucket"

            from highfold_c2c.services.storage.seaweed_storage import SeaweedStorage

            storage = SeaweedStorage()
            url = storage._get_url("jobs/highfold_c2c/123/input/input.json")
            assert url == "http://test:8888/buckets/test-bucket/jobs/highfold_c2c/123/input/input.json"

    def test_get_url_strips_leading_slash(self):
        """Test that leading slashes are stripped from keys."""
        with patch("highfold_c2c.services.storage.seaweed_storage.storage_config") as mock_config:
            mock_config.filer_endpoint = "http://test:8888"
            mock_config.bucket = "test-bucket"
            mock_config.get_filer_base_url.return_value = "http://test:8888/buckets/test-bucket"

            from highfold_c2c.services.storage.seaweed_storage import SeaweedStorage

            storage = SeaweedStorage()
            url = storage._get_url("/jobs/highfold_c2c/123/input.json")
            assert not url.startswith("http://test:8888/buckets/test-bucket//")


class TestGetStorage:
    """Test the get_storage singleton."""

    def test_singleton(self):
        """Test that get_storage returns the same instance."""
        import highfold_c2c.services.storage as storage_module

        # Reset singleton
        storage_module._storage_instance = None

        with patch("highfold_c2c.services.storage.SeaweedStorage") as MockClass:
            instance = MagicMock()
            MockClass.return_value = instance

            s1 = storage_module.get_storage()
            s2 = storage_module.get_storage()

            assert s1 is s2
            MockClass.assert_called_once()

        # Cleanup
        storage_module._storage_instance = None
