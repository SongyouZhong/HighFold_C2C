"""Tests for HighFoldTaskProcessor and AsyncTaskProcessor."""

from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest


class TestHighFoldTaskProcessor:
    """Test HighFoldTaskProcessor."""

    @pytest.mark.asyncio
    async def test_query_no_pending_tasks(self, mock_db_connection):
        """Test query_and_process_tasks when no tasks are pending."""
        with patch(
            "highfold_c2c.core.task_processor.DatabaseManager"
        ) as MockDB:
            MockDB.get_pending_highfold_tasks = AsyncMock(return_value=[])

            from highfold_c2c.core.task_processor import (
                HighFoldTaskProcessor,
            )

            with patch(
                "highfold_c2c.core.task_processor.get_storage"
            ) as mock_get_storage:
                mock_get_storage.return_value = AsyncMock()

                processor = HighFoldTaskProcessor()
                await processor.query_and_process_tasks()

            MockDB.get_pending_highfold_tasks.assert_called_once()


class TestAsyncTaskProcessor:
    """Test AsyncTaskProcessor."""

    def test_initialization(self):
        """Test AsyncTaskProcessor initializes with correct defaults."""
        from highfold_c2c.core.async_processor import AsyncTaskProcessor

        processor = AsyncTaskProcessor(max_workers=3)
        assert processor.max_workers == 3
        assert processor.is_running is True
        assert processor.get_task_count() == 0
        assert processor.get_active_tasks() == []

        # Clean up
        processor.thread_executor.shutdown(wait=False)

    def test_get_active_tasks(self):
        """Test get_active_tasks returns empty list initially."""
        from highfold_c2c.core.async_processor import AsyncTaskProcessor

        processor = AsyncTaskProcessor()
        assert processor.get_active_tasks() == []
        assert processor.get_task_count() == 0

        # Clean up
        processor.thread_executor.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test graceful shutdown."""
        from highfold_c2c.core.async_processor import AsyncTaskProcessor

        processor = AsyncTaskProcessor()
        await processor.shutdown()

        assert processor.is_running is False
