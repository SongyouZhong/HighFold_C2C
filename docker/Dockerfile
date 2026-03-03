# ============================================================
# HighFold-C2C Dockerfile
# ============================================================
# Multi-environment image:
#   - Conda env (highfold_c2c): PyTorch + Transformers + FastAPI
#   - LocalColabFold (pixi): JAX + AlphaFold2 (installed separately)
#
# Stage 2 (structure prediction) runs as a subprocess via colabfold_batch,
# preserving GPU memory isolation between PyTorch and JAX.

FROM condaforge/mambaforge:latest AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Conda environment ───────────────────────────────────────
COPY environment.yml .
RUN mamba env create -f environment.yml && mamba clean -afy

# ── Copy project sources ────────────────────────────────────
COPY pyproject.toml .
COPY src/ src/
COPY c2c/ c2c/
COPY scripts/ scripts/
COPY utils/ utils/
COPY alphafold/ alphafold/
COPY colabfold/ colabfold/
COPY checkpoints/ checkpoints/

# Install the package (editable)
RUN mamba run --no-capture-output -n highfold_c2c pip install -e .

# ── Runtime ──────────────────────────────────────────────────
# Create necessary directories
RUN mkdir -p /tmp/highfold_c2c/logs /tmp/highfold_c2c/resource

EXPOSE 8003

ENTRYPOINT ["mamba", "run", "--no-capture-output", "-n", "highfold_c2c"]
CMD ["uvicorn", "highfold_c2c.app:app", "--host", "0.0.0.0", "--port", "8003"]
