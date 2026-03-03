"""
HighFold-C2C FastAPI Application

Main application module for the cyclic peptide design & structure prediction service.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from highfold_c2c.config.logging_config import setup_logging, get_log_file_path
from highfold_c2c.config import storage as storage_config
from highfold_c2c.services.storage import get_storage
from highfold_c2c.core.async_processor import AsyncTaskProcessor
from highfold_c2c.core.task_processor import background_task_runner

# Configure logging
log_file = get_log_file_path()
setup_logging(level="INFO", log_file=log_file)
logger = logging.getLogger(__name__)

# Global state
async_processor: Optional[AsyncTaskProcessor] = None
background_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    global async_processor, background_task

    # === Startup ===
    logger.info("Starting HighFold-C2C API...")

    logger.info("Initializing async task processor...")
    async_processor = AsyncTaskProcessor()

    logger.info("Starting background task runner...")
    background_task = asyncio.create_task(background_task_runner())

    logger.info("HighFold-C2C API startup complete")
    yield

    # === Shutdown ===
    logger.info("Shutting down HighFold-C2C API...")

    if background_task:
        logger.info("Cancelling background task...")
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            logger.info("Background task cancelled successfully")

    if async_processor:
        await async_processor.shutdown()

    logger.info("HighFold-C2C API shutdown complete")


# Create FastAPI application
app = FastAPI(
    lifespan=lifespan,
    title="HighFold-C2C API",
    description=(
        "Cyclic peptide design and structure prediction service. "
        "C2C sequence generation + HighFold/AlphaFold2 with CycPOEM + "
        "physicochemical evaluation. "
        "Tasks are managed via a shared PostgreSQL tasks table."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Exception Handlers
# =============================================================================


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    """Handle validation errors."""
    logger.error(f"Validation error: {exc}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    logger.error(f"HTTP error: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# =============================================================================
# Basic Routes
# =============================================================================


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "message": "HighFold-C2C API",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "active_tasks": (
            async_processor.get_task_count() if async_processor else 0
        ),
    }


@app.get("/status")
async def get_status():
    """Get service status."""
    if not async_processor:
        return {"status": "initializing"}

    return {
        "status": "running",
        "active_tasks": async_processor.get_task_count(),
        "active_task_ids": async_processor.get_active_tasks(),
    }


# =============================================================================
# Result Retrieval Routes
# =============================================================================


@app.get("/results/{task_id}")
async def get_task_results(task_id: str):
    """Retrieve results summary for a completed task.

    Reads the output CSV and pLDDT scores from SeaweedFS.
    """
    try:
        storage = get_storage()

        # Try to download the output CSV
        csv_key = f"jobs/highfold_c2c/{task_id}/output/output.csv"
        try:
            csv_bytes = await storage.download_bytes(csv_key)
            csv_content = csv_bytes.decode("utf-8")
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Results not found for task: {task_id}",
            )

        # Parse CSV to return as JSON
        import csv
        import io

        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)

        return {
            "task_id": task_id,
            "num_sequences": len(rows),
            "results": rows,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Result retrieval error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve results: {str(e)}",
        )


@app.get("/results/{task_id}/csv")
async def get_task_csv(task_id: str):
    """Download the output CSV file for a task."""
    from fastapi.responses import Response

    try:
        storage = get_storage()
        csv_key = f"jobs/highfold_c2c/{task_id}/output/output.csv"

        try:
            csv_bytes = await storage.download_bytes(csv_key)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"CSV not found for task: {task_id}",
            )

        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=highfold_{task_id}_output.csv"
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CSV download error: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to download CSV: {str(e)}"
        )


@app.get("/structures/{task_id}/{filename}")
async def get_structure_file(task_id: str, filename: str):
    """Download a PDB structure file for a task.

    Returns a presigned URL or proxies the file from SeaweedFS.
    """
    try:
        storage = get_storage()

        # Structures live under output/ with their original names
        structure_key = f"jobs/highfold_c2c/{task_id}/output/{filename}"

        if not await storage.file_exists(structure_key):
            raise HTTPException(
                status_code=404,
                detail=f"Structure file not found: {filename}",
            )

        url = await storage.get_presigned_url(structure_key)
        return {"task_id": task_id, "filename": filename, "download_url": url}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Structure file error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve structure: {str(e)}",
        )


@app.get("/sequences/{task_id}")
async def get_generated_sequences(task_id: str):
    """Retrieve the generated FASTA sequences for a task."""
    try:
        storage = get_storage()
        fasta_key = f"jobs/highfold_c2c/{task_id}/output/predict.fasta"

        try:
            fasta_bytes = await storage.download_bytes(fasta_key)
            fasta_content = fasta_bytes.decode("utf-8")
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"FASTA not found for task: {task_id}",
            )

        # Parse FASTA into list of {name, sequence}
        sequences = []
        current_name = None
        current_seq = []
        for line in fasta_content.strip().split("\n"):
            if line.startswith(">"):
                if current_name is not None:
                    sequences.append(
                        {"name": current_name, "sequence": "".join(current_seq)}
                    )
                current_name = line[1:].strip()
                current_seq = []
            else:
                current_seq.append(line.strip())
        if current_name is not None:
            sequences.append(
                {"name": current_name, "sequence": "".join(current_seq)}
            )

        return {
            "task_id": task_id,
            "num_sequences": len(sequences),
            "sequences": sequences,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sequence retrieval error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve sequences: {str(e)}",
        )


# =============================================================================
# Server Runner
# =============================================================================


def run_server(
    host: str = "0.0.0.0", port: int = 8003, reload: bool = False
):
    """Run the uvicorn server programmatically."""
    import uvicorn

    uvicorn.run(
        "highfold_c2c.app:app", host=host, port=port, reload=reload
    )


if __name__ == "__main__":
    run_server()
