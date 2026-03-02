# HighFold-C2C: Cyclic Peptide Design and Structure Prediction

HighFold-C2C is a unified pipeline that combines **C2C** (cyclic peptide sequence generation using a T5 model) with **HighFold** (cyclic peptide structure prediction using CycPOEM-enhanced AlphaFold2).

## Features

- **C2C Sequence Generation**: Given a core peptide sequence, generate diverse cyclic peptide candidates using a trained T5 model
- **HighFold Structure Prediction**: Predict 3D structures of cyclic peptides with head-to-tail and disulfide bridge constraints via CycPOEM (Cyclic Position Offset Encoding Matrix)
- **Unified Pipeline**: One command to run the full workflow — from sequence design to structure prediction to physicochemical evaluation
- **Backward Compatible**: The original `colabfold_batch` CLI workflow is fully preserved

## Project Structure

```
HighFold_C2C/
├── alphafold/          # AlphaFold core with CycPOEM modifications
├── colabfold/          # ColabFold with CycPOEM computation + --disulfide-bond-pairs
├── utils/              # CycPOEM construction, disulfide bridge combinations, evaluation
├── c2c/                # C2C T5 model for cyclic peptide sequence generation
│   ├── model.py        # T5 model definition, CharTokenizer, model loading
│   ├── generate.py     # Sequence generation (greedy + sampling)
│   ├── evaluate.py     # Physicochemical properties + pLDDT scoring
│   └── config.py       # Default configuration constants
├── scripts/            # User entry points
│   ├── run_pipeline.py       # Full 3-stage pipeline
│   └── run_predict_only.py   # Structure prediction only (backward compatible)
├── checkpoints/        # Model weights directory (c2c_model.pt)
└── HighFold_data/      # Datasets
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
SITE_PACKAGES="path/to/localcolabfold/.pixi/envs/default/lib/python3.10/site-packages"
cp -r HighFold_C2C/alphafold/* "$SITE_PACKAGES/alphafold/"
cp -r HighFold_C2C/colabfold/* "$SITE_PACKAGES/colabfold/"
```

### Step 3: Install C2C environment

```bash
cd HighFold_C2C
conda env create -f environment.yml
conda activate highfold_c2c
```

### Step 4: Download C2C model weights

Place the `c2c_model.pt` file into the `checkpoints/` directory:

```bash
# Download c2c_model.pt (obtain from the project maintainers)
cp /path/to/c2c_model.pt checkpoints/
```

### Step 5: Ensure `colabfold_batch` is on PATH

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
    --disulfide-bond-pairs 1 5 \
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
    --disulfide-bond-pairs 2 5
```

Or directly use `colabfold_batch`:

```bash
colabfold_batch --model-type alphafold2 --msa-mode single_sequence \
    --disulfide-bond-pairs 2 5 input.fasta output/
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
| `--model-type` | `alphafold2` | AlphaFold model type |
| `--msa-mode` | `single_sequence` | MSA mode |
| `--disulfide-bond-pairs` | [] | Disulfide bond positions (flat list) |
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

## Sequence Constraints

- Total cyclic peptide length should be ≤ 20 amino acids (training data range)
- Core length should be ≥ 30% of total length
- Example: core=3 aa + span=7 aa = 10 aa total (valid)
- Counter-example: core=1 aa + span=10 aa = 11 aa (core ratio 9%, too low)

## Citation

If you use HighFold, please cite:

> HighFold: accurately predicting structures of cyclic peptides and complexes with head-to-tail and disulfide bridge constraints

## License

See [LICENSE](LICENSE) for details.
