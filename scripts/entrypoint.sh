#!/usr/bin/env bash
set -euo pipefail

# Activate virtual environment if present
if [[ -f /home/comfyuser/venv/bin/activate ]]; then
  source /home/comfyuser/venv/bin/activate
fi

# Switch to ComfyUI directory
cd /home/comfyuser/ComfyUI

# Attempt to download/update models (if variables set)
python /home/comfyuser/scripts/download_civitai_models.py || true

# Start ComfyUI (forward any additional args)
exec python main.py --listen 0.0.0.0 --port 8188 "$@" 