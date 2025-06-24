#!/usr/bin/env bash
# -------------------------------------------------------------
# Automated installer for ComfyUI + (optional) model downloads
# -------------------------------------------------------------
# This script is intended to be run **inside an existing Linux
# container or VM** where you have root privileges (or at least
# the ability to `apt-get install`). It will:
#   1. Install system packages needed by ComfyUI
#   2. Clone the ComfyUI repository into $COMFY_DIR
#   3. Create a Python virtual-environment and install
#      • PyTorch (CPU or CUDA depending on $CPU_ONLY)
#      • ComfyUI requirements
#      • requests + tqdm (used by download script)
#   4. Optionally download models/LORAs from Civitai using the
#      companion Python script (`download_civitai_models.py`).
#   5. Optionally copy local models from $MODELS_SOURCE_DIR into
#      the destination models directory.
#
# Environment variables that can customise behaviour:
#   COMFY_DIR           – Target install directory
#                         (default: /workspace/ComfyUI)
#   CPU_ONLY            – Set to 1 for CPU-only PyTorch (default 1)
#                         Set to 0 to install CUDA build (requires
#                         compatible CUDA runtime already present).
#   MODEL_DEST_DIR      – Overrides models.dest_dir from YAML.
#   MODELS_SOURCE_DIR   – Overrides models.source_dir from YAML.
#   CIVITAI_API_KEY     – API key for Civitai (required for downloads).
#   WORKFLOW            – Select specific workflow by name to install only
#                         its dependencies (plus global ones).
#   Any variable named  CIVITAI_<CATEGORY> (e.g. CIVITAI_VAE) will
#                       override the corresponding list in YAML.
#                       Normally you configure model lists only in the
#                       YAML file; env vars are just for quick overrides.
#   AUTO_START          – Set to 1 to automatically start ComfyUI after install
#
# Example usage:
#   CPU_ONLY=0 \
#   CIVITAI_API_KEY=... \
#   CIVITAI_CHECKPOINTS="12345, urn:air:sdxl:embedding:civitai:1309512" \
#   CIVITAI_LORAS="99999:88888" \
#   MODELS_SOURCE_DIR=/host_mount/models \
#   AUTO_START=1 \
#   ./install_comfy_and_models.sh
# -------------------------------------------------------------
set -euo pipefail

# -------------------------------------------------------------
# Optional: load environment variables from a file
# If ENV_FILE is set, or a .env file exists in the current directory,
# the script will source it with `export` so that variables become
# available just like if they were passed in the shell environment.
# -------------------------------------------------------------
ENV_FILE="${ENV_FILE:-}"  # allow user to specify: ENV_FILE=/path/to/.env ./install...
if [[ -z "$ENV_FILE" && -f .env ]]; then
  ENV_FILE=".env"
fi

if [[ -n "$ENV_FILE" && -f "$ENV_FILE" ]]; then
  echo "[*] Loading environment variables from $ENV_FILE"
  # Export every variable defined in the file
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

# -------------------------------------------------------------
# Load YAML configuration (config.yml by default) to populate
# variables and lists, reducing reliance on env vars. Only
# CIVITAI_API_KEY and AUTO_START are expected via env.
# -------------------------------------------------------------

# Determine the directory this script resides in (so we can find helper scripts)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Path to YAML config file; can be overridden via CONFIG_FILE env
CONFIG_FILE="${CONFIG_FILE:-config.yml}"

# Validate configuration first
python "$SCRIPT_DIR/validate_config.py" "$CONFIG_FILE" || exit 1

