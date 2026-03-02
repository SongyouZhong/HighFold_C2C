"""
CycPOEM (Cyclic Position Offset Encoding Matrix)
=================================================

Core algorithm for computing shortest-path distance matrices on cyclic peptides
with optional disulfide bond connectivity. Used to replace the standard linear
relative-position encoding in AlphaFold with a topology-aware encoding.

Algorithm summary:
  1. Build an adjacency graph with:
     - linear peptide bonds (i ↔ i+1)
     - N-C cyclization bond (0 ↔ n-1)
     - disulfide bonds (c1[k] ↔ c2[k])
  2. Run Floyd-Warshall to find shortest paths.
  3. Apply sign convention: upper-triangle distances are negated to encode
     directionality.

The resulting matrix is stored as ``feat['offset_ss']`` and injected into
AlphaFold's relative-position encoding by the modified ``modules.py`` /
``modules_multimer.py``.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Public API used by batch.py
# ---------------------------------------------------------------------------


def get_offset(
    disulfide_bond_pairs: List[Tuple[int, int]],
    feat: Dict[str, np.ndarray],
) -> None:
    """Compute CycPOEM for **multimer** features (in-place).

    Determines cyclic-peptide residues by finding the first chain boundary
    (``residue_index == 0``), computes the CycPOEM distance matrix, and stores
    it as ``feat['offset_ss']`` together with ``feat['cycpep_index']``.
    """
    feat["cycpep_index"] = np.arange(len(feat["residue_index"]))
    index_zero = [
        i
        for i in range(len(feat["residue_index"]))
        if feat["residue_index"][i] == 0
    ]
    if len(index_zero) > 1:
        feat["cycpep_index"] = np.arange(index_zero[1])
    len_cycpep = len(feat["cycpep_index"])
    c_start, c_end = _split_pairs(disulfide_bond_pairs)
    feat["offset_ss"] = np.array(cpcm(len_cycpep, c_start, c_end))


def get_offset_monomer(
    disulfide_bond_pairs: List[Tuple[int, int]],
    feat: Dict[str, np.ndarray],
) -> None:
    """Compute CycPOEM for **monomer** features (in-place).

    Iterates over the batch dimension of ``feat['residue_index']``, computes one
    CycPOEM matrix per sample, and stores the stacked result as
    ``feat['offset_ss']``.
    """
    c_start, c_end = _split_pairs(disulfide_bond_pairs)
    offset_ss = []
    for i in range(len(feat["residue_index"])):
        len_cycpep = len(feat["residue_index"][i])
        offset_ss.append(cpcm(len_cycpep, c_start, c_end))
    feat["offset_ss"] = np.array(offset_ss)


# ---------------------------------------------------------------------------
# Core algorithm
# ---------------------------------------------------------------------------


def cpcm(
    n_aa: int,
    c1: List[int],
    c2: List[int],
    flag_nc: int = 1,
) -> np.ndarray:
    """Cyclic Peptide Connectivity Matrix.

    Parameters
    ----------
    n_aa : int
        Number of amino-acid residues.
    c1, c2 : list[int]
        Paired cysteine residue indices for disulfide bonds.
    flag_nc : int
        Whether to add the N-C cyclization bond (1 = yes).

    Returns
    -------
    matrix : np.ndarray, shape (n_aa, n_aa)
        Signed shortest-path distance matrix.
    """
    matrix, _path = calc_offset_matrix_signal(n_aa, c1, c2, flag_nc)
    matrix = _mtx_with_upper_negative(matrix)
    return matrix


def calc_offset_matrix_signal(
    n_aa: int,
    c1: List[int],
    c2: List[int],
    flag_nc: int = 1,
) -> Tuple[np.ndarray, np.ndarray]:
    """Build adjacency graph and run Floyd-Warshall (with path tracking).

    Parameters
    ----------
    n_aa : int
        Number of amino-acid residues.
    c1, c2 : list[int]
        Paired cysteine residue indices (must have equal length).
    flag_nc : int
        Whether to include the N→C cyclization bond.

    Returns
    -------
    matrix : np.ndarray
        Shortest-path distance matrix.
    path : np.ndarray
        Predecessor matrix for path reconstruction.
    """
    if len(c1) != len(c2):
        return np.array([]), np.array([])

    # init adjacency matrix and path
    matrix = np.zeros((n_aa, n_aa)) + n_aa
    path = np.zeros_like(matrix) - 1
    for i in range(n_aa):
        matrix[i][i] = 0
        path[i][i] = i

    # linear peptide connection
    for i in range(n_aa - 1):
        matrix[i][i + 1] = 1
        matrix[i + 1][i] = 1
        path[i][i + 1] = i
        path[i + 1][i] = i + 1

    # N-C cyclization bond
    if flag_nc:
        matrix[0][n_aa - 1] = 1
        matrix[n_aa - 1][0] = 1
        path[0][n_aa - 1] = 0
        path[n_aa - 1][0] = n_aa - 1

    # disulfide bonds
    for i in range(len(c1)):
        matrix[c1[i]][c2[i]] = 1
        matrix[c2[i]][c1[i]] = 1
        path[c1[i]][c2[i]] = c1[i]
        path[c2[i]][c1[i]] = c2[i]

    # Floyd-Warshall shortest path
    matrix, path = _get_opt_path_signal(matrix, path)
    return matrix, path


def calc_offset_matrix(
    n_aa: int,
    c1: List[int],
    c2: List[int],
) -> np.ndarray:
    """Simpler offset matrix (without path tracking).

    Builds the same adjacency graph as :func:`calc_offset_matrix_signal` but
    returns a signed distance matrix directly (without path predecessor info).
    """
    if len(c1) != len(c2):
        return np.array([])

    matrix = np.zeros((n_aa, n_aa)) + n_aa
    for i in range(n_aa):
        matrix[i][i] = 0

    # linear peptide connection
    for i in range(n_aa - 1):
        matrix[i][i + 1] = 1
        matrix[i + 1][i] = 1

    # N-C cyclization bond
    matrix[0][n_aa - 1] = 1
    matrix[n_aa - 1][0] = 1

    # disulfide bonds
    for i in range(len(c1)):
        matrix[c1[i]][c2[i]] = 1
        matrix[c2[i]][c1[i]] = 1

    matrix = _get_opt_path(matrix)

    # sign convention: upper triangle negative
    for i in range(matrix.shape[0]):
        for j in range(i + 1, matrix.shape[0]):
            matrix[i][j] *= -1

    return matrix


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _split_pairs(
    pairs: List[Tuple[int, int]],
) -> Tuple[List[int], List[int]]:
    """Split list of (start, end) pairs into two lists."""
    c_start: List[int] = []
    c_end: List[int] = []
    for item in pairs:
        c_start.append(item[0])
        c_end.append(item[1])
    return c_start, c_end


def _mtx_with_upper_negative(matrix: np.ndarray) -> np.ndarray:
    """Negate upper-triangle values for directional encoding."""
    for i in range(matrix.shape[0]):
        for j in range(i + 1, matrix.shape[0]):
            matrix[i][j] *= -1
    return matrix


def _get_opt_path_signal(
    matrix: np.ndarray,
    path: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Floyd-Warshall with path tracking."""
    for k in range(matrix.shape[0]):
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[0]):
                if matrix[i][j] > matrix[i][k] + matrix[k][j]:
                    matrix[i][j] = matrix[i][k] + matrix[k][j]
                    path[i][j] = k
    return matrix, path


