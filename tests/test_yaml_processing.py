#!/usr/bin/env python3
"""Unit tests for YAML processing and reference resolution logic"""

import pathlib
import subprocess
import sys
import tempfile
from typing import Any
import unittest

try:
    import yaml
except ImportError:
    yaml = None


class TestYAMLProcessing(unittest.TestCase):
    """Test YAML configuration processing and reference resolution."""

    def setUp(self):
        """Set up test fixtures."""
        self.install_script = (
            pathlib.Path(__file__).parent.parent
            / "scripts"
            / "install_comfy_and_models.sh"
        )
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = pathlib.Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def write_config(self, data: dict[str, Any]) -> pathlib.Path:
        """Write a config dict to a temporary YAML file."""
        if yaml is None:
            self.skipTest("PyYAML not available")

        config_path = self.temp_path / "test_config.yml"
        config_path.write_text(yaml.dump(data))
        return config_path

    def run_yaml_processor(
        self, config_path: pathlib.Path, workflow: str = None
    ) -> dict[str, str]:
        """Run the YAML processing part of the installer and capture env vars."""
        # Create a small script that just runs the YAML processing part
        test_script = self.temp_path / "test_yaml.py"
        test_script.write_text(f'''
import sys
import os
sys.path.insert(0, "{self.install_script.parent}")

# Mock the CONFIG_FILE path
os.environ["CONFIG_FILE"] = "{config_path}"
if "{workflow}":
    os.environ["WORKFLOW"] = "{workflow}"

# Execute the YAML processing Python code from the installer
exec("""
import os
import sys
import yaml
import shlex
import pathlib

cfg_file = pathlib.Path(os.environ["CONFIG_FILE"])
data = yaml.safe_load(cfg_file.read_text()) or {{}}

def export_var(name, value):
    if value is None:
        return
    print(f"{{name}}={{shlex.quote(str(value))}}")

# Installation section overrides
install = data.get('install', {{}})
export_var('COMFY_DIR', install.get('comfy_dir'))
export_var('CPU_ONLY', int(bool(install.get('cpu_only', True))))

# Models section handling (supports arbitrary categories)
models = data.get('models', {{}})
export_var('MODEL_DEST_DIR', models.get('dest_dir'))
export_var('MODELS_SOURCE_DIR', models.get('source_dir'))

def extract_ids(lst, global_models=None):
    global_models = global_models or {{}}
    if not lst:
        return None
    out = []
    for item in lst:
        if isinstance(item, dict):
            if 'ref' in item:
                ref_id = item['ref']
                val = f"REF:{{ref_id}}"
            else:
                val = item.get('urn') or item.get('url') or item.get('id')
            if val:
                out.append(str(val))
        elif item:
            out.append(str(item))
    return ','.join(out) if out else None

def resolve_refs(category, items, global_models):
    resolved = []
    for item_str in (items or '').split(','):
        item_str = item_str.strip()
        if not item_str:
            continue
        if item_str.startswith('REF:'):
            ref_id = item_str[4:]
            global_cat = global_models.get(category, [])
            found = False
            for global_item in global_cat:
                if isinstance(global_item, dict) and global_item.get('id') == ref_id:
                    actual = global_item.get('urn') or global_item.get('url') or global_item.get('id')
                    if actual:
                        resolved.append(str(actual))
                        found = True
                        break
            if not found:
                print(f"WARNING_REF_NOT_FOUND:{{ref_id}}:{{category}}", file=sys.stderr)
        else:
            resolved.append(item_str)
    return ','.join(resolved) if resolved else None

# Handle workflow-specific dependencies
selected_workflow = os.getenv('WORKFLOW')
workflow_models = {{}}
workflow_nodes = []

if selected_workflow:
    workflows = data.get('workflows', [])
    for wf in workflows:
        if isinstance(wf, dict) and wf.get('name') == selected_workflow:
            print(f"SELECTED_WORKFLOW={{selected_workflow}}", file=sys.stderr)
            wf_models = wf.get('models', {{}})
            for cat, lst in wf_models.items():
                workflow_models[cat] = lst
            wf_nodes = wf.get('custom_nodes', [])
            for node in wf_nodes:
                if isinstance(node, dict) and node.get('url'):
                    workflow_nodes.append(node.get('url'))
            break
    else:
        print(f"WORKFLOW_NOT_FOUND:{{selected_workflow}}", file=sys.stderr)

# Merge global + workflow-specific models
all_models = {{}}
for cat, lst in models.items():
    if cat not in ('dest_dir', 'source_dir'):
        all_models[cat] = lst or []

for cat, lst in workflow_models.items():
    if cat in all_models:
        all_models[cat] = all_models[cat] + (lst or [])
    else:
        all_models[cat] = lst or []

# Build index of global models by ID for reference resolution
global_models_by_cat = {{}}
for cat, lst in models.items():
    if cat not in ('dest_dir', 'source_dir'):
        global_models_by_cat[cat] = lst or []

# Export model categories with reference resolution
for cat, lst in all_models.items():
    ids = extract_ids(lst if isinstance(lst, list) else None, global_models_by_cat)
    ids = resolve_refs(cat, ids, global_models_by_cat)
    if ids:
        export_var(f'CIVITAI_{{cat.upper()}}', ids)

# Custom nodes: global + workflow-specific
urls = []
for node in data.get('custom_nodes', []):
    if isinstance(node, dict):
        url = node.get('url')
        if url:
            urls.append(str(url))

urls.extend(workflow_nodes)
export_var('YAML_CUSTOM_NODE_URLS', ' '.join(urls))
""")
''')

        result = subprocess.run(
            [sys.executable, str(test_script)], capture_output=True, text=True
        )

        # Parse the output into a dict
        env_vars = {}
        warnings = []

        for line in result.stdout.strip().split("\n"):
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                # Remove quotes if present
                if (
                    value.startswith('"')
                    and value.endswith('"')
                    or value.startswith("'")
                    and value.endswith("'")
                ):
                    value = value[1:-1]
                env_vars[key] = value

        for line in result.stderr.strip().split("\n"):
            if line:
                warnings.append(line)

        env_vars["_WARNINGS"] = warnings
        return env_vars

    def test_basic_config_processing(self):
        """Test basic YAML config processing without workflows."""
        config = {
            "install": {"comfy_dir": "/custom/path", "cpu_only": False},
            "models": {
                "dest_dir": "/custom/models",
                "checkpoints": [
                    "urn:air:sdxl:checkpoint:civitai:12345",
                    {
                        "urn": "urn:air:sd1:checkpoint:civitai:67890",
                        "name": "Test Model",
                    },
                ],
                "loras": ["urn:air:sd1:lora:civitai:11111"],
            },
            "custom_nodes": [
                {"name": "TestNode", "url": "git+https://github.com/test/node.git"}
            ],
        }

        config_path = self.write_config(config)
        env_vars = self.run_yaml_processor(config_path)

        self.assertEqual(env_vars.get("COMFY_DIR"), "/custom/path")
        self.assertEqual(env_vars.get("CPU_ONLY"), "0")  # False becomes 0
        self.assertEqual(env_vars.get("MODEL_DEST_DIR"), "/custom/models")
        self.assertIn(
            "urn:air:sdxl:checkpoint:civitai:12345",
            env_vars.get("CIVITAI_CHECKPOINTS", ""),
        )
        self.assertIn(
            "urn:air:sd1:checkpoint:civitai:67890",
            env_vars.get("CIVITAI_CHECKPOINTS", ""),
        )
        self.assertEqual(
            env_vars.get("CIVITAI_LORAS"), "urn:air:sd1:lora:civitai:11111"
        )
        self.assertEqual(
            env_vars.get("YAML_CUSTOM_NODE_URLS"),
            "git+https://github.com/test/node.git",
        )

    def test_reference_resolution(self):
        """Test that model references are resolved correctly."""
        config = {
            "models": {
                "checkpoints": [
                    {
                        "id": "sdxl-base",
                        "urn": "urn:air:sdxl:checkpoint:civitai:12345",
                        "name": "SDXL Base",
                    },
                    {
                        "id": "realistic-vision",
                        "urn": "urn:air:sd1:checkpoint:civitai:67890",
                    },
                ]
            },
            "workflows": [
                {
                    "name": "Test Workflow",
                    "models": {
                        "checkpoints": [
                            {"ref": "sdxl-base"},
                            {"ref": "realistic-vision"},
                        ]
                    },
                }
            ],
        }

        config_path = self.write_config(config)
        env_vars = self.run_yaml_processor(config_path, workflow="Test Workflow")

        # Should contain both global and workflow checkpoints (resolved from refs)
        checkpoints = env_vars.get("CIVITAI_CHECKPOINTS", "")
        self.assertIn("urn:air:sdxl:checkpoint:civitai:12345", checkpoints)
        self.assertIn("urn:air:sd1:checkpoint:civitai:67890", checkpoints)

        # Should show workflow was selected
        warnings = env_vars.get("_WARNINGS", [])
        self.assertTrue(any("SELECTED_WORKFLOW=Test Workflow" in w for w in warnings))

    def test_invalid_reference(self):
        """Test handling of invalid references."""
        config = {
            "models": {
                "checkpoints": [
                    {
                        "id": "existing-model",
                        "urn": "urn:air:sdxl:checkpoint:civitai:12345",
                    }
                ]
            },
            "workflows": [
                {
                    "name": "Test Workflow",
                    "models": {"checkpoints": [{"ref": "non-existent-model"}]},
                }
            ],
        }

        config_path = self.write_config(config)
        env_vars = self.run_yaml_processor(config_path, workflow="Test Workflow")

        # Should show warning about missing reference
        warnings = env_vars.get("_WARNINGS", [])
        self.assertTrue(
            any(
                "WARNING_REF_NOT_FOUND:non-existent-model:checkpoints" in w
                for w in warnings
            )
        )

    def test_workflow_not_found(self):
        """Test handling when requested workflow doesn't exist."""
        config = {"workflows": [{"name": "Existing Workflow"}]}

        config_path = self.write_config(config)
        env_vars = self.run_yaml_processor(
            config_path, workflow="Non-existent Workflow"
        )

        warnings = env_vars.get("_WARNINGS", [])
        self.assertTrue(
            any("WORKFLOW_NOT_FOUND:Non-existent Workflow" in w for w in warnings)
        )

    def test_workflow_merging(self):
        """Test that workflow-specific models are merged with global ones."""
        config = {
            "models": {
                "checkpoints": [
                    {
                        "id": "global-model",
                        "urn": "urn:air:sdxl:checkpoint:civitai:11111",
                    }
                ]
            },
            "custom_nodes": [
                {"name": "GlobalNode", "url": "git+https://github.com/global/node.git"}
            ],
            "workflows": [
                {
                    "name": "Test Workflow",
                    "models": {
                        "checkpoints": [{"ref": "global-model"}],
                        "loras": ["urn:air:sd1:lora:civitai:22222"],
                    },
                    "custom_nodes": [
                        {
                            "name": "WorkflowNode",
                            "url": "git+https://github.com/workflow/node.git",
                        }
                    ],
                }
            ],
        }

        config_path = self.write_config(config)
        env_vars = self.run_yaml_processor(config_path, workflow="Test Workflow")

        # Should have both global and workflow-specific content
        checkpoints = env_vars.get("CIVITAI_CHECKPOINTS", "")
        self.assertIn(
            "urn:air:sdxl:checkpoint:civitai:11111", checkpoints
        )  # Global + workflow ref

        loras = env_vars.get("CIVITAI_LORAS", "")
        self.assertEqual(loras, "urn:air:sd1:lora:civitai:22222")  # Workflow only

        nodes = env_vars.get("YAML_CUSTOM_NODE_URLS", "")
        self.assertIn("git+https://github.com/global/node.git", nodes)
        self.assertIn("git+https://github.com/workflow/node.git", nodes)

    def test_arbitrary_model_categories(self):
        """Test that arbitrary model categories are supported."""
        config = {
            "models": {
                "vae": ["urn:air:sdxl:vae:civitai:11111"],
                "embeddings": [
                    {
                        "urn": "urn:air:sd1:embedding:civitai:22222",
                        "name": "Test Embedding",
                    }
                ],
                "upscale_models": ["urn:air:universal:upscale:civitai:33333"],
            }
        }

        config_path = self.write_config(config)
        env_vars = self.run_yaml_processor(config_path)

        self.assertEqual(env_vars.get("CIVITAI_VAE"), "urn:air:sdxl:vae:civitai:11111")
        self.assertEqual(
            env_vars.get("CIVITAI_EMBEDDINGS"), "urn:air:sd1:embedding:civitai:22222"
        )
        self.assertEqual(
            env_vars.get("CIVITAI_UPSCALE_MODELS"),
            "urn:air:universal:upscale:civitai:33333",
        )


if __name__ == "__main__":
    unittest.main()
