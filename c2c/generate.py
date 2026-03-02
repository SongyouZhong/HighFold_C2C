"""
Cyclic peptide sequence generation: expand a core peptide into full cyclic peptide candidates.

Extracted from C2C_release/1-predict-cyclic.py and refactored for module import.
"""

import random
from pathlib import Path

import torch
from transformers import LogitsProcessorList, StoppingCriteriaList

from c2c.model import (
    LETTER_SET,
    BlockEosUntilLetters,
    StopAtLetters,
    load_c2c_model,
    make_input_text,
)
from c2c.config import (
    DEFAULT_CHECKPOINT_PATH,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_TOP_K,
    DEFAULT_MAX_LENGTH,
    DEFAULT_SEED,
    MAX_TOTAL_LENGTH,
    MIN_CORE_RATIO,
)


def validate_sequence_params(core: str, span_len: int) -> None:
    """Validate that core + span_len satisfy known constraints.

    Raises
    ------
    ValueError
        If the total length exceeds ``MAX_TOTAL_LENGTH`` or the core ratio is
        below ``MIN_CORE_RATIO``.
    """
    total_len = len(core) + span_len
    if total_len > MAX_TOTAL_LENGTH:
        raise ValueError(
            f"Total length ({total_len}) exceeds maximum ({MAX_TOTAL_LENGTH} aa). "
            f"Reduce span_len or shorten core."
        )
    core_ratio = len(core) / total_len
    if core_ratio < MIN_CORE_RATIO:
        raise ValueError(
            f"Core ratio ({core_ratio:.1%}) is below minimum ({MIN_CORE_RATIO:.0%}). "
            f"Core length must be >= {MIN_CORE_RATIO:.0%} of total length."
        )


def sample_c2c_dual(
    core: str,
    n_greedy: int,
    n_sampled: int,
    checkpoint_path: str = DEFAULT_CHECKPOINT_PATH,
    span_len: int = None,
    temperature: float = DEFAULT_TEMPERATURE,
    top_p: float = DEFAULT_TOP_P,
    top_k: int = DEFAULT_TOP_K,
    max_length: int = DEFAULT_MAX_LENGTH,
    seed: int = None,
) -> dict:
    """Generate cyclic peptide sequences by extending a core peptide.

    Uses a trained C2C T5 model to predict span residues appended to the core.
    Both greedy decoding and nucleus sampling are supported.

    Parameters
    ----------
    core : str
        Core peptide sequence (e.g. ``"NNN"``).
    n_greedy : int
        Number of greedy-decoded sequences.
    n_sampled : int
        Number of sampling-decoded sequences.
    checkpoint_path : str
        Path to ``c2c_model.pt``.
    span_len : int, optional
        Number of residues to generate. Defaults to ``len(core)``.
    temperature : float
        Sampling temperature.
    top_p : float
        Nucleus sampling threshold.
    top_k : int
        Top-k sampling parameter. 0 disables top-k filtering.
    max_length : int
        Maximum generation length in tokens.
    seed : int, optional
        Random seed for reproducibility.

    Returns
    -------
    dict
        Keys: ``greedy_spans``, ``sampled_spans``, ``greedy_assembled``,
        ``sampled_assembled``.
    """
    if seed is not None:
        random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)

    model, tokenizer, device = load_c2c_model(checkpoint_path)

    if span_len is None:
        span_len = len(core)

    validate_sequence_params(core, span_len)

    def _prepare_input(n_batch):
        prompt = make_input_text(core, span_len)
        encs = [tokenizer.encode(prompt, add_eos=False) for _ in range(n_batch)]
        max_in = max(len(x) for x in encs)
        input_ids = torch.full((n_batch, max_in), tokenizer.pad_token_id, dtype=torch.long)
        attn_mask = torch.zeros((n_batch, max_in), dtype=torch.long)
        for i, ids in enumerate(encs):
            input_ids[i, : len(ids)] = torch.tensor(ids, dtype=torch.long)
            attn_mask[i, : len(ids)] = 1
        return input_ids.to(device), attn_mask.to(device)

    eos_id = tokenizer.eos_token_id

    def _processors(n):
        return LogitsProcessorList([BlockEosUntilLetters(tokenizer, eos_id, [span_len] * n)])

    def _stoppers(n):
        return StoppingCriteriaList([StopAtLetters(tokenizer, [span_len] * n)])

    # --- Greedy decoding ---
    if n_greedy > 0:
        ids_g, mask_g = _prepare_input(n_greedy)
        gen_g = model.generate(
            input_ids=ids_g,
            attention_mask=mask_g,
            max_length=max_length,
            do_sample=False,
            logits_processor=_processors(n_greedy),
            stopping_criteria=_stoppers(n_greedy),
        )
        txt_g = tokenizer.batch_decode(gen_g, skip_special_tokens=True)
        greedy_spans = [
            "".join(ch for ch in t if ch in LETTER_SET)[:span_len] for t in txt_g
        ]
    else:
        greedy_spans = []

    # --- Sampling decoding ---
    if n_sampled > 0:
        ids_s, mask_s = _prepare_input(n_sampled)
        gen_kwargs = dict(
            input_ids=ids_s,
            attention_mask=mask_s,
            max_length=max_length,
            do_sample=True,
            temperature=temperature,
            top_p=top_p,
            logits_processor=_processors(n_sampled),
            stopping_criteria=_stoppers(n_sampled),
        )
        if top_k > 0:
            gen_kwargs["top_k"] = top_k
        gen_s = model.generate(**gen_kwargs)
        txt_s = tokenizer.batch_decode(gen_s, skip_special_tokens=True)
        sampled_spans = [
            "".join(ch for ch in t if ch in LETTER_SET)[:span_len] for t in txt_s
        ]
    else:
        sampled_spans = []

    # Assemble full sequences: core + generated span
    greedy_assembled = [core + s for s in greedy_spans]
    sampled_assembled = [core + s for s in sampled_spans]

    # Release GPU memory so colabfold_batch (JAX) can use the full GPU later
    del model
    torch.cuda.empty_cache()

    return {
        "greedy_spans": greedy_spans,
        "sampled_spans": sampled_spans,
        "greedy_assembled": greedy_assembled,
        "sampled_assembled": sampled_assembled,
    }


def write_fasta(sequences: list, output_path: str, prefix: str = "pep") -> None:
    """Write sequences to a FASTA file.

    Parameters
    ----------
    sequences : list[str]
        Amino-acid sequences to write.
    output_path : str
        Destination file path (e.g. ``"output/predict.fasta"``).
    prefix : str
        Header prefix. Entries are named ``>{prefix}1``, ``>{prefix}2``, etc.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as fh:
        for i, seq in enumerate(sequences, start=1):
            fh.write(f">{prefix}{i}\n")
            fh.write(f"{seq}\n")
