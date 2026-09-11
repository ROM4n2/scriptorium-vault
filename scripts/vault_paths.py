#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vault root resolution — the single portability contract.

Every vault script MUST obtain the vault root through `resolve_vault_root`
instead of hardcoding a machine-specific path. Precedence:

    1. explicit CLI value (`--vault-root`)
    2. `VAULT_ROOT` environment variable
    3. default: the parent directory of this `scripts/` folder

Rule (3) makes a portable template work anywhere: drop the kit, run the
script, and the root is wherever the kit lives. Rules (1) and (2) let a
single machine drive several vaults, or run the scripts from elsewhere.

A resolved root MUST exist; missing paths raise `FileNotFoundError` rather
than silently falling back to a wrong directory (fail loud, not wrong).
"""

import os
import pathlib
from typing import Optional

VAULT_ROOT_ENV = "VAULT_ROOT"

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent


def default_vault_root() -> pathlib.Path:
    """Default root = parent of the scripts/ directory (portable layout)."""
    return _SCRIPTS_DIR.parent


def resolve_vault_root(
    cli_value: Optional[str] = None,
    env: Optional[dict] = None,
) -> pathlib.Path:
    """Resolve the vault root: CLI > $VAULT_ROOT > scripts/ parent."""
    raw = cli_value
    if not raw:
        raw = (env if env is not None else os.environ).get(VAULT_ROOT_ENV)
    if raw:
        root = pathlib.Path(raw).expanduser().resolve()
    else:
        root = default_vault_root().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"vault root not found: {root}")
    return root


def add_vault_root_arg(parser) -> None:
    """Attach the standard `--vault-root` option to an argparse parser."""
    parser.add_argument(
        "--vault-root",
        default=None,
        help=f"vault root (default: ${VAULT_ROOT_ENV} or the parent of scripts/)",
    )
