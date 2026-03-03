# HighFold-C2C: Cyclic Peptide Design and Structure Prediction

HighFold-C2C is a unified pipeline that combines **C2C** (cyclic peptide sequence generation using a T5 model) with **HighFold** (cyclic peptide structure prediction using CycPOEM-enhanced AlphaFold2).

It can run as a **standalone CLI tool** or be deployed as a **microservice** with FastAPI, PostgreSQL task tracking, and SeaweedFS object storage — following the same architecture as the AstraMolecula platform.

## Features

- **C2C Sequence Generation**: Given a core peptide sequence, generate diverse cyclic peptide candidates using a trained T5 model
- **HighFold Structure Prediction**: Predict 3D structures of cyclic peptides with head-to-tail and disulfide bridge constraints via CycPOEM (Cyclic Position Offset Encoding Matrix)
- **New ColabFold v1.5.5 Support**: Adapted to the latest ColabFold with modular architecture (`input.py`, `relax.py`, `extra_ptm.py`), `deepfold_v1` model support, and improved MSA pairing. See [docs/colabfold-migration.md](docs/colabfold-migration.md) for details.
- **Unified Pipeline**: One command to run the full workflow — from sequence design to structure prediction to physicochemical evaluation
- **Microservice Mode**: FastAPI server (port 8003) with background task polling, multi-worker support, and RESTful result retrieval
- **Object Storage**: SeaweedFS integration for centralized input/output file management
- **Task Tracking**: PostgreSQL-based task queue (shared with AstraMolecula `tasks` table, `task_type='highfold_c2c'`)
- **Docker Ready**: GPU-enabled containerized deployment with Docker Compose; connects to external PostgreSQL and SeaweedFS on the host
- **Backward Compatible**: The original `colabfold_batch` CLI workflow is fully preserved; CycPOEM is only activated when `--disulfide-bond-pairs` is provided

## Project Structure

```
HighFold_C2C/
├── alphafold/              # AlphaFold core with CycPOEM modifications
├── colabfold/              # ColabFold v1.5.5 with CycPOEM computation + --disulfide-bond-pairs
│   ├── cycpoem.py          # CycPOEM algorithm (standalone module)
│   ├── batch.py            # Main entry point (CycPOEM injected)
│   ├── input.py            # Input parsing (new in v1.5.5)
│   └── relax.py            # Structure relaxation (new in v1.5.5)
├── utils/                  # CycPOEM construction, disulfide bridge combinations, evaluation
├── c2c/                    # C2C T5 model for cyclic peptide sequence generation
│   ├── model.py            # T5 model definition, CharTokenizer, model loading
│   ├── generate.py         # Sequence generation (greedy + sampling)
│   ├── evaluate.py         # Physicochemical properties + pLDDT scoring
│   └── config.py           # Default configuration constants
├── scripts/                # CLI entry points (original usage)
│   ├── run_pipeline.py     # Full 3-stage pipeline
│   └── run_predict_only.py # Structure prediction only
├── src/highfold_c2c/       # ★ Microservice layer (new)
│   ├── app.py              # FastAPI application (port 8003)
│   ├── __main__.py         # CLI: python -m highfold_c2c
│   ├── config/             # Settings, storage config, logging
│   ├── database/           # PostgreSQL connection pool & task queries
│   ├── core/               # Pipeline wrapper, task processor, async processor
│   └── services/storage/   # SeaweedFS async client
├── database/               # SQL migration scripts
│   └── init_highfold_tables.sql
├── docker/                 # Docker deployment files
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   └── docker-manage.sh
├── tests/                  # Unit tests (pytest)
├── checkpoints/            # Model weights directory (c2c_model.pt)
└── HighFold_data/          # Datasets
```

## Installation

### Prerequisites

