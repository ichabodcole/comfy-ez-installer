#!/usr/bin/env python3
"""Validate a ComfyUI installer YAML configuration.

Exit code 0 → valid, 1 → validation errors, 2 → fatal error (e.g. file unreadable).
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    print(
        "[!] PyYAML is required for validation but is not installed.", file=sys.stderr
    )
    sys.exit(2)

CONFIG_PATH = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
if not CONFIG_PATH or not CONFIG_PATH.is_file():
    print("[!] Please supply a valid path to config.yml", file=sys.stderr)
    sys.exit(2)

try:
    data: dict[str, Any] = yaml.safe_load(CONFIG_PATH.read_text()) or {}
except yaml.YAMLError as exc:
    print(f"[!] YAML parsing error: {exc}", file=sys.stderr)
    sys.exit(1)

errors: list[str] = []

# Allowed top-level keys
allowed_top = {"install", "models", "custom_nodes", "workflows"}
for key in data:
    if key not in allowed_top:
        errors.append(f"Unknown top-level key: {key}")

install = data.get("install", {}) or {}
if not isinstance(install, dict):
    errors.append("install section must be a mapping")
else:
    for k in install:
        if k not in {"comfy_dir", "cpu_only"}:
            errors.append(f"install: unknown key {k}")
    if "cpu_only" in install and not isinstance(install["cpu_only"], bool):
        errors.append("install.cpu_only must be boolean")

models = data.get("models", {}) or {}
if not isinstance(models, dict):
    errors.append("models section must be a mapping")
else:
    for k, v in models.items():
        if k in {"dest_dir", "source_dir"}:
            continue
        if not isinstance(v, list):
            errors.append(f"models.{k} must be a list")
            continue
        for idx, item in enumerate(v):
            if isinstance(item, str):
                continue
            if isinstance(item, dict):
                has_content = any(key in item for key in ("urn", "url", "id", "ref"))
                if not has_content:
                    errors.append(
                        f"models.{k}[{idx}] must have 'urn', 'url', 'id', or 'ref' field"
                    )
                # Check for conflicting fields
                if "ref" in item and any(key in item for key in ("urn", "url", "id")):
                    errors.append(
                        f"models.{k}[{idx}] cannot have both 'ref' and direct content fields"
                    )
            else:
                errors.append(f"models.{k}[{idx}] must be str or mapping")

custom_nodes = data.get("custom_nodes", [])
if custom_nodes and not isinstance(custom_nodes, list):
    errors.append("custom_nodes must be a list")
else:
    for idx, node in enumerate(custom_nodes or []):
        if not isinstance(node, dict):
            errors.append(f"custom_nodes[{idx}] must be mapping with 'url' or 'id'")
            continue
        # Custom nodes can have url for direct references or id for global definitions
        if "url" not in node and "id" not in node:
            errors.append(f"custom_nodes[{idx}] missing 'url' or 'id' field")

workflows = data.get("workflows", [])
if workflows and not isinstance(workflows, list):
    errors.append("workflows must be a list")
else:
    for idx, wf in enumerate(workflows or []):
        if not isinstance(wf, dict):
            errors.append(f"workflows[{idx}] must be mapping")
            continue
        if "name" not in wf:
            errors.append(f"workflows[{idx}] missing 'name' field")

        # Validate workflow models section (same rules as global models)
        wf_models = wf.get("models", {})
        if wf_models and not isinstance(wf_models, dict):
            errors.append(f"workflows[{idx}].models must be a mapping")
        else:
            for k, v in wf_models.items():
                if not isinstance(v, list):
                    errors.append(f"workflows[{idx}].models.{k} must be a list")
                    continue
                for item_idx, item in enumerate(v):
                    if isinstance(item, str):
                        continue
                    if isinstance(item, dict):
                        has_content = any(
                            key in item for key in ("urn", "url", "id", "ref")
                        )
                        if not has_content:
                            errors.append(
                                f"workflows[{idx}].models.{k}[{item_idx}] must have 'urn', 'url', 'id', or 'ref' field"
                            )
                        # Check for conflicting fields
                        if "ref" in item and any(
                            key in item for key in ("urn", "url", "id")
                        ):
                            errors.append(
                                f"workflows[{idx}].models.{k}[{item_idx}] cannot have both 'ref' and direct content fields"
                            )
                    else:
                        errors.append(
                            f"workflows[{idx}].models.{k}[{item_idx}] must be str or mapping"
                        )

        # Validate workflow custom_nodes
        wf_nodes = wf.get("custom_nodes", [])
        if wf_nodes and not isinstance(wf_nodes, list):
            errors.append(f"workflows[{idx}].custom_nodes must be a list")
        else:
            for node_idx, node in enumerate(wf_nodes or []):
                if not isinstance(node, dict):
                    errors.append(
                        f"workflows[{idx}].custom_nodes[{node_idx}] must be mapping with 'url' or 'ref'"
                    )
                    continue
                has_content = any(key in node for key in ("url", "ref"))
                if not has_content:
                    errors.append(
                        f"workflows[{idx}].custom_nodes[{node_idx}] missing 'url' or 'ref' field"
                    )
                # Check for conflicting fields
                if "ref" in node and "url" in node:
                    errors.append(
                        f"workflows[{idx}].custom_nodes[{node_idx}] cannot have both 'ref' and 'url' fields"
                    )

# Validate that all refs point to existing IDs
models = data.get("models", {}) or {}
custom_nodes = data.get("custom_nodes", []) or []
workflows = data.get("workflows", []) or []

# Build index of available IDs by category
available_ids = {}
for cat, lst in models.items():
    if cat in ("dest_dir", "source_dir"):
        continue
    available_ids[cat] = set()
    for item in lst or []:
        if isinstance(item, dict) and "id" in item:
            available_ids[cat].add(item["id"])

# Build index of available custom node IDs
available_custom_node_ids = set()
for node in custom_nodes:
    if isinstance(node, dict) and "id" in node:
        available_custom_node_ids.add(node["id"])

# Check workflow refs
for wf_idx, wf in enumerate(workflows):
    if not isinstance(wf, dict):
        continue
    wf_models = wf.get("models", {}) or {}
    for cat, lst in wf_models.items():
        for item_idx, item in enumerate(lst or []):
            if isinstance(item, dict) and "ref" in item:
                ref_id = item["ref"]
                if cat not in available_ids or ref_id not in available_ids[cat]:
                    errors.append(
                        f"workflows[{wf_idx}].models.{cat}[{item_idx}] ref '{ref_id}' not found in models.{cat}"
                    )
    
    # Check custom node refs
    wf_nodes = wf.get("custom_nodes", []) or []
    for node_idx, node in enumerate(wf_nodes):
        if isinstance(node, dict) and "ref" in node:
            ref_id = node["ref"]
            if ref_id not in available_custom_node_ids:
                errors.append(
                    f"workflows[{wf_idx}].custom_nodes[{node_idx}] ref '{ref_id}' not found in global custom_nodes"
                )

if errors:
    print("[!] Configuration validation failed:")
    for err in errors:
        print(f"  - {err}")
    sys.exit(1)

print("[✓] config.yml passed validation")
