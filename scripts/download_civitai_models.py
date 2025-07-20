#!/usr/bin/env python3
"""Download specified Civitai models into the ComfyUI models directory.

Can be used via command line arguments or environment variables.

Command line usage:
    python download_civitai_models.py --api-key YOUR_KEY --dest-dir /path/to/models \\
        --checkpoints "model1,model2" --loras "lora1,lora2"

Environment variable usage (for backward compatibility):
    CIVITAI_API_KEY=your_key CIVITAI_CHECKPOINTS="model1,model2" python download_civitai_models.py

The script is idempotent: it skips files that already exist locally.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from urllib.parse import urlparse

import requests

from tqdm import tqdm


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Download Civitai models to ComfyUI models directory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download checkpoints and LoRAs
  %(prog)s --api-key YOUR_KEY --checkpoints "model1,model2" --loras "lora1"
  
  # Use URNs with specific versions
  %(prog)s --api-key YOUR_KEY --checkpoints "urn:air:sdxl:checkpoint:civitai:443821@1928679"
  
  # Mix of formats
  %(prog)s --api-key YOUR_KEY --checkpoints "443821,urn:air:sdxl:checkpoint:civitai:1125067@1803585"
        """,
    )
    
    parser.add_argument(
        "--api-key",
        help="Civitai API key (can also use CIVITAI_API_KEY env var)",
        default=os.getenv("CIVITAI_API_KEY"),
    )
    
    parser.add_argument(
        "--dest-dir",
        type=pathlib.Path,
        help="Destination directory for models (default: %(default)s)",
        default=pathlib.Path(os.getenv("CIVITAI_MODEL_DIR", "/home/comfyuser/ComfyUI/models")),
    )
    
    parser.add_argument(
        "--download-threads",
        type=int,
        help="Number of concurrent download threads (default: %(default)s)",
        default=int(os.getenv("CIVITAI_DOWNLOAD_THREADS", "3")),
    )
    
    # Model category arguments
    parser.add_argument(
        "--checkpoints",
        help="Comma-separated list of checkpoint models to download",
        default=os.getenv("CIVITAI_CHECKPOINTS", ""),
    )
    
    parser.add_argument(
        "--loras",
        help="Comma-separated list of LoRA models to download", 
        default=os.getenv("CIVITAI_LORAS", ""),
    )
    
    parser.add_argument(
        "--embeddings",
        help="Comma-separated list of embedding models to download",
        default=os.getenv("CIVITAI_EMBEDDINGS", ""),
    )
    
    parser.add_argument(
        "--vae",
        help="Comma-separated list of VAE models to download",
        default=os.getenv("CIVITAI_VAE", ""),
    )
    
    parser.add_argument(
        "--controlnets",
        help="Comma-separated list of ControlNet models to download",
        default=os.getenv("CIVITAI_CONTROLNETS", ""),
    )
    
    parser.add_argument(
        "--upscalers",
        help="Comma-separated list of upscaler models to download",
        default=os.getenv("CIVITAI_UPSCALERS", ""),
    )
    
    # Also support arbitrary categories via environment variables for backward compatibility
    parser.add_argument(
        "--from-env",
        action="store_true",
        help="Also scan environment variables for CIVITAI_* model categories",
        default=True,
    )
    
    return parser.parse_args()


def get_model_entries_from_args(args: argparse.Namespace) -> list[tuple[str, pathlib.Path]]:
    """Build model entries list from command line arguments."""
    entries: list[tuple[str, pathlib.Path]] = []
    
    # Process explicit category arguments
    categories = {
        "checkpoints": args.checkpoints,
        "loras": args.loras, 
        "embeddings": args.embeddings,
        "vae": args.vae,
        "controlnets": args.controlnets,
        "upscalers": args.upscalers,
    }
    
    for category, models_str in categories.items():
        if not models_str.strip():
            continue
            
        dest_dir = args.dest_dir / category
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        for item in models_str.split(","):
            item = item.strip()
            if item:
                entries.append((item, dest_dir))
    
    # Also scan environment variables if requested (for backward compatibility)
    if args.from_env:
        for env_key, value in os.environ.items():
            if not env_key.startswith("CIVITAI_"):
                continue
            if env_key in {"CIVITAI_API_KEY", "CIVITAI_MODEL_DIR", "CIVITAI_DOWNLOAD_THREADS"}:
                continue
            
            # Skip categories already handled by explicit arguments
            category = env_key[len("CIVITAI_"):].lower()
            if category in categories:
                continue
                
            raw = value.strip()
            if not raw:
                continue
                
            dest_dir = args.dest_dir / category
            dest_dir.mkdir(parents=True, exist_ok=True)
            for item in raw.split(","):
                item = item.strip()
                if item:
                    entries.append((item, dest_dir))
    
    return entries