- Linux with NVIDIA GPU (CUDA 12.x)
- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or [Mamba](https://mamba.readthedocs.io/)

### Step 1: Install LocalColabFold

Follow the instructions at [LocalColabFold](https://github.com/YoshitakaMo/localcolabfold):

```bash
# Example for Linux
cd localcolabfold
pixi install && pixi run setup
```

### Step 2: Install HighFold overlay

Copy the modified AlphaFold and ColabFold source files on top of the LocalColabFold installation:

```bash
SITE_PACKAGES="path/to/localcolabfold/.pixi/envs/default/lib/python3.12/site-packages"
cp -r HighFold_C2C/alphafold/* "$SITE_PACKAGES/alphafold/"
cp -r HighFold_C2C/colabfold/* "$SITE_PACKAGES/colabfold/"
```

### Step 3: Install C2C environment

```bash
cd HighFold_C2C
conda env create -f environment.yml
conda activate highfold_c2c
```

### Step 4: Install the package (for microservice mode)

```bash
# Install in development mode
pip install -e ".[dev]"
```

### Step 5: Download C2C model weights

Place the `c2c_model.pt` file into the `checkpoints/` directory:

```bash
# Download c2c_model.pt (obtain from the project maintainers)
cp /path/to/c2c_model.pt checkpoints/
```

### Step 6: Ensure `colabfold_batch` is on PATH

```bash
export PATH="path/to/localcolabfold/.pixi/envs/default/bin:$PATH"
# Verify
which colabfold_batch
```

## Usage

### Full Pipeline (Recommended)

One command to run all three stages — sequence generation, structure prediction, and evaluation:

```bash
conda activate highfold_c2c

python -m scripts.run_pipeline \
    --core NNN \
    --span-len 5 \
    --num-sample 20 \
    --output-dir ./output
```

This will:
1. **Stage 1**: Generate 20 cyclic peptide sequences (1 greedy + 19 sampled) extending the core `NNN` by 5 residues
2. **Stage 2**: Predict 3D structures for all candidates using HighFold/AlphaFold2
3. **Stage 3**: Compute physicochemical properties and pLDDT scores, output `output.csv`

### With Disulfide Bridges

```bash
python -m scripts.run_pipeline \
    --core CNNNC \
    --span-len 5 \
    --num-sample 20 \
    --disulfide-bond-pairs "0,4" \
    --output-dir ./output
```

### Skip Stages

```bash
# Generate sequences only (no structure prediction)
python -m scripts.run_pipeline \
    --core NNN --span-len 5 --skip-predict

# Predict from existing FASTA (skip C2C generation)
python -m scripts.run_pipeline \
    --skip-generate --fasta-input my_sequences.fasta --output-dir ./output
```

### Structure Prediction Only (Original HighFold Usage)

For users who only need structure prediction (backward compatible with HighFold):

```bash
python -m scripts.run_predict_only \
    input.fasta ./output/ \
    --model-type alphafold2 \
    --msa-mode single_sequence \
    --disulfide-bond-pairs "1,4"
```

Or directly use `colabfold_batch`:

```bash
colabfold_batch --model-type alphafold2 --msa-mode single_sequence \
    --disulfide-bond-pairs "1,4" input.fasta output/
```

### Pipeline Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--core` | (required) | Core peptide sequence |
| `--span-len` | 5 | Number of residues to extend |
| `--num-sample` | 20 | Total candidate sequences |
| `--checkpoint` | `checkpoints/c2c_model.pt` | C2C model weights |
| `--temperature` | 1.0 | Sampling temperature |
| `--top-p` | 0.9 | Nucleus sampling threshold |
| `--output-dir` | `./output` | Output directory |
| `--model-type` | `alphafold2` | AlphaFold model type (`alphafold2`, `alphafold2_ptm`, `alphafold2_multimer_v1/v2/v3`, `deepfold_v1`) |
| `--msa-mode` | `single_sequence` | MSA mode |
| `--disulfide-bond-pairs` | None | Disulfide bond positions (format: `"A,B"` or `"A,B:C,D"`, 0-based) |
| `--num-models` | 5 | Number of AlphaFold models |
| `--colabfold-bin` | `colabfold_batch` | Path to colabfold_batch |

## Output Files

After running the full pipeline, `output/` will contain:

| File | Description |
|------|-------------|
| `predict.fasta` | Generated cyclic peptide sequences |
| `pep*_unrelaxed_*.pdb` | Predicted 3D structures |
| `pep*_scores_*.json` | Per-residue pLDDT scores |
| `output.csv` | Summary: sequences, pLDDT, MW, pI, aromaticity, instability, hydrophobicity, hydrophilicity |

## Microservice Mode

### Overview

HighFold-C2C can also run as a background microservice that polls a PostgreSQL task queue and processes jobs automatically. This is designed for integration with the **AstraMolecula** platform.

**Architecture:**
- **FastAPI** server on port 8003 (health check, task status, result retrieval)
- **Background polling** — checks database every 180 seconds for `pending` tasks
- **SeaweedFS** object storage for input/output files
- **Multi-worker** — `ThreadPoolExecutor` supports concurrent task processing

### Quick Start (Service)

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env with your database and SeaweedFS settings

# 2. Start the service
python -m highfold_c2c --host 0.0.0.0 --port 8003

# Or use the entry point
highfold-c2c-server --host 0.0.0.0 --port 8003
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Service info |
| GET | `/health` | Health check |
| GET | `/status` | Service status (active tasks, uptime) |
| GET | `/results/{task_id}` | Get task results (JSON) |
| GET | `/results/{task_id}/csv` | Download output.csv |
| GET | `/structures/{task_id}/{filename}` | Download PDB structure file |
| GET | `/sequences/{task_id}` | Get generated sequences |

### Task Workflow

1. An external system (e.g. AstraMolecula) inserts a row into the `tasks` table with `task_type='highfold_c2c'` and `status='pending'`, along with parameters in the `highfold_task_params` table
2. The background worker picks up the task, downloads input files from SeaweedFS
3. Runs the 3-stage pipeline (C2C → ColabFold → Evaluate)
4. Uploads results to SeaweedFS and updates task status to `completed` or `failed`

### Database Tables

The service uses the shared AstraMolecula `tasks` table plus a dedicated parameters table:

```sql
-- Parameters table (see database/init_highfold_tables.sql)
CREATE TABLE highfold_task_params (
    task_id       INTEGER PRIMARY KEY REFERENCES tasks(id),
    core_sequence VARCHAR(100) NOT NULL,
    span_len      INTEGER DEFAULT 5,
    num_sample    INTEGER DEFAULT 20,
    temperature   FLOAT DEFAULT 1.0,
    top_p         FLOAT DEFAULT 0.9,
    model_type    VARCHAR(50) DEFAULT 'alphafold2',
    disulfide_bond_pairs TEXT,
    ...
);
```

### Docker Deployment

> **Note:** The Docker setup deploys **only the HighFold-C2C application container**.
> It connects to **external services already running on the host machine**:
> - **PostgreSQL** (default: host port 5432)
> - **SeaweedFS** (default: host port 8888)
>
> Make sure these services are running before starting the container.

#### Prerequisites

1. Docker with [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) for GPU support
2. PostgreSQL running on the host (shared with AstraMolecula platform)
3. SeaweedFS running on the host (shared with AstraMolecula platform)
4. Place `c2c_model.pt` in `checkpoints/` directory

#### Quick Start

```bash
cd docker

# 1. Configure environment (use host.docker.internal for Docker)
cp ../.env.example ../.env
# Edit ../.env if needed (defaults connect to host services)

# 2. Initialize database tables (first time only)
./docker-manage.sh init-db

# 3. Build the image
./docker-manage.sh build

# 4. Start the app
./docker-manage.sh up

# View logs
./docker-manage.sh logs --follow

# Development mode (hot reload + source mounting)
./docker-manage.sh up --dev

# Stop
./docker-manage.sh down
```

#### Manual Docker Compose Commands

```bash
cd docker

# Build
docker compose --env-file ../.env build app

# Start
docker compose --env-file ../.env up -d app

# Logs
docker compose --env-file ../.env logs -f

# Stop
docker compose --env-file ../.env down
```

### Environment Variables

See [.env.example](.env.example) for all configuration options. Key variables:

| Variable | Default (Docker) | Description |
|----------|------------------|-------------|
| `DB_HOST` | `host.docker.internal` | PostgreSQL host (use `127.0.0.1` for non-Docker) |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `mydatabase` | Database name |
| `SEAWEED_FILER_ENDPOINT` | `http://host.docker.internal:8888` | SeaweedFS Filer URL (use `http://localhost:8888` for non-Docker) |
| `SEAWEED_BUCKET` | `astramolecula` | Storage bucket name |
| `TASK_QUERY_INTERVAL` | `180` | Polling interval (seconds) |
| `MAX_CONCURRENT_TASKS` | `2` | Max parallel tasks |
| `C2C_CHECKPOINT_PATH` | `checkpoints/c2c_model.pt` | Model weights path |
| `COLABFOLD_BIN` | `colabfold_batch` | colabfold_batch executable |

## Sequence Constraints

- Total cyclic peptide length should be ≤ 20 amino acids (training data range)
- Core length should be ≥ 30% of total length
- Example: core=3 aa + span=7 aa = 10 aa total (valid)
- Counter-example: core=1 aa + span=10 aa = 11 aa (core ratio 9%, too low)

## Citation

If you use HighFold, please cite:

> HighFold: accurately predicting structures of cyclic peptides and complexes with head-to-tail and disulfide bridge constraints

## Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
python -m pytest tests/ -v

# Run specific test modules
python -m pytest tests/test_pipeline.py -v
python -m pytest tests/test_storage.py -v
python -m pytest tests/test_task_processor.py -v
```

## Documentation

- [ColabFold v1.5.5 Migration Details](docs/colabfold-migration.md) — Detailed description of all changes made to adapt CycPOEM to the new ColabFold version
- [Merge Plan](merge-plan.md) — Original C2C + HighFold merge design document
- [.env.example](.env.example) — All environment variables for microservice configuration
- [database/init_highfold_tables.sql](database/init_highfold_tables.sql) — Database migration script
- [中文文档](README_CN.md) — Chinese documentation

## License

See [LICENSE](LICENSE) for details.
