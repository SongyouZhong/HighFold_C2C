"""
Run HighFold structure prediction only (without C2C sequence generation).

This is a convenience wrapper around ``colabfold_batch`` that maintains
backward compatibility with the original HighFold workflow.

Usage::

    python -m scripts.run_predict_only \\
        input.fasta output/ \\
        [--model-type alphafold2] \\
        [--msa-mode single_sequence] \\
        [--disulfide-bond-pairs "1,4"]
"""

import argparse
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(
        description="HighFold structure prediction (wrapper around colabfold_batch)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "This script simply forwards arguments to colabfold_batch.\n"
            "Make sure LocalColabFold is installed and colabfold_batch is on PATH.\n"
            "\n"
            "Example:\n"
            "  python -m scripts.run_predict_only input.fasta ./output \\\n"
            "      --model-type alphafold2 --msa-mode single_sequence\n"
        ),
    )
    parser.add_argument("input", help="Input FASTA/a3m file or directory")
    parser.add_argument("results", help="Output directory")
    parser.add_argument("--model-type", default="alphafold2",
                        choices=["auto", "alphafold2", "alphafold2_ptm",
                                 "alphafold2_multimer_v1", "alphafold2_multimer_v2",
                                 "alphafold2_multimer_v3", "deepfold_v1"])
    parser.add_argument("--msa-mode", default="single_sequence",
                        choices=["mmseqs2_uniref_env", "mmseqs2_uniref", "single_sequence"])
    parser.add_argument("--disulfide-bond-pairs", type=str, default=None,
                        help="Disulfide bond pairs (format: 'A,B' or 'A,B:C,D', 0-based)")
    parser.add_argument("--num-models", type=int, default=5, choices=[1, 2, 3, 4, 5])
    parser.add_argument("--num-recycle", type=int, default=None)
    parser.add_argument("--templates", action="store_true")
    parser.add_argument("--amber", action="store_true")
    parser.add_argument("--num-relax", type=int, default=0)
    parser.add_argument("--colabfold-bin", default="colabfold_batch",
                        help="Path to colabfold_batch executable")

    args = parser.parse_args()

    if shutil.which(args.colabfold_bin) is None:
        print(
            f"Error: '{args.colabfold_bin}' not found on PATH.\n"
            f"Install LocalColabFold first, then overlay HighFold source files.",
            file=sys.stderr,
        )
        sys.exit(1)

    cmd = [args.colabfold_bin]
    cmd += ["--model-type", args.model_type]
    cmd += ["--msa-mode", args.msa_mode]
    cmd += ["--num-models", str(args.num_models)]
    if args.num_recycle is not None:
        cmd += ["--num-recycle", str(args.num_recycle)]
    if args.templates:
        cmd += ["--templates"]
    if args.amber:
        cmd += ["--amber"]
        if args.num_relax > 0:
            cmd += ["--num-relax", str(args.num_relax)]
    if args.disulfide_bond_pairs:
        cmd += ["--disulfide-bond-pairs", args.disulfide_bond_pairs]
    cmd += [args.input, args.results]

    print(f"Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)


if __name__ == "__main__":
    main()
