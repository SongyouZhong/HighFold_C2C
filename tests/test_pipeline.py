"""Tests for the core pipeline module."""

from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from highfold_c2c.core.pipeline import (
    _parse_disulfide_pairs,
    _build_colabfold_cmd,
)


class TestParseDisulfidePairs:
    """Test disulfide bond pair parsing."""

    def test_empty_string(self):
        assert _parse_disulfide_pairs("") == []

    def test_none(self):
        assert _parse_disulfide_pairs(None) == []

    def test_single_pair(self):
        assert _parse_disulfide_pairs("2,5") == [(2, 5)]

    def test_multiple_pairs(self):
        assert _parse_disulfide_pairs("2,5:3,7") == [(2, 5), (3, 7)]

    def test_triple_pairs(self):
        result = _parse_disulfide_pairs("1,4:2,5:3,7")
        assert result == [(1, 4), (2, 5), (3, 7)]


class TestBuildColabfoldCmd:
    """Test colabfold_batch command construction."""

    def test_basic_command(self):
        cmd = _build_colabfold_cmd(
            colabfold_bin="colabfold_batch",
            fasta_path=Path("/tmp/predict.fasta"),
            output_dir=Path("/tmp/output"),
            model_type="alphafold2",
            msa_mode="single_sequence",
            num_models=5,
            num_recycle=None,
            use_templates=False,
            amber=False,
            num_relax=0,
            disulfide_bond_pairs=[],
        )
        assert cmd[0] == "colabfold_batch"
        assert "--model-type" in cmd
        assert "alphafold2" in cmd
        assert "--msa-mode" in cmd
        assert "single_sequence" in cmd
        assert "--num-models" in cmd
        assert "5" in cmd
        assert str(Path("/tmp/predict.fasta")) in cmd
        assert str(Path("/tmp/output")) in cmd

    def test_with_disulfide_bonds(self):
        cmd = _build_colabfold_cmd(
            colabfold_bin="colabfold_batch",
            fasta_path=Path("/tmp/predict.fasta"),
            output_dir=Path("/tmp/output"),
            model_type="alphafold2",
            msa_mode="single_sequence",
            num_models=5,
            num_recycle=None,
            use_templates=False,
            amber=False,
            num_relax=0,
            disulfide_bond_pairs=[(2, 5), (3, 7)],
        )
        assert "--disulfide-bond-pairs" in cmd
        idx = cmd.index("--disulfide-bond-pairs")
        assert cmd[idx + 1] == "2,5:3,7"

    def test_with_amber(self):
        cmd = _build_colabfold_cmd(
            colabfold_bin="colabfold_batch",
            fasta_path=Path("/tmp/predict.fasta"),
            output_dir=Path("/tmp/output"),
            model_type="alphafold2",
            msa_mode="single_sequence",
            num_models=5,
            num_recycle=3,
            use_templates=True,
            amber=True,
            num_relax=2,
            disulfide_bond_pairs=[],
        )
        assert "--amber" in cmd
        assert "--num-relax" in cmd
        assert "--templates" in cmd
        assert "--num-recycle" in cmd
        assert "3" in cmd

    def test_custom_bin_path(self):
        cmd = _build_colabfold_cmd(
            colabfold_bin="/opt/localcolabfold/bin/colabfold_batch",
            fasta_path=Path("/tmp/predict.fasta"),
            output_dir=Path("/tmp/output"),
            model_type="alphafold2_ptm",
            msa_mode="mmseqs2_uniref",
            num_models=3,
            num_recycle=None,
            use_templates=False,
            amber=False,
            num_relax=0,
            disulfide_bond_pairs=[],
        )
        assert cmd[0] == "/opt/localcolabfold/bin/colabfold_batch"
        assert "alphafold2_ptm" in cmd
        assert "mmseqs2_uniref" in cmd