def get_download_threads():
    """Get the number of download threads from environment (for backward compatibility)."""
    return max(1, int(os.getenv("CIVITAI_DOWNLOAD_THREADS", "4")))


def parse_urn(urn: str) -> dict | None:
    """Parse a URN into its components."""
    if not urn.startswith("urn:air:"):
        return None

    try:
        parts = urn.split(":")
        if len(parts) != 6:
            return None

        _, namespace, model_type, category, platform, model_id = parts
        if namespace != "air" or not model_id.strip():
            return None

        return {
            "model_type": model_type,
            "category": category,
            "platform": platform,
            "model_id": model_id,
        }
    except (ValueError, IndexError):
        return None


def is_direct_url(url: str) -> bool:
    """Check if the given string is a direct HTTP/HTTPS URL."""
    return url.startswith(("http://", "https://"))


def get_filename_from_url(url: str) -> str:
    """Extract filename from URL."""
    parsed = urlparse(url)
    filename = pathlib.Path(parsed.path).name
    return filename if filename else "download"


def download_direct_url(url: str, dest_path: pathlib.Path) -> bool:
    """Download from direct URL to destination path."""
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=30) as resp:
            if resp.status_code != 200:
                return False
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return True
    except requests.RequestException:
        return False


def get_civitai_model_info(model_id: str) -> dict | None:
    """Get model info from Civitai API."""
    url = f"https://civitai.com/api/v1/models/{model_id}"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            return None

        data = resp.json()
        versions = data.get("modelVersions", [])
        if not versions:
            return None

        version = versions[0]  # Latest version
        files = version.get("files", [])
        if not files:
            return None

        file_info = files[0]  # First file
        return {
            "filename": file_info.get("name"),
            "download_url": file_info.get("downloadUrl"),
        }
    except requests.RequestException:
        return None


def get_model_dest_path(
    models_dir: pathlib.Path, model_spec: str, filename: str
) -> pathlib.Path:
    """Get destination path for a model."""
    parsed = parse_urn(model_spec)
    if parsed:
        category = parsed["category"]
        # Add 's' to make it plural like in the actual script
        if not category.endswith("s"):
            category += "s"
        return models_dir / category / filename
    else:
        # Direct URL, save to root models dir
        return models_dir / filename


def download_model(models_dir: pathlib.Path, model_spec: str) -> bool:
    """Download a single model specified by URN or direct URL.
    
    NOTE: This function is deprecated and only kept for testing.
    The main implementation now uses process_model_entry() which has
    better support for version specifiers in URNs.
    """
    if is_direct_url(model_spec):
        filename = get_filename_from_url(model_spec)
        dest_path = get_model_dest_path(models_dir, model_spec, filename)

        if dest_path.exists():
            return True  # Already exists

        return download_direct_url(model_spec, dest_path)
    else:
        # Civitai URN
        parsed = parse_urn(model_spec)
        if not parsed:
            return False

        model_id = parsed["model_id"]
        info = get_civitai_model_info(model_id)
        if not info:
            return False

        filename = info["filename"]
        download_url = info["download_url"]
        dest_path = get_model_dest_path(models_dir, model_spec, filename)

        if dest_path.exists():
            return True  # Already exists

        return download_direct_url(download_url, dest_path)


