"""C2C default configuration constants."""

# Model defaults
DEFAULT_CHECKPOINT_PATH = "checkpoints/c2c_model.pt"

# Generation defaults
DEFAULT_SPAN_LEN = 5
DEFAULT_NUM_SAMPLE = 20
DEFAULT_TEMPERATURE = 1.0
DEFAULT_TOP_P = 0.9
DEFAULT_TOP_K = 0
DEFAULT_MAX_LENGTH = 128
DEFAULT_SEED = 42

# Sequence constraints
MAX_TOTAL_LENGTH = 20   # Maximum total cyclic peptide length (aa)
MIN_CORE_RATIO = 0.3    # Minimum ratio of core length to total length
