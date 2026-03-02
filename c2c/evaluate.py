"""
Cyclic peptide physicochemical property calculation, pLDDT score collection,
and CSV report generation.

Extracted from C2C_release/3-final.py and refactored for module import.
"""

import glob
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from Bio.SeqUtils.ProtParam import ProteinAnalysis

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HOPP_WOODS: Dict[str, float] = {
    "A": -0.5, "R":  3.0, "N":  0.2, "D":  3.0, "C": -1.0,
    "Q":  0.2, "E":  3.0, "G":  0.0, "H": -0.5, "I": -1.8,
    "L": -1.8, "K":  3.0, "M": -1.3, "F": -2.5, "P":  0.0,
    "S":  0.3, "T": -0.4, "W": -3.4, "Y": -2.3, "V": -1.5,
}
"""Hopp-Woods hydrophilicity scale for 20 standard amino acids."""


# ---------------------------------------------------------------------------
# Property calculations
# ---------------------------------------------------------------------------

def calculate_hydrophilicity(sequence: str, scale: Dict[str, float] = None) -> float:
    """Compute the mean Hopp-Woods hydrophilicity of a sequence.

    Parameters
    ----------
    sequence : str
        Amino-acid sequence (single-letter codes).
    scale : dict, optional
        Custom hydrophilicity scale.  Defaults to ``HOPP_WOODS``.

    Returns
    -------
    float
        Mean hydrophilicity value.
    """
    if scale is None:
        scale = HOPP_WOODS
    values = [scale.get(aa, 0.0) for aa in sequence]
    return sum(values) / len(values) if values else 0.0


def calculate_properties(sequence: str) -> dict:
    """Compute physicochemical properties for a single peptide sequence.

    Parameters
    ----------
    sequence : str
        Amino-acid sequence.

    Returns
    -------
    dict
        Keys: ``molecular_weight``, ``isoelectric_point``, ``aromaticity``,
        ``instability_index``, ``hydrophobicity`` (GRAVY), ``hydrophilicity``
        (Hopp-Woods), ``secondary_structure`` (helix, turn, sheet fractions).
    """
    analysis = ProteinAnalysis(sequence)
    return {
        "molecular_weight": analysis.molecular_weight(),
        "isoelectric_point": analysis.isoelectric_point(),
        "aromaticity": analysis.aromaticity(),
        "instability_index": analysis.instability_index(),
        "hydrophobicity": analysis.gravy(),
        "hydrophilicity": calculate_hydrophilicity(sequence),
        "secondary_structure": analysis.secondary_structure_fraction(),
    }


# ---------------------------------------------------------------------------
# FASTA reading
# ---------------------------------------------------------------------------

def read_fasta_sequences(fasta_path: str) -> List[str]:
    """Read sequences from a FASTA file (skipping header lines).

    Parameters
    ----------
    fasta_path : str
        Path to the FASTA file.

    Returns
    -------
    list[str]
        List of amino-acid sequences.
    """
    sequences = []
    with open(fasta_path, "r") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith(">"):
                sequences.append(line)
    return sequences


# ---------------------------------------------------------------------------
# pLDDT score collection
# ---------------------------------------------------------------------------

def collect_plddt_scores(
    result_dir: str,
    seq_list: List[str],
    model_pattern: str = "alphafold2",
) -> Dict[str, float]:
    """Collect mean pLDDT scores from ColabFold/HighFold JSON output files.

    For each sequence (indexed 1..N matching the FASTA order), globs for JSON
    files matching ``pep{i}_scores_rank_00*_{model_pattern}_model_*_seed_000.json``
    inside *result_dir* and averages the per-residue pLDDT values across all models.

    Parameters
    ----------
    result_dir : str
        Directory containing ColabFold output files.
    seq_list : list[str]
        Ordered list of sequences (matching FASTA entry order).
    model_pattern : str
        Model name pattern in the JSON filename (default ``"alphafold2"``).

    Returns
    -------
    dict[str, float]
        Mapping from sequence string to mean pLDDT score.
    """
    result_dir = Path(result_dir)
    score_dict: Dict[str, float] = {}

    for i, seq in enumerate(seq_list, start=1):
        pattern = str(
            result_dir / f"pep{i}_scores_rank_00*_{model_pattern}_model_*_seed_000.json"
        )
        file_list = glob.glob(pattern)
        score_list = []
        for filepath in file_list:
            with open(filepath, "r") as fh:
                data = json.load(fh)
            if "plddt" in data:
                score_list.append(np.mean(data["plddt"]))
        if score_list:
            score_dict[seq] = float(np.mean(score_list))
        else:
            score_dict[seq] = float("nan")

    return score_dict


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    seq_list: List[str],
    score_dict: Dict[str, float],
    output_path: str,
) -> pd.DataFrame:
    """Generate a CSV report with physicochemical properties and pLDDT scores.

    Parameters
    ----------
    seq_list : list[str]
        Ordered list of peptide sequences.
    score_dict : dict[str, float]
        Mapping from sequence to pLDDT score.
    output_path : str
        Destination CSV file path.

    Returns
    -------
    pandas.DataFrame
        The generated report data.
    """
    rows = []
    for i, seq in enumerate(seq_list, start=1):
        props = calculate_properties(seq)
        rows.append({
            "Index": i,
            "Cyclic sequence": seq,
            "pLDDT": score_dict.get(seq, float("nan")),
            "Molecular weight": props["molecular_weight"],
            "Isoelectric point": props["isoelectric_point"],
            "Aromaticity": props["aromaticity"],
            "Instability index": props["instability_index"],
            "Hydrophobicity": props["hydrophobicity"],
            "Hydrophilicity": props["hydrophilicity"],
        })

    df = pd.DataFrame(rows)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return df
