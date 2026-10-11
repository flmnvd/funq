"""Start the local stdio MCP server."""

import argparse
import logging
import os
from pathlib import Path

from .server import create_server
from .service import FunqService


def main(argv=None):
    directory = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="MCP bridge to an existing Funq-enabled Qt application")
    parser.add_argument("--funq-root", type=Path,
                        default=os.environ.get("FUNQ_ROOT", directory.parent), help="Funq checkout containing client/funq")
    parser.add_argument("--artifact-dir", type=Path,
                        default=os.environ.get("FUNQ_MCP_ARTIFACT_DIR", directory / "artifacts"))
    parser.add_argument("--max-frame-mb", type=int, default=32, help="Maximum Funq response size (1..256 MiB)")
    args = parser.parse_args(argv)
    if not 1 <= args.max_frame_mb <= 256:
        parser.error("--max-frame-mb must be between 1 and 256")
    logging.basicConfig(level=logging.INFO)  # logging writes to stderr; stdout belongs to MCP.
    service = FunqService(args.funq_root, args.artifact_dir, max_frame_bytes=args.max_frame_mb * 1024 * 1024)
    create_server(service).run(transport="stdio")


if __name__ == "__main__":
    main()