# Load YAML configuration now (overrides env where appropriate)
load_yaml_config() {
  local cfg="$CONFIG_FILE"
  [[ ! -f "$cfg" ]] && return 0

  echo "[*] Loading configuration from $cfg"

  # Use Python + PyYAML to emit shell-compatible exports
  eval "$(python - <<'PY' "$cfg"
import sys, yaml, shlex, pathlib, os
cfg_file = pathlib.Path(sys.argv[1])
data = yaml.safe_load(cfg_file.read_text()) or {}

def export_var(name, value):
    if value is None:
        return
    # Quote the value for shell safety
    print(f"export {name}={shlex.quote(str(value))}")

# Installation section overrides
install = data.get('install', {})
export_var('COMFY_DIR', install.get('comfy_dir'))
export_var('CPU_ONLY', int(bool(install.get('cpu_only', True))))

# Models section handling (supports arbitrary categories)
models = data.get('models', {})
export_var('MODEL_DEST_DIR', models.get('dest_dir'))
export_var('MODELS_SOURCE_DIR', models.get('source_dir'))

def extract_ids(lst, global_models=None):
    """Extract URN/URL/ID values from a list, resolving 'ref' entries."""
    global_models = global_models or {}
    if not lst:
        return None
    out = []
    for item in lst:
        if isinstance(item, dict):
            # Handle references first
            if 'ref' in item:
                ref_id = item['ref']
                # Look up in global models - we'll pass the category later
                val = f"REF:{ref_id}"  # placeholder, resolved below
            else:
                val = item.get('urn') or item.get('url') or item.get('id')
            if val:
                out.append(str(val))
        elif item:
            out.append(str(item))
    return ','.join(out) if out else None

# Handle workflow-specific dependencies
selected_workflow = os.getenv('WORKFLOW')
workflow_models = {}
workflow_nodes = []

if selected_workflow:
    workflows = data.get('workflows', [])
    for wf in workflows:
        if isinstance(wf, dict) and wf.get('name') == selected_workflow:
            print(f"[*] Selected workflow: {selected_workflow}", file=sys.stderr)
            wf_models = wf.get('models', {})
            for cat, lst in wf_models.items():
                workflow_models[cat] = lst
            wf_nodes = wf.get('custom_nodes', [])
            for node in wf_nodes:
                if isinstance(node, dict):
                    if node.get('url'):
                        workflow_nodes.append(node.get('url'))
                    elif node.get('ref'):
                        # We'll resolve this reference later
                        workflow_nodes.append(f"REF:{node.get('ref')}")
            break
    else:
        print(f"[!] Workflow '{selected_workflow}' not found", file=sys.stderr)

# Merge global + workflow-specific models
all_models = {}
# Start with global models
for cat, lst in models.items():
    if cat not in ('dest_dir', 'source_dir'):
        all_models[cat] = lst or []

# Add workflow-specific models
for cat, lst in workflow_models.items():
    if cat in all_models:
        all_models[cat] = all_models[cat] + (lst or [])
    else:
        all_models[cat] = lst or []

def resolve_refs(category, items, global_models):
    """Resolve ref: entries by looking up in global models."""
    resolved = []
    for item_str in (items or '').split(','):
        item_str = item_str.strip()
        if not item_str:
            continue
        if item_str.startswith('REF:'):
            ref_id = item_str[4:]  # remove "REF:" prefix
            # Look for this ref_id in global models for this category
            global_cat = global_models.get(category, [])
            found = False
            for global_item in global_cat:
                if isinstance(global_item, dict) and global_item.get('id') == ref_id:
                    # Extract the actual URN/URL
                    actual = global_item.get('urn') or global_item.get('url') or global_item.get('id')
                    if actual:
                        resolved.append(str(actual))
                        found = True
                        break
            if not found:
                print(f"[!] Warning: ref '{ref_id}' not found in models.{category}", file=sys.stderr)
        else:
            resolved.append(item_str)
    return ','.join(resolved) if resolved else None

# Build index of global models by ID for reference resolution
global_models_by_cat = {}
for cat, lst in models.items():
    if cat not in ('dest_dir', 'source_dir'):
        global_models_by_cat[cat] = lst or []

# Export model categories with reference resolution
for cat, lst in all_models.items():
    ids = extract_ids(lst if isinstance(lst, list) else None, global_models_by_cat)
    ids = resolve_refs(cat, ids, global_models_by_cat)
    if ids:
        export_var(f'CIVITAI_{cat.upper()}', ids)

# Custom nodes: global + workflow-specific
urls = []
# Global nodes
for node in data.get('custom_nodes', []):
    if isinstance(node, dict):
        url = node.get('url')
        if url:
            urls.append(str(url))

# Build index of global custom nodes by ID for reference resolution
global_custom_nodes = {}
for node in data.get('custom_nodes', []):
    if isinstance(node, dict) and node.get('id'):
        global_custom_nodes[node.get('id')] = node

# Resolve workflow-specific custom node references
resolved_workflow_nodes = []
for node_url in workflow_nodes:
    if node_url.startswith('REF:'):
        ref_id = node_url[4:]  # remove "REF:" prefix
        if ref_id in global_custom_nodes:
            actual_url = global_custom_nodes[ref_id].get('url')
            if actual_url:
                resolved_workflow_nodes.append(str(actual_url))
            else:
                print(f"[!] Warning: custom node ref '{ref_id}' has no url field", file=sys.stderr)
        else:
            print(f"[!] Warning: custom node ref '{ref_id}' not found in global custom_nodes", file=sys.stderr)
    else:
        resolved_workflow_nodes.append(node_url)

urls.extend(resolved_workflow_nodes)

export_var('YAML_CUSTOM_NODE_URLS', ' '.join(urls))
PY
)"
}

