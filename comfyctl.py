#!/usr/bin/env python3
"""Simple CLI wrapper for ComfyUI installer and runtime.

Usage:
  comfyctl install   [--config CONFIG] [--env-file ENV] [--workflow WORKFLOW]
  comfyctl validate  [--config CONFIG]
  comfyctl start     [--config CONFIG]

Environment variables like AUTO_START, CIVITAI_API_KEY still apply.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT / "scripts"
INSTALL_SH = SCRIPTS_DIR / "install_comfy_and_models.sh"
VALIDATE_PY = SCRIPTS_DIR / "validate_config.py"

DEFAULT_CONFIG = ROOT / "config.yml"


def run_install(args: argparse.Namespace):
    import sys
    cmd = ["bash", str(INSTALL_SH)]
    env = os.environ.copy()
    if args.config:
        env["CONFIG_FILE"] = str(pathlib.Path(args.config).resolve())
    if args.env_file:
        env["ENV_FILE"] = str(pathlib.Path(args.env_file).resolve())
    if args.workflow:
        env["WORKFLOW"] = args.workflow
    try:
        subprocess.run(cmd, env=env, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Installation failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)


def run_validate(args: argparse.Namespace):
    """Validate a YAML configuration file."""
    import sys

    config_path = pathlib.Path(args.config or DEFAULT_CONFIG).resolve()

    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        sys.exit(1)

    # Run the validation script
    cmd = [sys.executable, str(VALIDATE_PY), str(config_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Print the output from the validator
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    sys.exit(result.returncode)


def run_start(args: argparse.Namespace):
    import sys
    cfg_path = pathlib.Path(args.config or DEFAULT_CONFIG).resolve()
    comfy_dir = "/workspace/ComfyUI"  # default
    # Read config to override comfy_dir if set
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(cfg_path.read_text()) or {}
        comfy_dir = data.get("install", {}).get("comfy_dir", comfy_dir)
    except Exception:
        pass  # fallback to default

    python_bin = pathlib.Path(comfy_dir) / "venv" / "bin" / "python"
    main_py = pathlib.Path(comfy_dir) / "main.py"
    cmd = [str(python_bin), str(main_py), "--listen", "--port", "8188"]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ ComfyUI failed to start with exit code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)


def main():
    ap = argparse.ArgumentParser(
        prog="comfyctl", description="Manage ComfyUI environment"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_install = sub.add_parser("install", help="Run the installer script")
    ap_install.add_argument("--config", help="Path to config.yml")
    ap_install.add_argument("--env-file", help="Path to .env file")
    ap_install.add_argument(
        "--workflow", help="Install dependencies for specific workflow only"
    )
    ap_install.set_defaults(func=run_install)

    ap_validate = sub.add_parser("validate", help="Validate a configuration file")
    ap_validate.add_argument(
        "--config", help="Path to config.yml (default: config.yml)"
    )
    ap_validate.set_defaults(func=run_validate)

    ap_start = sub.add_parser("start", help="Launch ComfyUI using configured comfy_dir")
    ap_start.add_argument("--config", help="Path to config.yml (to locate comfy_dir)")
    ap_start.set_defaults(func=run_start)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