def _get_opt_path(matrix: np.ndarray) -> np.ndarray:
    """Floyd-Warshall without path tracking."""
    n = matrix.shape[0]
    path = np.zeros_like(matrix)
    for i in range(n):
        path[i] = np.arange(n)

    for m in range(n):
        for i in range(n):
            for j in range(n):
                if matrix[i][m] + matrix[m][j] < matrix[i][j]:
                    matrix[i][j] = matrix[i][m] + matrix[m][j]
                    path[i][j] = m
    return matrix


def _get_path(path: np.ndarray, i: int, j: int) -> str:
    """Reconstruct shortest path between *i* and *j* (for debugging)."""
    if int(path[i][j]) == i:
        return f"{i} {j}"
    k = int(path[i][j])
    return _get_path(path, i, k) + " " + _get_path(path, k, j) + " "


def _mtx_with_signal(m: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Alternative sign assignment using path tracing (currently unused)."""
    m_signal = np.zeros_like(m)
    n = m.shape[0]
    for i in range(n):
        for j in range(i, i + n - 1):
            if m[i][j % n] < m[i][(j + 1) % n]:
                m_signal[i][(j + 1) % n] = -1
            else:
                break
        for j in range(i, i - n + 1, -1):
            if m[i][j % n] < m[i][(j - 1) % n]:
                m_signal[i][(j - 1) % n] = 1
            else:
                break

    for i in range(n):
        for j in range(n):
            if i != j and m_signal[i][j] == 0:
                route = _get_path(p, i, j).strip().split()
                route_sum = 0
                for k in range(0, len(route), 2):
                    route_sum += m_signal[int(route[k])][int(route[k + 1])]
                m_signal[i][j] = np.sign(route_sum)

    for i in range(n):
        for j in range(n):
            if i != j and m_signal[i][j] == 0:
                m_signal[i][j] = np.sign(
                    m_signal[i][j] + 0.5 * np.sign(int(i < j) - 0.5)
                )

    return m_signal * m
