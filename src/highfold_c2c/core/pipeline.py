"""
HighFold-C2C Pipeline

Wraps the three-stage pipeline (C2C generation → HighFold prediction → Evaluation)
as a callable function for the task processing layer.

This module is the synchronous, CPU/GPU-bound workhorse — it is invoked inside a
``ThreadPoolExecutor`` by the task processor to avoid blocking the async event loop.
"""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse_disulfide_pairs(raw: Optional[str]) -> List[Tuple[int, int]]:
    """Parse disulfide bond pairs from ``'A,B:C,D'`` format."""
    if not raw:
        return []
    pairs: List[Tuple[int, int]] = []
    for pair_str in raw.split(":"):
        parts = pair_str.strip().split(",")
        if len(parts) == 2:
            pairs.append((int(parts[0]), int(parts[1])))
    return pairs


def _add_cyclic_conect(pdb_path: Path) -> None:
    """Add CONECT records for the head-to-tail cyclic bond to a PDB file.

    AlphaFold's ``to_pdb()`` never writes CONECT records, so the cyclic
    N-C terminal bond is invisible to molecular viewers.  This function
    finds the backbone N atom of the first residue and the backbone C atom
    of the last residue in each chain and appends CONECT records.
    """
    text = pdb_path.read_text()
    lines = text.split("\n")

    # Collect per-chain first-N and last-C atom serial numbers
    # {chain_id: {"first_n": (res_num, serial), "last_c": (res_num, serial)}}
    chains: Dict[str, Dict[str, Tuple[int, int]]] = {}
    for line in lines:
        if not line.startswith("ATOM"):
            continue
        atom_name = line[12:16].strip()
        chain_id = line[21]
        res_num = int(line[22:26].strip())
        serial = int(line[6:11].strip())

        if chain_id not in chains:
            chains[chain_id] = {}
        entry = chains[chain_id]

        if atom_name == "N":
            if "first_n" not in entry or res_num < entry["first_n"][0]:
                entry["first_n"] = (res_num, serial)
        if atom_name == "C":
            if "last_c" not in entry or res_num > entry["last_c"][0]:
                entry["last_c"] = (res_num, serial)

    conect_lines: List[str] = []
    for chain_id, entry in chains.items():
        if "first_n" in entry and "last_c" in entry:
            n_serial = entry["first_n"][1]
            c_serial = entry["last_c"][1]
            conect_lines.append(f"CONECT{c_serial:>5}{n_serial:>5}")
            conect_lines.append(f"CONECT{n_serial:>5}{c_serial:>5}")

    if not conect_lines:
        return

    # Insert CONECT records before the END line
    out_lines: List[str] = []
    inserted = False
    for line in lines:
        stripped = line.strip()
        if stripped == "END" and not inserted:
            for cl in conect_lines:
                out_lines.append(cl.ljust(80))
            inserted = True
        out_lines.append(line)

    if not inserted:
        # No END line found — just append
        for cl in conect_lines:
            out_lines.append(cl.ljust(80))

    pdb_path.write_text("\n".join(out_lines))


def _cyclize_pdb_files(output_dir: Path) -> int:
    """Add cyclic CONECT records to all PDB files in *output_dir*.

    Returns the number of PDB files processed.
    """
    count = 0
    for pdb_file in sorted(output_dir.glob("*.pdb")):
        try:
            _add_cyclic_conect(pdb_file)
            count += 1
        except Exception as exc:
            logger.warning("Failed to add cyclic CONECT to %s: %s", pdb_file.name, exc)
    return count


def _build_colabfold_cmd(
    colabfold_bin: str,
    fasta_path: Path,
    output_dir: Path,
    model_type: str,
    msa_mode: str,
    num_models: int,
    num_recycle: Optional[int],
    use_templates: bool,
    amber: bool,
    num_relax: int,
    disulfide_bond_pairs: List[Tuple[int, int]],
) -> List[str]:
    """Build the ``colabfold_batch`` CLI command."""
    cmd = [colabfold_bin]
    cmd += ["--model-type", model_type]
    cmd += ["--msa-mode", msa_mode]
    cmd += ["--num-models", str(num_models)]
    if num_recycle is not None:
        cmd += ["--num-recycle", str(num_recycle)]
    if use_templates:
        cmd += ["--templates"]
    if amber:
        cmd += ["--amber"]
        if num_relax > 0:
            cmd += ["--num-relax", str(num_relax)]
    if disulfide_bond_pairs:
        pairs_str = ":".join(f"{a},{b}" for a, b in disulfide_bond_pairs)
        cmd += ["--disulfide-bond-pairs", pairs_str]
    cmd += [str(fasta_path), str(output_dir)]
    return cmd


# ── Main pipeline entry point ────────────────────────────────────────────────


