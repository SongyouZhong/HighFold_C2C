"""
HighFold Task Processor

Processes HighFold-C2C tasks from the database with SeaweedFS storage support.
Polls the database for pending tasks and runs the pipeline.
"""

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List

from highfold_c2c.database.db import DatabaseManager, get_db_connection
from highfold_c2c.core.pipeline import run_highfold_pipeline
from highfold_c2c.services.storage import get_storage
from highfold_c2c.config import storage as storage_config
from highfold_c2c.config.settings import get_settings

logger = logging.getLogger(__name__)


class HighFoldTaskProcessor:
    """HighFold-C2C task processor with SeaweedFS storage support."""

    def __init__(self):
        self.storage = get_storage()
        self.settings = get_settings()

    async def process_highfold_task(
        self, task_id: str, job_dir: str, connection
    ) -> None:
        """Process a single HighFold-C2C task.

        Workflow:
            1. Create temp dir
            2. Download input.json (and optional FASTA) from SeaweedFS
            3. Merge input.json with DB params
            4. Update status -> running
            5. Run pipeline in executor
            6. Upload outputs to SeaweedFS
            7. Update status -> finished / failed
            8. Cleanup temp dir
        """
        temp_job_dir = None

        try:
            logger.info(f"Starting HighFold task: {task_id}")

            storage_prefix = job_dir
            logger.info(
                f"Processing task, storage prefix: {storage_prefix}"
            )

            # 1. Prepare temp directory
            storage_config.ensure_temp_dir()
            temp_job_dir = storage_config.temp_dir / task_id
            temp_job_dir.mkdir(parents=True, exist_ok=True)
            temp_input_dir = temp_job_dir / "input"
            temp_input_dir.mkdir(exist_ok=True)

            # 2. Download input.json from SeaweedFS
            remote_config_key = f"{storage_prefix}/input/input.json"
            config_file = temp_input_dir / "input.json"

            try:
                await self.storage.download_file(remote_config_key, config_file)
                logger.info(
                    f"Downloaded config from SeaweedFS: {remote_config_key}"
                )
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except FileNotFoundError:
                logger.warning(
                    "No input.json in SeaweedFS, using DB params only"
                )
                config = {}

            # 3. Merge with database task params (DB takes precedence)
            db_params = await DatabaseManager.get_task_params(task_id)
            if db_params:
                logger.info(f"Got task params from DB for {task_id}")
                # Map DB column names to config keys
                param_mapping = {
                    "core_sequence": "core_sequence",
                    "span_len": "span_len",
                    "num_sample": "num_sample",
                    "temperature": "temperature",
                    "top_p": "top_p",
                    "seed": "seed",
                    "model_type": "model_type",
                    "msa_mode": "msa_mode",
                    "disulfide_bond_pairs": "disulfide_bond_pairs",
                    "num_models": "num_models",
                    "num_recycle": "num_recycle",
                    "use_templates": "use_templates",
                    "amber": "amber",
                    "num_relax": "num_relax",
                    "skip_generate": "skip_generate",
                    "skip_predict": "skip_predict",
                    "skip_evaluate": "skip_evaluate",
                }
                for db_key, config_key in param_mapping.items():
                    val = db_params.get(db_key)
                    if val is not None:
                        config[config_key] = val

            # Apply defaults from settings
            config.setdefault("checkpoint", self.settings.C2C_CHECKPOINT_PATH)
            config.setdefault("colabfold_bin", self.settings.COLABFOLD_BIN)
            config.setdefault("model_type", self.settings.DEFAULT_MODEL_TYPE)
            config.setdefault("msa_mode", self.settings.DEFAULT_MSA_MODE)
            config.setdefault("num_models", self.settings.DEFAULT_NUM_MODELS)
            config.setdefault("span_len", self.settings.DEFAULT_SPAN_LEN)
            config.setdefault("num_sample", self.settings.DEFAULT_NUM_SAMPLE)
            config.setdefault("temperature", self.settings.DEFAULT_TEMPERATURE)
            config.setdefault("top_p", self.settings.DEFAULT_TOP_P)
            config.setdefault("seed", self.settings.DEFAULT_SEED)

            logger.info(f"Final task configuration: {config}")

            # Download existing FASTA if skip_generate
            if config.get("skip_generate"):
                remote_fasta_key = f"{storage_prefix}/input/predict.fasta"
                local_fasta = temp_input_dir / "predict.fasta"
                try:
                    await self.storage.download_file(
                        remote_fasta_key, local_fasta
                    )
                    config["fasta_input_path"] = str(local_fasta)
                    logger.info("Downloaded user FASTA from SeaweedFS")
                except FileNotFoundError:
                    logger.warning(
                        "skip_generate is True but no FASTA found in storage"
                    )

            # 4. Update status -> running
            await DatabaseManager.update_task_status(
                connection, task_id, "running"
            )

            # 5. Run pipeline in thread executor
            logger.info(f"Task {task_id}: launching pipeline")
            loop = asyncio.get_event_loop()
            pipeline_result = await loop.run_in_executor(
                None,
                run_highfold_pipeline,
                config,
                temp_job_dir,
            )

            # 6. Upload all output files to SeaweedFS
            output_dir = temp_job_dir / "output"
            if output_dir.exists():
                logger.info("Uploading task results to SeaweedFS...")
                for result_file in output_dir.rglob("*"):
                    if result_file.is_file():
                        relative_path = result_file.relative_to(output_dir)
                        remote_key = (
                            f"{storage_prefix}/output/{relative_path}"
                        )
                        await self.storage.upload_file(result_file, remote_key)
                        logger.info(f"Uploaded: {remote_key}")

            # 7. Update status -> finished
            await DatabaseManager.update_task_status(
                connection, task_id, "finished"
            )
            logger.info(f"Task {task_id} completed successfully")

        except Exception as e:
            logger.error(f"Task {task_id} failed: {str(e)}")
            try:
                await DatabaseManager.update_task_status(
                    connection, task_id, "failed"
                )
            except Exception as db_error:
                logger.error(f"Failed to update task status: {db_error}")
            raise
        finally:
            # 8. Cleanup
            if temp_job_dir and temp_job_dir.exists():
                try:
                    shutil.rmtree(temp_job_dir, ignore_errors=True)
                    logger.info(
                        f"Cleaned up temporary directory: {temp_job_dir}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to clean up temporary directory: {e}"
                    )

    async def query_and_process_tasks(self) -> None:
        """Poll the database for pending tasks and process them."""
        try:
            tasks = await DatabaseManager.get_pending_highfold_tasks()

            if tasks:
                logger.info(f"Found {len(tasks)} pending highfold_c2c tasks")

                connection = await get_db_connection()
                if not connection:
                    logger.error("Failed to get database connection")
                    return

                try:
                    for task in tasks:
                        task_id, user_id, task_type, job_dir, status = task
                        logger.info(
                            f"Processing task: ID={task_id}, "
                            f"user={user_id}, type={task_type}"
                        )
                        try:
                            await self.process_highfold_task(
                                task_id, job_dir, connection
                            )
                        except Exception as e:
                            logger.error(
                                f"Error processing task {task_id}: {e}"
                            )
                            continue
                finally:
                    connection.close()
            else:
                logger.debug("No pending highfold_c2c tasks found")

        except Exception as e:
            logger.error(f"Error querying tasks: {e}")


async def background_task_runner() -> None:
    """Background task runner — polls database for pending tasks.

    Runs as an ``asyncio.Task`` started during FastAPI lifespan.
    Default interval: 180 seconds (configurable via TASK_QUERY_INTERVAL).
    """
    settings = get_settings()
    interval = settings.TASK_QUERY_INTERVAL
    processor = HighFoldTaskProcessor()
    logger.info(
        "HighFold background task started, polling every %d seconds", interval
    )

    while True:
        try:
            await processor.query_and_process_tasks()
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Background task runner cancelled")
            break
        except Exception as e:
            logger.error(f"Background task error: {e}")
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(background_task_runner())
