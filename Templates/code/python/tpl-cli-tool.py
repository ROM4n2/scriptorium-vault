#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Production-grade CLI Script Template
Includes Windows GBK stdout defense, argparse, and structured logging.
"""

import sys

# Windows GBK stdout defense (MUST be at top)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import json
import logging
import pathlib
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def process_data(input_path: pathlib.Path, dry_run: bool = True) -> Dict[str, Any]:
    """Core domain logic."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    logger.info(f"Processing {input_path} (dry_run={dry_run})")
    return {
        "status": "success",
        "file": str(input_path),
        "dry_run": dry_run,
        "items_processed": 0
    }


def main():
    parser = argparse.ArgumentParser(description="CLI Tool Template")
    parser.add_argument("input", type=str, help="Path to input file or directory")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Preview actions without mutating disk")
    parser.add_argument("--apply", action="store_true", help="Apply mutations")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    args = parser.parse_args()
    dry_run = not args.apply

    try:
        res = process_data(pathlib.Path(args.input), dry_run=dry_run)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            logger.info(f"Result: {res}")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Execution failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
