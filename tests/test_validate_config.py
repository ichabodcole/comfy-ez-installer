#!/usr/bin/env python3
"""Unit tests for validate_config.py"""

import pathlib
import subprocess
import sys
import tempfile
from typing import Any
import unittest

# Add the scripts directory to the path so we can import the validation logic
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

try:
    import yaml
except ImportError:
    yaml = None


class TestConfigValidation(unittest.TestCase):
    """Test the configuration validation script."""

    def setUp(self):
        """Set up test fixtures."""
        self.script_path = (
            pathlib.Path(__file__).parent.parent / "scripts" / "validate_config.py"
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

    def run_validator(self, config_path: pathlib.Path) -> tuple[int, str, str]:
        """Run the validator script and return (exit_code, stdout, stderr)."""
        result = subprocess.run(
            [sys.executable, str(self.script_path), str(config_path)],
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout, result.stderr

    def test_valid_minimal_config(self):
        """Test that a minimal valid config passes."""
        config = {}
        config_path = self.write_config(config)
        exit_code, stdout, stderr = self.run_validator(config_path)

        self.assertEqual(exit_code, 0)
        self.assertIn("passed validation", stdout)

    def test_valid_full_config(self):
        """Test that a complete valid config passes."""
        config = {
            "install": {"comfy_dir": "/workspace/ComfyUI", "cpu_only": True},
            "models": {
                "dest_dir": "/workspace/models",
                "source_dir": "/host/models",
                "checkpoints": [
                    {
                        "id": "sdxl-base",
                        "urn": "urn:air:sdxl:checkpoint:civitai:12345",
                        "name": "SDXL Base",
                    }
                ],
                "loras": ["urn:air:sd1:lora:civitai:98765"],
            },
            "custom_nodes": [
                {
                    "name": "ControlNet",
                    "url": "git+https://github.com/example/controlnet.git",
                }
            ],
            "workflows": [
                {
                    "name": "Test Workflow",
                    "models": {"checkpoints": [{"ref": "sdxl-base"}]},
                    "custom_nodes": [
                        {
                            "name": "WorkflowNode",
                            "url": "git+https://github.com/example/workflow-node.git",
                        }
                    ],
                }
            ],
        }
        config_path = self.write_config(config)
        exit_code, stdout, stderr = self.run_validator(config_path)

        self.assertEqual(exit_code, 0)
        self.assertIn("passed validation", stdout)

    def test_invalid_top_level_key(self):
        """Test that unknown top-level keys are rejected."""
        config = {"invalid_key": "value"}
        config_path = self.write_config(config)
        exit_code, stdout, stderr = self.run_validator(config_path)

        self.assertEqual(exit_code, 1)
        self.assertIn("Unknown top-level key: invalid_key", stdout)

    def test_invalid_install_section(self):
        """Test validation of install section."""
        config = {"install": {"cpu_only": "not_a_boolean", "unknown_field": "value"}}
        config_path = self.write_config(config)
        exit_code, stdout, stderr = self.run_validator(config_path)

        self.assertEqual(exit_code, 1)
        self.assertIn("install.cpu_only must be boolean", stdout)
        self.assertIn("install: unknown key unknown_field", stdout)

    def test_invalid_models_structure(self):
        """Test validation of models section."""
        config = {
            "models": {
                "checkpoints": [
                    {"name": "missing urn/url/id"}  # Missing required field
                ]
            }
        }
        config_path = self.write_config(config)
        exit_code, stdout, stderr = self.run_validator(config_path)

        self.assertEqual(exit_code, 1)
        self.assertIn("must have 'urn', 'url', 'id', or 'ref' field", stdout)

    def test_conflicting_ref_and_direct_fields(self):
        """Test that ref cannot be mixed with direct content fields."""
        config = {
            "models": {
                "checkpoints": [
                    {
                        "ref": "some-ref",
                        "urn": "urn:air:sdxl:checkpoint:civitai:12345",  # Conflict!
                    }
                ]
            }
        }
        config_path = self.write_config(config)
        exit_code, stdout, stderr = self.run_validator(config_path)

        self.assertEqual(exit_code, 1)
        self.assertIn("cannot have both 'ref' and direct content fields", stdout)

    def test_invalid_workflow_ref(self):
        """Test that workflow refs must point to existing IDs."""
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
                    "models": {
                        "checkpoints": [
                            {"ref": "non-existent-model"}  # This ref doesn't exist
                        ]
                    },
                }
            ],
        }
        config_path = self.write_config(config)
        exit_code, stdout, stderr = self.run_validator(config_path)

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "ref 'non-existent-model' not found in models.checkpoints", stdout
        )

    def test_missing_workflow_name(self):
        """Test that workflows must have a name field."""
        config = {"workflows": [{"description": "Missing name field"}]}
        config_path = self.write_config(config)
        exit_code, stdout, stderr = self.run_validator(config_path)

        self.assertEqual(exit_code, 1)
        self.assertIn("missing 'name' field", stdout)

    def test_invalid_custom_nodes(self):
        """Test validation of custom_nodes section."""
        config = {
            "custom_nodes": [
                {"name": "Missing URL"}  # Missing required url field
            ]
        }
        config_path = self.write_config(config)
        exit_code, stdout, stderr = self.run_validator(config_path)

        self.assertEqual(exit_code, 1)
        self.assertIn("missing 'url' field", stdout)

    def test_nonexistent_file(self):
        """Test handling of non-existent config file."""
        nonexistent_path = self.temp_path / "does_not_exist.yml"
        exit_code, stdout, stderr = self.run_validator(nonexistent_path)

        self.assertEqual(exit_code, 2)
        self.assertIn("Please supply a valid path", stderr)

    def test_invalid_yaml(self):
        """Test handling of malformed YAML."""
        config_path = self.temp_path / "invalid.yml"
        config_path.write_text("invalid: yaml: content: [")  # Malformed YAML
        exit_code, stdout, stderr = self.run_validator(config_path)

        self.assertEqual(exit_code, 1)
        self.assertIn("YAML parsing error", stderr)


if __name__ == "__main__":
    unittest.main()