# Load YAML configuration now (overrides env where appropriate)
load_yaml_config

# -------------------------------------------------------------
# Variable defaults (may already be set via env or YAML)
# -------------------------------------------------------------

COMFY_DIR="${COMFY_DIR:-/workspace/ComfyUI}"
CPU_ONLY="${CPU_ONLY:-1}"
MODEL_DEST_DIR="${MODEL_DEST_DIR:-${COMFY_DIR}/models}"
MODELS_SOURCE_DIR="${MODELS_SOURCE_DIR:-}"  # optional

# Path to Python helper script
HELPER_PY="${SCRIPT_DIR}/download_civitai_models.py"

pkg_install() {
  if command -v apt-get >/dev/null 2>&1; then
    echo "[*] Installing system packages via apt-get..."
    apt-get update -y
    # shellcheck disable=SC2016
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      git ffmpeg libgl1 ca-certificates wget python3 python3-venv python3-distutils
  else
    echo "[!] apt-get not found. Please ensure Git, Python3, and other prerequisites are present."
  fi
}

clone_comfy() {
  if [[ -d "$COMFY_DIR/.git" ]]; then
    echo "[✓] ComfyUI already cloned at $COMFY_DIR - skipping clone"
  else
    echo "[*] Cloning ComfyUI into $COMFY_DIR..."
    git clone --depth=1 https://github.com/comfyanonymous/ComfyUI.git "$COMFY_DIR"
  fi
}

build_venv() {
  if [[ ! -d "$COMFY_DIR/venv" ]]; then
    echo "[*] Creating Python venv..."
    python3 -m venv "$COMFY_DIR/venv"
  fi
  # shellcheck source=/dev/null
  source "$COMFY_DIR/venv/bin/activate"
  echo "[*] Upgrading pip & wheel..."
  pip install --upgrade pip wheel setuptools
}

install_torch() {
  # Ensure python interpreter is available
  if ! command -v python &>/dev/null && ! command -v python3 &>/dev/null; then
    echo "[!] Python interpreter not found in PATH." >&2
    exit 1
  fi
  if [[ "$CPU_ONLY" == "1" ]]; then
    echo "[*] Installing CPU-only PyTorch..."
    pip install --index-url https://download.pytorch.org/whl/cpu \
      'torch>=2.1,<3' 'torchvision>=0.16,<1'
  else
    echo "[*] Installing CUDA-enabled PyTorch (cu121)..."
    pip install --extra-index-url https://download.pytorch.org/whl/cu121 \
      'torch>=2.1,<3' 'torchvision>=0.16,<1'
  fi
}

install_requirements() {
  echo "[*] Installing ComfyUI requirements..."
  pip install -r "$COMFY_DIR/requirements.txt" requests tqdm pyyaml
}

