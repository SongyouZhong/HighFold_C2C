"""
Async Task Processor

Handles concurrent processing of HighFold-C2C tasks with progress tracking.
"""

import asyncio
import json
import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Optional

from highfold_c2c.database.db import get_db_connection
from highfold_c2c.core.pipeline import run_highfold_pipeline
from highfold_c2c.services.storage import get_storage
from highfold_c2c.config import storage as storage_config

logger = logging.getLogger(__name__)


class TaskProgressCallback:
    """Task progress callback handler."""

    def __init__(self, task_id: str, connection):
        self.task_id = task_id
        self.connection = connection
        self._is_completed = False

    async def update_progress(
        self, progress: float, info: Optional[str] = None
    ) -> None:
        if self._is_completed:
            logger.debug(
                "Task %s already completed, skipping progress update",
                self.task_id,
            )
            return

        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute(
                    "UPDATE tasks SET status = %s, info = %s WHERE id = %s",
                    ("processing", info or "", self.task_id),
                )
                await self.connection.commit()

            logger.debug(
                "Task %s progress updated: %.1f%% - %s",
                self.task_id,
                progress,
                info or "",
            )
        except Exception as e:
            logger.error(
                "Failed to update progress for task %s: %s", self.task_id, e
            )

    def mark_completed(self) -> None:
        self._is_completed = True


class AsyncTaskProcessor:
    """Async task processor with concurrent execution support."""

    def __init__(self, max_workers: int = 2):
        self.max_workers = max_workers
        self.thread_executor = ThreadPoolExecutor(max_workers=max_workers)
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.is_running = True

        logger.info(
            "AsyncTaskProcessor initialized with %d workers", max_workers
        )

    async def submit_task(self, task_id: str, job_dir: str) -> bool:
        """Submit a task for async processing."""
        if not self.is_running:
            logger.warning(
                "TaskProcessor is not running, cannot submit task %s", task_id
            )
            return False
        if task_id in self.active_tasks:
            logger.warning("Task %s is already running", task_id)
            return False
        try:
            task = asyncio.create_task(
                self._process_task(task_id, job_dir)
            )
            self.active_tasks[task_id] = task
            logger.info("Task %s submitted successfully", task_id)
            return True
        except Exception as e:
            logger.error("Failed to submit task %s: %s", task_id, e)
            return False

    async def _process_task(self, task_id: str, job_dir: str) -> None:
        """Process a single task with storage integration."""
        connection = None
        temp_job_dir = None

        try:
            connection = await get_db_connection()
            if not connection:
                raise Exception("Failed to connect to database")

            progress_callback = TaskProgressCallback(task_id, connection)
            await progress_callback.update_progress(
                0, "Starting HighFold pipeline"
            )

            storage = get_storage()

            # Prepare temp directory
            storage_config.ensure_temp_dir()
            temp_job_dir = storage_config.temp_dir / task_id
            temp_job_dir.mkdir(parents=True, exist_ok=True)
            temp_input_dir = temp_job_dir / "input"
            temp_input_dir.mkdir(exist_ok=True)

            # Download input config
            await progress_callback.update_progress(
                5, "Downloading input files from storage"
            )
            remote_config_key = f"{job_dir}/input/input.json"
            local_config_file = temp_input_dir / "input.json"

            try:
                await storage.download_file(remote_config_key, local_config_file)
                with open(local_config_file, "r") as f:
                    config = json.load(f)
            except FileNotFoundError:
                config = {}

            # Merge DB params
            from highfold_c2c.database.db import DatabaseManager

            db_params = await DatabaseManager.get_task_params(task_id)
            if db_params:
                for key, val in db_params.items():
                    if val is not None and key not in ("id", "task_id", "created_at", "updated_at"):
                        config[key] = val

            await progress_callback.update_progress(
                10, "Validating configuration"
            )

            # Download FASTA if skipping generation
            if config.get("skip_generate"):
                remote_fasta = f"{job_dir}/input/predict.fasta"
                local_fasta = temp_input_dir / "predict.fasta"
                try:
                    await storage.download_file(remote_fasta, local_fasta)
                    config["fasta_input_path"] = str(local_fasta)
                except FileNotFoundError:
                    pass

            # Update status -> running
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "UPDATE tasks SET status = %s, started_at = NOW(), info = %s WHERE id = %s",
                    ("running", "Pipeline starting", task_id),
                )
                await connection.commit()

            await progress_callback.update_progress(
                20, "Running HighFold pipeline"
            )

            # Run pipeline in thread executor
            pipeline_result = await asyncio.get_event_loop().run_in_executor(
                self.thread_executor,
                run_highfold_pipeline,
                config,
                temp_job_dir,
            )

            # Upload results
            await progress_callback.update_progress(
                80, "Uploading results to storage"
            )
            output_dir = temp_job_dir / "output"
            if output_dir.exists():
                for result_file in output_dir.rglob("*"):
                    if result_file.is_file():
                        relative_path = result_file.relative_to(output_dir)
                        remote_key = f"{job_dir}/output/{relative_path}"
                        await storage.upload_file(result_file, remote_key)

            # Mark finished
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "UPDATE tasks SET status = %s, info = %s, finished_at = NOW() WHERE id = %s",
                    (
                        "finished",
                        json.dumps(pipeline_result, default=str),
                        task_id,
                    ),
                )
                await connection.commit()

            progress_callback.mark_completed()
            logger.info("Task %s completed successfully", task_id)

        except Exception as e:
            logger.error("Task %s failed: %s", task_id, str(e))
            if connection:
                try:
                    async with connection.cursor() as cursor:
                        await cursor.execute(
                            "UPDATE tasks SET status = %s, info = %s, finished_at = NOW() WHERE id = %s",
                            ("failed", str(e), task_id),
                        )
                        await connection.commit()
                except Exception as db_error:
                    logger.error(
                        "Failed to update task status in database: %s",
                        db_error,
                    )
        finally:
            if connection:
                connection.close()
            if temp_job_dir and temp_job_dir.exists():
                try:
                    shutil.rmtree(temp_job_dir, ignore_errors=True)
                except Exception as e:
                    logger.warning(
                        f"Failed to clean up temp directory: {e}"
                    )
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        if task_id not in self.active_tasks:
            logger.warning("Task %s not found in active tasks", task_id)
            return False
        try:
            task = self.active_tasks[task_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            connection = await get_db_connection()
            if connection:
                try:
                    async with connection.cursor() as cursor:
                        await cursor.execute(
                            "UPDATE tasks SET status = %s, info = %s, finished_at = NOW() WHERE id = %s",
                            ("cancelled", "Task cancelled by user", task_id),
                        )
                        await connection.commit()
                finally:
                    connection.close()

            del self.active_tasks[task_id]
            logger.info("Task %s cancelled successfully", task_id)
            return True
        except Exception as e:
            logger.error("Failed to cancel task %s: %s", task_id, e)
            return False

    def get_active_tasks(self) -> list:
        """Return list of active task IDs."""
        return list(self.active_tasks.keys())

    def get_task_count(self) -> int:
        """Return number of currently active tasks."""
        return len(self.active_tasks)

    async def shutdown(self) -> None:
        """Gracefully shut down the processor."""
        logger.info("Shutting down AsyncTaskProcessor...")
        self.is_running = False
        for task_id, task in self.active_tasks.items():
            logger.info("Cancelling task: %s", task_id)
            task.cancel()
        if self.active_tasks:
            await asyncio.gather(
                *self.active_tasks.values(), return_exceptions=True
            )
        self.thread_executor.shutdown(wait=True)
        logger.info("AsyncTaskProcessor shutdown complete")
