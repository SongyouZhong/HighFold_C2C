"""
C2C T5 model definition, CharTokenizer, LogitsProcessor, StoppingCriteria, and model loading.

Extracted from C2C_release/1-predict-cyclic.py and refactored into importable components.
"""

import torch
from transformers import (
    T5Config,
    T5ForConditionalGeneration,
    LogitsProcessorList,
    StoppingCriteriaList,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LETTER_SET = set(list("ACDEFGHIKLMNPQRSTVWY"))
"""Set of 20 standard amino acid single-letter codes."""


# ---------------------------------------------------------------------------
# CharTokenizer
# ---------------------------------------------------------------------------

class CharTokenizer:
    """Character-level tokenizer consistent with C2C training.

    Vocabulary: 4 special tokens (<pad>, <s>, </s>, <unk>) followed by a sorted
    union of amino-acid letters, digits, punctuation, and a-z/A-Z characters.
    """

    def __init__(self):
        aa = list("ACDEFGHIKLMNPQRSTVWY")
        digits = list("0123456789")
        punct = list(" <>/:-_=+.,;()[]{}\"'\\")
        letters = [chr(c) for c in range(65, 91)] + [chr(c) for c in range(97, 123)]
        basic = sorted(set(aa + digits + punct + letters + [" "]))

        self.pad_token = "<pad>"
        self.bos_token = "<s>"
        self.eos_token = "</s>"
        self.unk_token = "<unk>"
        specials = [self.pad_token, self.bos_token, self.eos_token, self.unk_token]

        self.vocab = specials + basic
        self.stoi = {t: i for i, t in enumerate(self.vocab)}
        self.itos = {i: t for i, t in enumerate(self.vocab)}

        self.pad_token_id = self.stoi[self.pad_token]
        self.eos_token_id = self.stoi[self.eos_token]
        self.bos_token_id = self.stoi[self.bos_token]
        self.unk_token_id = self.stoi[self.unk_token]

    def encode(self, text, add_eos=False, max_length=None):
        """Encode text to a list of token IDs."""
        ids = [self.stoi.get(ch, self.unk_token_id) for ch in text]
        if add_eos:
            ids.append(self.eos_token_id)
        if max_length is not None:
            ids = ids[:max_length]
        return ids

    def batch_decode(self, ids_batch, skip_special_tokens=True):
        """Decode a batch of token-ID sequences to strings."""
        outs = []
        data = ids_batch.tolist() if hasattr(ids_batch, "tolist") else ids_batch
        for ids in data:
            toks = [self.itos.get(int(i), self.unk_token) for i in ids]
            if skip_special_tokens:
                toks = [
                    t
                    for t in toks
                    if t not in (self.pad_token, self.eos_token, self.bos_token, self.unk_token)
                ]
            outs.append("".join(toks))
        return outs

    def convert_ids_to_tokens(self, ids):
        """Convert a list of integer IDs to token strings."""
        return [self.itos.get(int(i), self.unk_token) for i in ids]

    def convert_tokens_to_string(self, toks):
        """Concatenate tokens into a single string."""
        return "".join(toks)


# ---------------------------------------------------------------------------
# Helper: count amino-acid letters in generated IDs
# ---------------------------------------------------------------------------

def _count_letters_in_ids(tokenizer: CharTokenizer, ids) -> int:
    """Count how many characters in *ids* are standard amino-acid letters."""
    toks = tokenizer.convert_ids_to_tokens(ids.tolist())
    txt = tokenizer.convert_tokens_to_string(toks)
    return sum(1 for ch in txt if ch in LETTER_SET)


# ---------------------------------------------------------------------------
# LogitsProcessor & StoppingCriteria
# ---------------------------------------------------------------------------

class BlockEosUntilLetters(torch.nn.Module):
    """Logits processor that blocks EOS until *span_len* AA letters are generated,
    then forces EOS once the count is reached."""

    def __init__(self, tokenizer: CharTokenizer, eos_id: int, span_lens):
        super().__init__()
        self.tokenizer = tokenizer
        self.eos_id = eos_id
        self.span_lens = span_lens

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor):
        B = input_ids.size(0)
        for b in range(B):
            Ls = self.span_lens[b] if isinstance(self.span_lens, list) else int(self.span_lens)
            cnt = _count_letters_in_ids(self.tokenizer, input_ids[b])
            if cnt < Ls:
                scores[b, self.eos_id] = -float("inf")
            elif cnt >= Ls:
                scores[b, :] = -float("inf")
                scores[b, self.eos_id] = 0.0
        return scores


class StopAtLetters(torch.nn.Module):
    """Stopping criterion: stop when all sequences in the batch have generated
    at least *span_len* amino-acid letters."""

    def __init__(self, tokenizer: CharTokenizer, span_lens):
        super().__init__()
        self.tokenizer = tokenizer
        self.span_lens = span_lens

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs) -> bool:
        B = input_ids.size(0)
        for b in range(B):
            Ls = self.span_lens[b] if isinstance(self.span_lens, list) else int(self.span_lens)
            cnt = _count_letters_in_ids(self.tokenizer, input_ids[b])
            if cnt < Ls:
                return False
        return True


# ---------------------------------------------------------------------------
# Input formatting
# ---------------------------------------------------------------------------

def make_input_text(core: str, L: int) -> str:
    """Format the T5 input prompt for C2C generation.

    Parameters
    ----------
    core : str
        Core peptide sequence (e.g. ``"NNN"``).
    L : int
        Desired span length (number of residues to generate).

    Returns
    -------
    str
        Formatted prompt string.
    """
    sc = " ".join(core)
    return (
        f"<CORE_HEAD> {sc} </CORE_HEAD> "
        f"<CORE_TAIL> {sc} </CORE_TAIL> "
        f"<LEN> {L} </LEN>"
    )


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def load_c2c_model(checkpoint_path: str, device: str = None):
    """Load the C2C T5 model from a checkpoint file.

    Parameters
    ----------
    checkpoint_path : str
        Path to the ``c2c_model.pt`` checkpoint.
    device : str, optional
        PyTorch device string (``"cuda"``, ``"cpu"``).  Auto-detected if *None*.

    Returns
    -------
    tuple[T5ForConditionalGeneration, CharTokenizer, str]
        ``(model, tokenizer, device)``
    """
    tokenizer = CharTokenizer()
    config = T5Config(
        vocab_size=len(tokenizer.vocab),
        d_model=256,
        d_ff=512,
        num_layers=4,
        num_decoder_layers=4,
        num_heads=4,
        dropout_rate=0.3,
        layer_norm_epsilon=1e-6,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
        decoder_start_token_id=tokenizer.pad_token_id,
    )
    model = T5ForConditionalGeneration(config)
    model.config.decoder_start_token_id = tokenizer.pad_token_id

    ckpt = torch.load(checkpoint_path, map_location="cpu")
    if isinstance(ckpt, dict) and "state_dict" in ckpt:
        ckpt = ckpt["state_dict"]
    try:
        model.load_state_dict(ckpt, strict=True)
    except Exception:
        model.load_state_dict(ckpt, strict=False)

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    model.eval()
    return model, tokenizer, device
