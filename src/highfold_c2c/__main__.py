"""
HighFold-C2C CLI entry point.

Usage:
    python -m highfold_c2c
    python -m highfold_c2c --host 0.0.0.0 --port 8003
    python -m highfold_c2c --help
"""

import argparse
import sys


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="highfold_c2c",
        description=(
            "HighFold-C2C — Cyclic peptide design and structure prediction service"
        ),
    )

    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the server to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8003,
        help="Port to bind the server to (default: 8003)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Logging level (default: info)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )

    return parser.parse_args()


def main():
    """Main entry point for the CLI."""
    args = parse_args()

    try:
        import uvicorn

        uvicorn.run(
            "highfold_c2c.app:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            workers=args.workers,
            log_level=args.log_level,
        )
    except ImportError as e:
        print(f"Error: Missing dependency - {e}", file=sys.stderr)
        print(
            "Please install uvicorn: pip install uvicorn[standard]",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