# -------------------------------------------------------------
# Custom nodes installer
# Handles both Git repositories and PyPI packages:
# - Git URLs (github.com, gitlab.com, etc.) are cloned into custom_nodes/
# - git+ prefixed URLs have the prefix stripped before cloning
# - Other URLs are treated as PyPI packages and pip installed
# - If a cloned repo has requirements.txt, those are installed too
# -------------------------------------------------------------
install_custom_nodes() {
  local urls="${YAML_CUSTOM_NODE_URLS:-}"  # Provided by load_yaml_config
  [[ -z "$urls" ]] && return 0

  echo "[*] Installing custom nodes from YAML config..."

  # Ensure custom_nodes directory exists
  mkdir -p "$COMFY_DIR/custom_nodes"

  for u in $urls; do
    echo "    → $u"
    
    # Check if this is a git URL (starts with git+ or contains github.com, etc.)
    if [[ "$u" =~ ^git\+ ]] || [[ "$u" =~ github\.com|gitlab\.com|bitbucket\.org ]]; then
      # Remove git+ prefix if present
      clean_url="${u#git+}"
      
      # Extract repository name for directory
      repo_name=$(basename "$clean_url" .git)
      target_dir="$COMFY_DIR/custom_nodes/$repo_name"
      
      if [[ -d "$target_dir" ]]; then
        echo "      ✓ Already exists at $target_dir"
      else
        echo "      Cloning into $target_dir..."
        git clone --depth=1 "$clean_url" "$target_dir"
        
        # Install requirements if they exist
        if [[ -f "$target_dir/requirements.txt" ]]; then
          echo "      Installing requirements for $repo_name..."
          # Activate venv if not already active
          # shellcheck disable=SC1090
          source "$COMFY_DIR/venv/bin/activate"
          pip install -r "$target_dir/requirements.txt"
        fi
      fi
    else
      # Treat as a PyPI package
      echo "      Installing PyPI package: $u"
      # Activate venv if not already active  
      # shellcheck disable=SC1090
      source "$COMFY_DIR/venv/bin/activate"
      pip install --no-cache-dir "$u"
    fi
  done
}

download_models() {
  if [[ -f "$HELPER_PY" ]]; then
    echo "[*] Running model download helper..."
    export CIVITAI_MODEL_DIR="$MODEL_DEST_DIR"
    # CIVITAI_API_KEY / CIVITAI_* variables are passed through env
    python "$HELPER_PY" || true
  else
    echo "[!] Helper script $HELPER_PY not found. Skipping Civitai downloads."
  fi
}

copy_local_models() {
  if [[ -n "$MODELS_SOURCE_DIR" ]]; then
    echo "[*] Copying local models from $MODELS_SOURCE_DIR -> $MODEL_DEST_DIR..."
    mkdir -p "$MODEL_DEST_DIR"
    rsync -av --progress "$MODELS_SOURCE_DIR"/ "$MODEL_DEST_DIR"/
  fi
}

main() {
  # ---------------------------------------------------------
  # Detect an existing installation and short-circuit if found
  # ---------------------------------------------------------
  if [[ -d "$COMFY_DIR/.git" && -f "$COMFY_DIR/venv/bin/python" ]]; then
    echo "[✓] ComfyUI already installed at $COMFY_DIR - nothing to do."
    echo "    $COMFY_DIR/venv/bin/python $COMFY_DIR/main.py --listen --port 8188"

    # We still allow installing/updating models or custom nodes even if ComfyUI exists.
    install_custom_nodes
    download_models
    copy_local_models

    if [[ "${AUTO_START:-0}" == "1" ]]; then
      echo "[*] AUTO_START=1 detected - launching ComfyUI..."
      exec "$COMFY_DIR/venv/bin/python" "$COMFY_DIR/main.py" --listen --port 8188
    fi
    return 0
  fi

  pkg_install
  clone_comfy
  build_venv
  install_torch
  install_requirements
  install_custom_nodes
  download_models
  copy_local_models
  echo "[✔] All done! To start ComfyUI run:"
  echo "     $COMFY_DIR/venv/bin/python $COMFY_DIR/main.py --listen --port 8188"

  # Optionally start ComfyUI immediately if AUTO_START=1
  if [[ "${AUTO_START:-0}" == "1" ]]; then
    echo "[*] AUTO_START=1 detected - launching ComfyUI..."
    exec "$COMFY_DIR/venv/bin/python" "$COMFY_DIR/main.py" --listen --port 8188
  fi
}

main "$@" 