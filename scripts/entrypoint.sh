#!/usr/bin/env bash
set -euo pipefail

# Determine script directory and derive paths from it
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Set default paths but allow environment overrides
COMFY_DIR="${COMFY_DIR:-/home/comfyuser/ComfyUI}"
VENV_PATH="${VENV_PATH:-$COMFY_DIR/venv}"
MODELS_DIR="${MODELS_DIR:-$COMFY_DIR/models}"
DOWNLOAD_SCRIPT="${DOWNLOAD_SCRIPT:-$SCRIPT_DIR/download_civitai_models.py}"

# Activate virtual environment if present
if [[ -f "$VENV_PATH/bin/activate" ]]; then
  echo "[*] Activating virtual environment at $VENV_PATH"
  source "$VENV_PATH/bin/activate"
else
  echo "[!] No virtual environment found at $VENV_PATH, using system Python"
fi

# Switch to ComfyUI directory if it exists
if [[ -d "$COMFY_DIR" ]]; then
  echo "[*] Switching to ComfyUI directory: $COMFY_DIR"
  cd "$COMFY_DIR"
else
  echo "[!] ComfyUI directory not found at $COMFY_DIR"
  echo "    Set COMFY_DIR environment variable to the correct path"
  exit 1
fi

# Attempt to download/update models (if script exists and variables set)
if [[ -f "$DOWNLOAD_SCRIPT" ]]; then
  echo "[*] Running model download script..."
  # Use CLI arguments with fallback to environment variables
  python "$DOWNLOAD_SCRIPT" \
    --dest-dir "$MODELS_DIR" \
    --from-env true || echo "[!] Warning: Model download encountered issues"
else
  echo "[!] Download script not found at $DOWNLOAD_SCRIPT, skipping model downloads"
fi

# Start ComfyUI (forward any additional args)
echo "[*] Starting ComfyUI..."
exec python main.py --listen 0.0.0.0 --port 8188 "$@" 