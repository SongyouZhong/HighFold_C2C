"""
HighFold-C2C Test Fixtures
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_storage():
    """Mock SeaweedStorage instance."""
    storage = AsyncMock()
    storage.upload_file = AsyncMock(return_value="remote/key")
    storage.download_file = AsyncMock(return_value=Path("/tmp/file"))
    storage.download_bytes = AsyncMock(return_value=b"content")
    storage.file_exists = AsyncMock(return_value=True)
    storage.delete_file = AsyncMock(return_value=True)
    storage.list_files = AsyncMock(return_value=[])
    storage.upload_directory = AsyncMock(return_value=[])
    storage.download_directory = AsyncMock(return_value=[])
    storage.get_presigned_url = AsyncMock(return_value="http://example.com/file")
    storage.ensure_bucket_exists = AsyncMock()
    return storage


@pytest.fixture
def mock_db_connection():
    """Mock async database connection."""
    cursor_mock = AsyncMock()
    cursor_mock.execute = AsyncMock()
    cursor_mock.fetchall = AsyncMock(return_value=[])
    cursor_mock.fetchone = AsyncMock(return_value=None)

    connection = AsyncMock()
    connection.cursor = MagicMock(return_value=cursor_mock)
    connection.commit = AsyncMock()
    connection.close = MagicMock()

    # Support async context manager for cursor
    cursor_mock.__aenter__ = AsyncMock(return_value=cursor_mock)
    cursor_mock.__aexit__ = AsyncMock(return_value=False)

    return connection


@pytest.fixture
def sample_task_config():
    """Sample task configuration for testing."""
    return {
        "core_sequence": "NNN",
        "span_len": 5,
        "num_sample": 20,
        "temperature": 1.0,
        "top_p": 0.9,
        "seed": 42,
        "model_type": "alphafold2",
        "msa_mode": "single_sequence",
        "disulfide_bond_pairs": None,
        "num_models": 5,
        "num_recycle": None,
        "use_templates": False,
        "amber": False,
        "num_relax": 0,
        "skip_generate": False,
        "skip_predict": False,
        "skip_evaluate": False,
        "checkpoint": "checkpoints/c2c_model.pt",
        "colabfold_bin": "colabfold_batch",
    }


@pytest.fixture
def sample_task_db_row():
    """Sample task row as returned by DB query."""
    return (
        "task-uuid-1234",
        "user-uuid-5678",
        "highfold_c2c",
        "jobs/highfold_c2c/task-uuid-1234",
        "pending",
    )


@pytest.fixture
def sample_db_params():
    """Sample highfold_task_params row as a dict."""
    return {
        "id": "param-id-1234",
        "task_id": "task-uuid-1234",
        "core_sequence": "NNN",
        "span_len": 5,
        "num_sample": 20,
        "temperature": 1.0,
        "top_p": 0.9,
        "seed": 42,
        "model_type": "alphafold2",
        "msa_mode": "single_sequence",
        "disulfide_bond_pairs": None,
        "num_models": 5,
        "num_recycle": None,
        "use_templates": False,
        "amber": False,
        "num_relax": 0,
        "skip_generate": False,
        "skip_predict": False,
        "skip_evaluate": False,
    }


@pytest.fixture
def temp_directory(tmp_path):
    """Temporary directory for test file operations."""
    test_dir = tmp_path / "highfold_c2c_test"
    test_dir.mkdir()
    return test_dir