def run_highfold_pipeline(config: Dict[str, Any], work_dir: Path) -> Dict[str, Any]:
    """Run the full 3-stage HighFold-C2C pipeline.

    This function is **synchronous** and designed to run inside a
    ``ThreadPoolExecutor`` / ``run_in_executor`` call.

    Parameters
    ----------
    config : dict
        Task configuration. Expected keys::

            core_sequence : str           – core peptide (e.g. "NNN")
            span_len : int                – residues to extend
            num_sample : int              – total candidate sequences
            checkpoint : str              – path to c2c_model.pt
            temperature : float
            top_p : float
            seed : int
            model_type : str              – e.g. "alphafold2"
            msa_mode : str                – e.g. "single_sequence"
            disulfide_bond_pairs : str|None  – "2,5:3,7"
            num_models : int
            num_recycle : int|None
            use_templates : bool
            amber : bool
            num_relax : int
            colabfold_bin : str
            skip_generate : bool
            skip_predict : bool
            skip_evaluate : bool
            fasta_input_path : str|None   – path to existing FASTA (when skip_generate)

    work_dir : Path
        Temporary working directory for this task.

    Returns
    -------
    dict
        Result summary with keys: ``num_sequences``, ``csv_path``, ``plddt_summary``,
        ``output_files``.
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    output_dir = work_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    fasta_path = output_dir / "predict.fasta"

    skip_generate = config.get("skip_generate", False)
    skip_predict = config.get("skip_predict", False)
    skip_evaluate = config.get("skip_evaluate", False)

    result: Dict[str, Any] = {
        "num_sequences": 0,
        "csv_path": None,
        "plddt_summary": {},
        "output_files": [],
    }

    # ================================================================
    # Stage 1: C2C Sequence Generation
    # ================================================================
    if not skip_generate:
        core = config.get("core_sequence", "")
        if not core:
            raise ValueError("core_sequence is required for sequence generation")

        logger.info(
            "Stage 1/3: Generating sequences — core=%s, span_len=%d",
            core,
            config.get("span_len", 5),
        )
        from c2c.generate import sample_c2c_dual, write_fasta as c2c_write_fasta

        gen_result = sample_c2c_dual(
            core=core,
            n_greedy=1,
            n_sampled=config.get("num_sample", 20) - 1,
            checkpoint_path=config.get("checkpoint", "checkpoints/c2c_model.pt"),
            span_len=config.get("span_len", 5),
            temperature=config.get("temperature", 1.0),
            top_p=config.get("top_p", 0.9),
            seed=config.get("seed", 42),
        )
        all_seqs = gen_result["greedy_assembled"] + gen_result["sampled_assembled"]
        c2c_write_fasta(all_seqs, str(fasta_path))
        result["num_sequences"] = len(all_seqs)
        logger.info("Stage 1 complete: %d sequences -> %s", len(all_seqs), fasta_path)
    else:
        # Use existing FASTA
        existing_fasta = config.get("fasta_input_path")
        if existing_fasta and Path(existing_fasta).exists():
            shutil.copy2(existing_fasta, fasta_path)
            logger.info("Stage 1 skipped — using existing FASTA: %s", existing_fasta)
        elif fasta_path.exists():
            logger.info("Stage 1 skipped — FASTA already at: %s", fasta_path)
        else:
            raise FileNotFoundError(
                "skip_generate is True but no FASTA file was found or provided"
            )

    # ================================================================
    # Stage 2: HighFold Structure Prediction (subprocess)
    # ================================================================
    if not skip_predict:
        # Free PyTorch GPU memory before launching JAX-based colabfold
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("Released PyTorch GPU memory before Stage 2")
        except ImportError:
            pass

        colabfold_bin = config.get("colabfold_bin", "colabfold_batch")
        if shutil.which(colabfold_bin) is None:
            # Also check if it's an absolute path that exists
            if not Path(colabfold_bin).is_file():
                raise FileNotFoundError(
                    f"'{colabfold_bin}' not found on PATH or as absolute path. "
                    "Ensure the Docker image was built with ColabFold support "
                    "(see colabfold_environment.yml and scripts/colabfold_batch)."
                )

        disulfide_pairs = _parse_disulfide_pairs(
            config.get("disulfide_bond_pairs")
        )

        cmd = _build_colabfold_cmd(
            colabfold_bin=colabfold_bin,
            fasta_path=fasta_path,
            output_dir=output_dir,
            model_type=config.get("model_type", "alphafold2"),
            msa_mode=config.get("msa_mode", "single_sequence"),
            num_models=config.get("num_models", 5),
            num_recycle=config.get("num_recycle"),
            use_templates=config.get("use_templates", False),
            amber=config.get("amber", False),
            num_relax=config.get("num_relax", 0),
            disulfide_bond_pairs=disulfide_pairs,
        )

        logger.info("Stage 2/3: HighFold prediction — %s", " ".join(cmd))
        subprocess.run(cmd, check=True)
        logger.info("Stage 2 complete — results in %s", output_dir)

        # Post-process: add cyclic bond CONECT records to PDB files
        n_cyclized = _cyclize_pdb_files(output_dir)
        logger.info(
            "Stage 2 post-processing: added cyclic CONECT records to %d PDB files",
            n_cyclized,
        )
    else:
        logger.info("Stage 2 skipped")

    # ================================================================
    # Stage 3: Evaluation & Report
    # ================================================================
    if not skip_evaluate:
        logger.info("Stage 3/3: Evaluating properties & pLDDT scores")
        from c2c.evaluate import (
            read_fasta_sequences,
            collect_plddt_scores,
            generate_report,
        )

        seq_list = read_fasta_sequences(str(fasta_path))
        result["num_sequences"] = len(seq_list)

        if not skip_predict:
            score_dict = collect_plddt_scores(str(output_dir), seq_list)
        else:
            score_dict = {seq: float("nan") for seq in seq_list}

        csv_path = output_dir / "output.csv"
        df = generate_report(seq_list, score_dict, str(csv_path))
        result["csv_path"] = str(csv_path)

        # Build pLDDT summary
        import numpy as np

        valid_scores = [v for v in score_dict.values() if not np.isnan(v)]
        if valid_scores:
            result["plddt_summary"] = {
                "mean": float(np.mean(valid_scores)),
                "min": float(np.min(valid_scores)),
                "max": float(np.max(valid_scores)),
                "count": len(valid_scores),
            }

        logger.info(
            "Stage 3 complete — %d sequences evaluated, CSV at %s",
            len(df),
            csv_path,
        )
    else:
        logger.info("Stage 3 skipped")

    # Collect all output files
    result["output_files"] = [
        str(f.relative_to(output_dir)) for f in output_dir.rglob("*") if f.is_file()
    ]

    return result
