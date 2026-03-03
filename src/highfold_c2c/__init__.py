"""
HighFold-C2C: Cyclic peptide design and structure prediction service.

Provides a FastAPI-based microservice with:
  - SeaweedFS object storage integration
  - PostgreSQL task tracking (shared tasks table)
  - Background task polling with multi-worker support
  - Three-stage pipeline: C2C generation → HighFold prediction → Evaluation
"""

__version__ = "1.0.0"