def main():
    """Main download function."""
    args = parse_arguments()
    
    # Get model entries from command line arguments
    entries = get_model_entries_from_args(args)
    
    # Exit early if nothing to do
    if not entries:
        print("[*] No models specified for download")
        print("Use --help to see available options")
        return
    
    if not args.api_key:
        print("[!] No API key provided. Use --api-key or set CIVITAI_API_KEY environment variable")
        sys.exit(1)

    print(f"[*] Starting download of {len(entries)} model(s)...")
    print(f"[*] Destination directory: {args.dest_dir}")
    
    # Set up global headers with the API key
    global headers
    headers = {
        "Authorization": f"Bearer {args.api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    # Use the robust process_model_entry function for each entry
    for entry, dest_dir in entries:
        process_model_entry(entry, dest_dir)
    
    print("[✔] Model download process completed.")
    return


# Headers will be set in main() after parsing API key from arguments
headers = {}

# -------------------------------------------------------------
# Concurrency settings
# -------------------------------------------------------------
# You can control how many simultaneous downloads are performed
# by setting the environment variable CIVITAI_DOWNLOAD_THREADS.
# Default is 4. Set to 1 to disable concurrent downloading.
# -------------------------------------------------------------
MAX_WORKERS = max(1, int(os.getenv("CIVITAI_DOWNLOAD_THREADS", "3")))

session = requests.Session()
session.headers.update(headers)


def fetch_model_info(model_id: str) -> dict | None:
    """Return JSON metadata for the given model_id, or None on error."""
    url = f"https://civitai.com/api/v1/models/{model_id}"
    try:
        r = requests.get(url, headers=headers, timeout=30)
    except requests.RequestException as exc:
        print(f"[!] Network error fetching model {model_id}: {exc}")
        return None

    if r.status_code != 200:
        print(f"[!] Failed to fetch model {model_id}: {r.status_code} {r.text}")
        return None
    return r.json()


def download_file(url: str, dest: pathlib.Path):
    """Download file from url to dest with progress bar."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers=headers, stream=True) as resp:
        resp.raise_for_status()
        total_size = int(resp.headers.get("content-length", 0))
        with open(dest, "wb") as f, tqdm(total=total_size, unit="B", unit_scale=True, desc=dest.name) as bar:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    bar.update(len(chunk))


def _parse_model_spec(spec: str) -> tuple[str, str | None]:
    """Return (model_id, version_id) from various input formats.

    Accepts:
    • "1234"                      → ("1234", None)
    • "1234:9876"                 → ("1234", "9876")
    • "urn:air:...:civitai:ID"    → ("ID", None)
    • "urn:air:...:civitai:ID@VER"→ ("ID", "VER")
    """
    spec = spec.strip()
    if spec.startswith("urn:air:"):
        # Example: urn:air:sdxl:embedding:civitai:1309512@1477814
        try:
            # Split by ':' and find the segment after 'civitai'
            parts = spec.split(":")
            civ_index = parts.index("civitai")
            id_ver = parts[civ_index + 1]
            if "@" in id_ver:
                model_id, version_id = id_ver.split("@", 1)
            else:
                model_id, version_id = id_ver, None
            return model_id, version_id
        except (ValueError, IndexError):
            # Malformed URN; fall through to generic handling
            print(
                f"[!] Unable to parse AIR URN '{spec}', expected format …:civitai:<id>[@<version>]"
            )
            return spec, None
    # Fallback to original `id[:version]` format
    if ":" in spec:
        return tuple(spec.split(":", 1))  # type: ignore
    return spec, None


def process_model_entry(entry: str, dest_dir: pathlib.Path):
    """Download one model entry (URN/ID or direct URL) into dest_dir."""

    # Direct HTTP(S) link → download as-is
    if entry.startswith(("http://", "https://")):
        parsed = urlparse(entry)
        filename = pathlib.Path(parsed.path).name or "model"
        dest_path = dest_dir / filename
        if dest_path.exists():
            print(f"[✓] {filename} already exists, skipping")
            return
        print(f"[*] Downloading direct URL {filename}")
        try:
            download_file(entry, dest_path)
            print(f"[✓] Saved to {dest_path}")
        except requests.RequestException as exc:
            print(f"[!] Error downloading {entry}: {exc}")
            if dest_path.exists():
                dest_path.unlink(missing_ok=True)
        return

    # Otherwise treat as Civitai model spec
    model_id, version_id = _parse_model_spec(entry)

    data = fetch_model_info(model_id)
    if not data:
        return

    # Determine version to use
    versions = data.get("modelVersions", [])
    if not versions:
        print(f"[!] No versions found for model {model_id}")
        return

    version_data: dict | None = None
    if version_id:
        version_data = next(
            (v for v in versions if str(v.get("id")) == version_id), None
        )
        if not version_data:
            print(
                f"[!] Version {version_id} not found for model {model_id}; falling back to latest"
            )
    if version_data is None:
        version_data = versions[0]  # latest (API returns latest first)

    # Download every file associated with this version
    for file_info in version_data.get("files", []):
        url = file_info.get("downloadUrl")
        name = file_info.get("name")
        if not url or not name:
            continue
        dest_path = dest_dir / name
        if dest_path.exists():
            print(f"[✓] {name} already exists, skipping")
            continue
        print(f"[*] Downloading {name} (model {model_id})")
        try:
            download_file(url, dest_path)
            print(f"[✓] Saved to {dest_path}")
        except requests.RequestException as exc:
            print(f"[!] Error downloading {name}: {exc}")
            if dest_path.exists():
                dest_path.unlink(missing_ok=True)

    # -------------------------------------------------------------
    # Kick off downloads (possibly concurrently) - OLD LOGIC
    # -------------------------------------------------------------
    # This is the original download logic, now replaced by the main() function
    # using download_model() for consistency with tests
    #
    # if MAX_WORKERS == 1 or len(entries) <= 1:
    #     for entry, dest in entries:
    #         process_model_entry(entry, dest)
    # else:
    #     print(f"[*] Downloading using up to {MAX_WORKERS} parallel workers…")
    #     with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    #         future_map = {executor.submit(process_model_entry, entry, dest): (entry, dest) for entry, dest in entries}
    #         for future in as_completed(future_map):
    #             # Exceptions raised inside threads will be re-raised here.
    #             try:
    #                 future.result()
    #             except Exception as exc:
    #                 entry, _ = future_map[future]
    #                 print(f"[!] Error processing entry {entry}: {exc}")
    #
    #     print("[✔] Model download process completed.")


if __name__ == "__main__":
    main()
