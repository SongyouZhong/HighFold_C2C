"""
C2C-HighFold Unified Pipeline
==============================

Three-stage pipeline for cyclic peptide design and structure prediction:

  Stage 1: C2C sequence generation (PyTorch T5 model)
  Stage 2: HighFold structure prediction (subprocess → colabfold_batch CLI)
  Stage 3: Physicochemical property evaluation + pLDDT scoring → CSV report

Usage::

    python -m scripts.run_pipeline \\
        --core NNN --span-len 5 --num-sample 20 \\
        --checkpoint checkpoints/c2c_model.pt \\
        --output-dir ./output \\
        [--model-type alphafold2] \\
        [--msa-mode single_sequence] \\
        [--disulfide-bond-pairs "2,5:3,7"] \\
        [--colabfold-bin colabfold_batch]
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from c2c.generate import sample_c2c_dual, write_fasta
from c2c.evaluate import read_fasta_sequences, collect_plddt_scores, generate_report
from c2c.config import (
    DEFAULT_CHECKPOINT_PATH,
    DEFAULT_SPAN_LEN,
    DEFAULT_NUM_SAMPLE,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_SEED,
)


def _build_colabfold_cmd(
    colabfold_bin: str,
    fasta_path: Path,
    output_dir: Path,
    model_type: str,
    msa_mode: str,
    num_models: int,
    num_recycle: int | None,
    use_templates: bool,
    amber: bool,
    num_relax: int,
    disulfide_bond_pairs: list[tuple[int, int]],
) -> list[str]:
    """Build the colabfold_batch CLI command."""
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


def main():
    parser = argparse.ArgumentParser(
        description="C2C-HighFold: Cyclic peptide design and structure prediction pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Full pipeline\n"
            "  python -m scripts.run_pipeline --core NNN --span-len 5 --num-sample 20\n"
            "\n"
            "  # Skip generation, predict from existing FASTA\n"
            "  python -m scripts.run_pipeline --skip-generate --fasta-input my.fasta --output-dir out\n"
            "\n"
            "  # Generate only, no structure prediction\n"
            "  python -m scripts.run_pipeline --core NNN --span-len 5 --skip-predict\n"
        ),
    )

    # --- C2C sequence generation ---
    gen_group = parser.add_argument_group("C2C sequence generation")
    gen_group.add_argument("--core", type=str, help="Core peptide sequence (e.g. NNN)")
    gen_group.add_argument(
        "--span-len", type=int, default=DEFAULT_SPAN_LEN,
        help=f"Number of residues to extend (default: {DEFAULT_SPAN_LEN})",
    )
    gen_group.add_argument(
        "--num-sample", type=int, default=DEFAULT_NUM_SAMPLE,
        help=f"Total number of candidate sequences (default: {DEFAULT_NUM_SAMPLE})",
    )
    gen_group.add_argument(
        "--checkpoint", type=str, default=DEFAULT_CHECKPOINT_PATH,
        help=f"Path to c2c_model.pt (default: {DEFAULT_CHECKPOINT_PATH})",
    )
    gen_group.add_argument(
        "--temperature", type=float, default=DEFAULT_TEMPERATURE,
        help=f"Sampling temperature (default: {DEFAULT_TEMPERATURE})",
    )
    gen_group.add_argument(
        "--top-p", type=float, default=DEFAULT_TOP_P,
        help=f"Nucleus sampling threshold (default: {DEFAULT_TOP_P})",
    )
    gen_group.add_argument(
        "--seed", type=int, default=DEFAULT_SEED,
        help=f"Random seed (default: {DEFAULT_SEED})",
    )

    # --- HighFold structure prediction ---
    pred_group = parser.add_argument_group("HighFold structure prediction")
    pred_group.add_argument(
        "--output-dir", type=str, default="./output",
        help="Output directory for all results (default: ./output)",
    )
    pred_group.add_argument(
        "--model-type", type=str, default="alphafold2",
        choices=["alphafold2", "alphafold2_ptm",
                 "alphafold2_multimer_v1", "alphafold2_multimer_v2", "alphafold2_multimer_v3",
                 "deepfold_v1"],
        help="AlphaFold model type (default: alphafold2)",
    )
    pred_group.add_argument(
        "--msa-mode", type=str, default="single_sequence",
        choices=["mmseqs2_uniref_env", "mmseqs2_uniref", "single_sequence"],
        help="MSA mode (default: single_sequence)",
    )
    pred_group.add_argument(
        "--disulfide-bond-pairs", type=str, default=None,
        metavar="PAIRS",
        help="Disulfide bond position pairs (format: 'A,B' or 'A,B:C,D', 0-based, e.g. '2,5:3,7')",
    )
    pred_group.add_argument("--num-models", type=int, default=5, choices=[1, 2, 3, 4, 5])
    pred_group.add_argument("--num-recycle", type=int, default=None)
    pred_group.add_argument("--use-templates", action="store_true")
    pred_group.add_argument("--amber", action="store_true", help="Use AMBER for structure refinement")
    pred_group.add_argument("--num-relax", type=int, default=0, help="Number of top structures to relax")
    pred_group.add_argument(
        "--colabfold-bin", type=str, default="colabfold_batch",
        help="Path to colabfold_batch executable (default: colabfold_batch)",
    )

    # --- Stage control ---
    ctrl_group = parser.add_argument_group("Stage control")
    ctrl_group.add_argument(
        "--skip-generate", action="store_true",
        help="Skip sequence generation (use existing FASTA via --fasta-input)",
    )
    ctrl_group.add_argument(
        "--skip-predict", action="store_true",
        help="Skip structure prediction (only generate sequences)",
    )
    ctrl_group.add_argument(
        "--skip-evaluate", action="store_true",
        help="Skip evaluation stage",
    )
    ctrl_group.add_argument(
        "--fasta-input", type=str,
        help="Path to an existing FASTA file (used with --skip-generate)",
    )

    args = parser.parse_args()

    # --- Validation ---
    if not args.skip_generate and not args.core:
        parser.error("--core is required unless --skip-generate is set")
    if args.skip_generate and not args.fasta_input:
        parser.error("--fasta-input is required when --skip-generate is set")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fasta_path = output_dir / "predict.fasta"

    # Parse disulfide bond pairs from "A,B:C,D" format
    disulfide_bond_pairs: list[tuple[int, int]] = []
    if args.disulfide_bond_pairs is not None:
        for pair_str in args.disulfide_bond_pairs.split(":"):
            parts = pair_str.strip().split(",")
            if len(parts) != 2:
                parser.error(f"Each disulfide pair must be 'A,B', got '{pair_str}'")
            disulfide_bond_pairs.append((int(parts[0]), int(parts[1])))

    # ================================================================
    # Stage 1: C2C Sequence Generation
    # ================================================================
    if not args.skip_generate:
        print(f"[Stage 1/3] Generating cyclic peptide sequences: core={args.core}, span_len={args.span_len}")
        result = sample_c2c_dual(
            core=args.core,
            n_greedy=1,
            n_sampled=args.num_sample - 1,
            checkpoint_path=args.checkpoint,
            span_len=args.span_len,
            temperature=args.temperature,
            top_p=args.top_p,
            seed=args.seed,
        )
        all_seqs = result["greedy_assembled"] + result["sampled_assembled"]
        write_fasta(all_seqs, str(fasta_path))
        print(f"  -> Generated {len(all_seqs)} sequences, saved to {fasta_path}")
    else:
        fasta_path = Path(args.fasta_input)
        if not fasta_path.exists():
            print(f"Error: FASTA file not found: {fasta_path}", file=sys.stderr)
            sys.exit(1)
        print(f"[Stage 1/3] Skipped (using existing FASTA: {fasta_path})")

    # ================================================================
    # Stage 2: HighFold Structure Prediction (subprocess)
    # ================================================================
    if not args.skip_predict:
        # Check that colabfold_batch is available
        if shutil.which(args.colabfold_bin) is None:
            print(
                f"Error: '{args.colabfold_bin}' not found on PATH.\n"
                f"Please install LocalColabFold and add it to PATH, or use --colabfold-bin "
                f"to specify the full path to colabfold_batch.",
                file=sys.stderr,
            )
            sys.exit(1)

        cmd = _build_colabfold_cmd(
            colabfold_bin=args.colabfold_bin,
            fasta_path=fasta_path,
            output_dir=output_dir,
            model_type=args.model_type,
            msa_mode=args.msa_mode,
            num_models=args.num_models,
            num_recycle=args.num_recycle,
            use_templates=args.use_templates,
            amber=args.amber,
            num_relax=args.num_relax,
            disulfide_bond_pairs=disulfide_bond_pairs,
        )
        print(f"[Stage 2/3] HighFold structure prediction")
        print(f"  -> Running: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error: colabfold_batch failed with exit code {e.returncode}", file=sys.stderr)
            sys.exit(e.returncode)
        print(f"  -> Prediction complete, results in {output_dir}")
    else:
        print("[Stage 2/3] Skipped")

    # ================================================================
    # Stage 3: Evaluation & Report
    # ================================================================
    if not args.skip_evaluate and not args.skip_predict:
        print("[Stage 3/3] Computing physicochemical properties and pLDDT scores")
        seq_list = read_fasta_sequences(str(fasta_path))
        score_dict = collect_plddt_scores(str(output_dir), seq_list)
        csv_path = output_dir / "output.csv"
        df = generate_report(seq_list, score_dict, str(csv_path))
        print(f"  -> Report saved to {csv_path}")
        print(f"  -> {len(df)} sequences evaluated")
    elif args.skip_predict:
        # If prediction was skipped, we can still compute properties (without pLDDT)
        if not args.skip_evaluate:
            print("[Stage 3/3] Computing physicochemical properties (no pLDDT — prediction was skipped)")
            seq_list = read_fasta_sequences(str(fasta_path))
            score_dict = {seq: float("nan") for seq in seq_list}
            csv_path = output_dir / "output.csv"
            df = generate_report(seq_list, score_dict, str(csv_path))
            print(f"  -> Report saved to {csv_path} (pLDDT = NaN, prediction skipped)")
        else:
            print("[Stage 3/3] Skipped")
    else:
        print("[Stage 3/3] Skipped")

    print("\nDone!")


if __name__ == "__main__":
    main()
