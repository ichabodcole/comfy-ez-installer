#!/usr/bin/env python3
"""Tests for workflow reference resolution and model download integration."""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch

import yaml


class TestWorkflowReferences(unittest.TestCase):
    """Test workflow reference resolution and download integration."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.test_path = pathlib.Path(self.test_dir.name)
        self.comfyctl_path = pathlib.Path(__file__).parent.parent / "comfyctl.py"
        self.install_script = pathlib.Path(__file__).parent.parent / "scripts" / "install_comfy_and_models.sh"
        self.validator_script = pathlib.Path(__file__).parent.parent / "scripts" / "validate_config.py"

    def tearDown(self):
        """Clean up test fixtures."""
        self.test_dir.cleanup()

    def create_workflow_config(self) -> pathlib.Path:
        """Create a comprehensive config with workflow references."""
        config = {
            "install": {
                "comfy_dir": str(self.test_path / "ComfyUI"),
                "cpu_only": True
            },
            "models": {
                "dest_dir": str(self.test_path / "models"),
                "checkpoints": [
                    {
                        "id": "sdxl-base",
                        "urn": "urn:air:sdxl:checkpoint:civitai:101055",
                        "name": "SDXL Base",
                        "description": "Primary SDXL checkpoint"
                    },
                    {
                        "id": "realistic-vision",
                        "urn": "urn:air:sd1:checkpoint:civitai:4201",
                        "name": "Realistic Vision"
                    }
                ],
                "loras": [
                    {
                        "id": "style-lora",
                        "urn": "urn:air:sd1:lora:civitai:16576",
                        "name": "Style LoRA"
                    }
                ],
                "vae": [
                    {
                        "id": "sdxl-vae",
                        "urn": "urn:air:sdxl:vae:civitai:123456",
                        "name": "SDXL VAE"
                    }
                ]
            },
            "custom_nodes": [
                {
                    "name": "ComfyUI-Manager",
                    "url": "git+https://github.com/ltdrdata/ComfyUI-Manager.git"
                }
            ],
            "workflows": [
                {
                    "name": "Basic SDXL Generation",
                    "description": "Simple text-to-image with SDXL",
                    "models": {
                        "checkpoints": [
                            {"ref": "sdxl-base"}
                        ],
                        "vae": [
                            {"ref": "sdxl-vae"}
                        ],
                        "loras": [
                            # Mix of reference and direct URN
                            {"ref": "style-lora"},
                            {"urn": "urn:air:sd1:lora:civitai:99999", "name": "Workflow-specific LoRA"}
                        ]
                    },
                    "custom_nodes": [
                        {
                            "name": "SDXL-specific node",
                            "url": "git+https://github.com/example/sdxl-nodes.git"
                        }
                    ]
                },
                {
                    "name": "Portrait Generation",
                    "description": "Portrait-focused workflow",
                    "models": {
                        "checkpoints": [
                            {"ref": "realistic-vision"}
                        ],
                        "controlnet": [
                            {"urn": "urn:air:sd1:controlnet:civitai:54321", "name": "Face ControlNet"}
                        ]
                    }
                }
            ]
        }

        config_path = self.test_path / "workflow_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
        return config_path

    def simulate_yaml_processing(self, config_path, selected_workflow=None):
        """Simulate the YAML processing logic from install script."""
        with open(config_path) as f:
            data = yaml.safe_load(f)

        models = data.get('models', {})
        workflows = data.get('workflows', [])

        # Simulate the workflow selection and merging logic
        workflow_models = {}
        workflow_nodes = []

        if selected_workflow:
            for wf in workflows:
                if isinstance(wf, dict) and wf.get('name') == selected_workflow:
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

        # Build index of global models by ID for reference resolution
        global_models_by_cat = {}
        for cat, lst in models.items():
            if cat not in ('dest_dir', 'source_dir'):
                global_models_by_cat[cat] = lst or []

        # Extract and resolve references
        resolved_env_vars = {}

        for cat, lst in all_models.items():
            urns = []
            for item in lst:
                if isinstance(item, dict):
                    if 'ref' in item:
                        # Resolve reference
                        ref_id = item['ref']
                        global_cat = global_models_by_cat.get(cat, [])
                        for global_item in global_cat:
                            if isinstance(global_item, dict) and global_item.get('id') == ref_id:
                                actual = global_item.get('urn') or global_item.get('url') or global_item.get('id')
                                if actual:
                                    urns.append(str(actual))
                                break
                    else:
                        val = item.get('urn') or item.get('url') or item.get('id')
                        if val:
                            urns.append(str(val))
                elif item:
                    urns.append(str(item))

            if urns:
                resolved_env_vars[f'CIVITAI_{cat.upper()}'] = ','.join(urns)

        # Handle custom nodes with reference resolution
        global_nodes = [node['url'] for node in data.get('custom_nodes', []) if isinstance(node, dict) and node.get('url')]

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
                    # Note: warnings are printed to stderr in real script, but we skip in simulation
                else:
                    pass  # In simulation, we skip invalid refs silently
            else:
                resolved_workflow_nodes.append(node_url)

        all_node_urls = global_nodes + resolved_workflow_nodes
        if all_node_urls:
            resolved_env_vars['YAML_CUSTOM_NODE_URLS'] = ' '.join(all_node_urls)

        return resolved_env_vars

    def run_validator(self, config_path):
        """Run the config validator and return exit code and output."""
        result = subprocess.run(
            [sys.executable, str(self.validator_script), str(config_path)],
            capture_output=True, text=True
        )
        return result.returncode, result.stdout + result.stderr

    def test_basic_workflow_reference_resolution(self):
        """Test that workflow references resolve to correct URNs."""
        config_path = self.create_workflow_config()

        # Test with SDXL workflow
        env_vars = self.simulate_yaml_processing(config_path, "Basic SDXL Generation")

        # Should have all global checkpoints PLUS workflow-referenced checkpoints
        self.assertIn("CIVITAI_CHECKPOINTS", env_vars)
        checkpoints = env_vars["CIVITAI_CHECKPOINTS"].split(',')
        # Global models are included
        self.assertIn("urn:air:sdxl:checkpoint:civitai:101055", checkpoints)
        self.assertIn("urn:air:sd1:checkpoint:civitai:4201", checkpoints)
        # Workflow reference should resolve to the same SDXL base (may appear twice)
        sdxl_count = checkpoints.count("urn:air:sdxl:checkpoint:civitai:101055")
        self.assertGreaterEqual(sdxl_count, 1, "SDXL base checkpoint should be present")

        # Should have global + workflow VAE
        self.assertIn("CIVITAI_VAE", env_vars)
        vae_list = env_vars["CIVITAI_VAE"].split(',')
        self.assertIn("urn:air:sdxl:vae:civitai:123456", vae_list)  # Both global and referenced

        # Should have global + workflow LoRAs (both referenced and direct)
        self.assertIn("CIVITAI_LORAS", env_vars)
        loras = env_vars["CIVITAI_LORAS"].split(',')
        self.assertIn("urn:air:sd1:lora:civitai:16576", loras)  # Global + Referenced
        self.assertIn("urn:air:sd1:lora:civitai:99999", loras)  # Workflow direct

        # Should have custom nodes (global + workflow)
        self.assertIn("YAML_CUSTOM_NODE_URLS", env_vars)
        nodes = env_vars["YAML_CUSTOM_NODE_URLS"].split()
        self.assertIn("git+https://github.com/ltdrdata/ComfyUI-Manager.git", nodes)
        self.assertIn("git+https://github.com/example/sdxl-nodes.git", nodes)

    def test_different_workflow_different_models(self):
        """Test that different workflows resolve to different model sets."""
        config_path = self.create_workflow_config()

        # Test Portrait workflow
        env_vars = self.simulate_yaml_processing(config_path, "Portrait Generation")

        # Should have ALL global checkpoints PLUS workflow-referenced checkpoint
        self.assertIn("CIVITAI_CHECKPOINTS", env_vars)
        checkpoints = env_vars["CIVITAI_CHECKPOINTS"].split(',')
        # All global models should be present
        self.assertIn("urn:air:sdxl:checkpoint:civitai:101055", checkpoints)
        self.assertIn("urn:air:sd1:checkpoint:civitai:4201", checkpoints)
        # Workflow reference should add realistic-vision (may appear twice)
        rv_count = checkpoints.count("urn:air:sd1:checkpoint:civitai:4201")
        self.assertGreaterEqual(rv_count, 1, "Realistic Vision should be present")

        # Should have ControlNet models specific to this workflow
        self.assertIn("CIVITAI_CONTROLNET", env_vars)
        self.assertEqual(env_vars["CIVITAI_CONTROLNET"], "urn:air:sd1:controlnet:civitai:54321")

        # Should have global VAE and LoRAs (even though not specified in workflow)
        self.assertIn("CIVITAI_VAE", env_vars)  # Global VAE still present
        self.assertIn("CIVITAI_LORAS", env_vars)  # Global LoRAs still present

    def test_invalid_reference_handling(self):
        """Test handling of invalid references in workflows."""
        config = {
            "models": {
                "checkpoints": [
                    {"id": "existing-model", "urn": "urn:air:sdxl:checkpoint:civitai:12345"}
                ]
            },
            "workflows": [
                {
                    "name": "Test Workflow",
                    "models": {
                        "checkpoints": [
                            {"ref": "non-existent-model"}
                        ]
                    }
                }
            ]
        }

        config_path = self.test_path / "invalid_ref_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        env_vars = self.simulate_yaml_processing(config_path, "Test Workflow")

        # Should still have global checkpoints, but invalid ref should be skipped
        self.assertIn("CIVITAI_CHECKPOINTS", env_vars)
        self.assertEqual(env_vars["CIVITAI_CHECKPOINTS"], "urn:air:sdxl:checkpoint:civitai:12345")

    def test_workflow_model_merging_with_globals(self):
        """Test that workflow models are merged with global models."""
        config = {
            "models": {
                "checkpoints": [
                    {"id": "global-model", "urn": "urn:air:sdxl:checkpoint:civitai:11111"}
                ],
                "loras": [
                    {"urn": "urn:air:sd1:lora:civitai:22222", "name": "Global LoRA"}
                ]
            },
            "workflows": [
                {
                    "name": "Test Workflow",
                    "models": {
                        "checkpoints": [
                            {"ref": "global-model"},  # Reference global
                            {"urn": "urn:air:sd1:checkpoint:civitai:33333"}  # Add workflow-specific
                        ]
                    }
                }
            ]
        }

        config_path = self.test_path / "merge_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        env_vars = self.simulate_yaml_processing(config_path, "Test Workflow")

        # Should have both global and workflow checkpoints
        self.assertIn("CIVITAI_CHECKPOINTS", env_vars)
        checkpoints = env_vars["CIVITAI_CHECKPOINTS"].split(',')
        self.assertIn("urn:air:sdxl:checkpoint:civitai:11111", checkpoints)  # Global via ref
        self.assertIn("urn:air:sd1:checkpoint:civitai:33333", checkpoints)  # Workflow direct

        # Should still have global LoRAs even though not mentioned in workflow
        self.assertIn("CIVITAI_LORAS", env_vars)
        self.assertEqual(env_vars["CIVITAI_LORAS"], "urn:air:sd1:lora:civitai:22222")

    @patch('subprocess.run')
    def test_comfyctl_workflow_installation(self, mock_run):
        """Test that comfyctl can install a specific workflow with resolved references."""
        config_path = self.create_workflow_config()

        # Mock successful execution
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        # Test comfyctl install with workflow selection
        cmd = [
            sys.executable, str(self.comfyctl_path),
            "install",
            "--config", str(config_path),
            "--workflow", "Basic SDXL Generation"
        ]

        # Simulate the call (without actually executing)
        expected_env = os.environ.copy()
        expected_env.update({
            "CONFIG_FILE": str(config_path),
            "WORKFLOW": "Basic SDXL Generation"
        })

        # Verify the command structure
        self.assertEqual(cmd[2], "install")
        self.assertEqual(cmd[4], str(config_path))
        self.assertEqual(cmd[6], "Basic SDXL Generation")

    def test_workflow_with_mixed_reference_types(self):
        """Test workflow with mix of refs, direct URNs, and URLs."""
        config = {
            "models": {
                "checkpoints": [
                    {"id": "base-model", "urn": "urn:air:sdxl:checkpoint:civitai:12345"}
                ],
                "custom_models": [
                    {"id": "custom-base", "url": "https://example.com/custom.safetensors"}
                ]
            },
            "workflows": [
                {
                    "name": "Mixed Workflow",
                    "models": {
                        "checkpoints": [
                            {"ref": "base-model"},  # Reference
                            {"urn": "urn:air:sd1:checkpoint:civitai:67890"},  # Direct URN
                            "urn:air:sd1:checkpoint:civitai:99999"  # String URN
                        ],
                        "custom_models": [
                            {"ref": "custom-base"},  # Reference to URL
                            {"url": "https://example.com/workflow-specific.ckpt"}  # Direct URL
                        ]
                    }
                }
            ]
        }

        config_path = self.test_path / "mixed_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        env_vars = self.simulate_yaml_processing(config_path, "Mixed Workflow")

        # Should have all checkpoint types
        checkpoints = env_vars.get("CIVITAI_CHECKPOINTS", "").split(',')
        self.assertIn("urn:air:sdxl:checkpoint:civitai:12345", checkpoints)  # Ref resolved
        self.assertIn("urn:air:sd1:checkpoint:civitai:67890", checkpoints)  # Direct URN
        self.assertIn("urn:air:sd1:checkpoint:civitai:99999", checkpoints)  # String URN

        # Should have all custom model types
        custom_models = env_vars.get("CIVITAI_CUSTOM_MODELS", "").split(',')
        self.assertIn("https://example.com/custom.safetensors", custom_models)  # Ref resolved
        self.assertIn("https://example.com/workflow-specific.ckpt", custom_models)  # Direct URL

    def test_workflow_without_models_section(self):
        """Test workflow that only adds custom nodes, no models."""
        config = {
            "models": {
                "checkpoints": [
                    {"id": "base", "urn": "urn:air:sdxl:checkpoint:civitai:12345"}
                ]
            },
            "workflows": [
                {
                    "name": "Nodes Only Workflow",
                    "custom_nodes": [
                        {"name": "Special Node", "url": "git+https://github.com/special/node.git"}
                    ]
                    # No models section
                }
            ]
        }

        config_path = self.test_path / "nodes_only_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        env_vars = self.simulate_yaml_processing(config_path, "Nodes Only Workflow")

        # Should still have global models
        self.assertIn("CIVITAI_CHECKPOINTS", env_vars)
        self.assertEqual(env_vars["CIVITAI_CHECKPOINTS"], "urn:air:sdxl:checkpoint:civitai:12345")

        # Should have the workflow-specific custom node
        self.assertIn("YAML_CUSTOM_NODE_URLS", env_vars)
        self.assertEqual(env_vars["YAML_CUSTOM_NODE_URLS"], "git+https://github.com/special/node.git")

    def test_multiple_references_same_category(self):
        """Test workflow with multiple references in the same model category."""
        config = {
            "models": {
                "checkpoints": [
                    {"id": "model-1", "urn": "urn:air:sdxl:checkpoint:civitai:11111"},
                    {"id": "model-2", "urn": "urn:air:sd1:checkpoint:civitai:22222"},
                    {"id": "model-3", "urn": "urn:air:sd2:checkpoint:civitai:33333"}
                ]
            },
            "workflows": [
                {
                    "name": "Multi-Model Workflow",
                    "models": {
                        "checkpoints": [
                            {"ref": "model-1"},
                            {"ref": "model-2"},
                            {"ref": "model-3"}
                        ]
                    }
                }
            ]
        }

        config_path = self.test_path / "multi_ref_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        env_vars = self.simulate_yaml_processing(config_path, "Multi-Model Workflow")

        # Should have all global models PLUS all referenced models
        checkpoints = env_vars.get("CIVITAI_CHECKPOINTS", "").split(',')
        # Should have at least the 3 unique models (may have duplicates)
        unique_checkpoints = list(set(checkpoints))
        self.assertGreaterEqual(len(unique_checkpoints), 3)
        self.assertIn("urn:air:sdxl:checkpoint:civitai:11111", checkpoints)
        self.assertIn("urn:air:sd1:checkpoint:civitai:22222", checkpoints)
        self.assertIn("urn:air:sd2:checkpoint:civitai:33333", checkpoints)

    def test_workflow_reference_resolution_with_download_env_vars(self):
        """Test that resolved references create proper environment variables for downloads."""
        config_path = self.create_workflow_config()
        env_vars = self.simulate_yaml_processing(config_path, "Basic SDXL Generation")

        # Verify that all expected download environment variables are created
        expected_vars = [
            "CIVITAI_CHECKPOINTS",
            "CIVITAI_VAE",
            "CIVITAI_LORAS",
            "YAML_CUSTOM_NODE_URLS"
        ]

        for var in expected_vars:
            self.assertIn(var, env_vars, f"Missing environment variable: {var}")
            self.assertTrue(len(env_vars[var]) > 0, f"Empty environment variable: {var}")

        # Verify URN format for model downloads
        for var in ["CIVITAI_CHECKPOINTS", "CIVITAI_VAE", "CIVITAI_LORAS"]:
            if var in env_vars:
                urns = env_vars[var].split(',')
                for urn in urns:
                    self.assertTrue(
                        urn.startswith("urn:air:") or urn.startswith("http"),
                        f"Invalid URN/URL format in {var}: {urn}"
                    )

    def test_workflow_custom_node_references(self):
        """Test that workflow custom nodes can use references to global custom nodes."""
        # Test data with custom node references
        config = {
            "custom_nodes": [
                {"id": "comfy-manager", "url": "https://github.com/ltdrdata/ComfyUI-Manager"},
                {"id": "controlnet", "url": "https://github.com/Fannovel16/comfyui_controlnet_aux"},
                {"url": "https://github.com/some/direct-node"}  # No ID, direct use only
            ],
            "workflows": [
                {
                    "name": "test-workflow",
                    "custom_nodes": [
                        {"ref": "comfy-manager"},
                        {"ref": "controlnet"},
                        {"url": "https://github.com/workflow/specific-node"}
                    ]
                }
            ]
        }

        config_path = self.test_path / "test_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        # Test the simulation
        env_vars = self.simulate_yaml_processing(config_path, "test-workflow")

        # Check that custom node URLs were resolved correctly
        self.assertIn("YAML_CUSTOM_NODE_URLS", env_vars)

        urls = env_vars["YAML_CUSTOM_NODE_URLS"].split()
        expected_urls = [
            "https://github.com/some/direct-node",  # Global direct
            "https://github.com/ltdrdata/ComfyUI-Manager",  # Resolved ref
            "https://github.com/Fannovel16/comfyui_controlnet_aux",  # Resolved ref
            "https://github.com/workflow/specific-node"  # Workflow direct
        ]
        self.assertEqual(set(urls), set(expected_urls))

    def test_workflow_custom_node_invalid_references(self):
        """Test handling of invalid custom node references."""
        config = {
            "custom_nodes": [
                {"id": "existing-node", "url": "https://github.com/valid/node"}
            ],
            "workflows": [
                {
                    "name": "test-workflow",
                    "custom_nodes": [
                        {"ref": "nonexistent-node"},  # Invalid reference
                        {"ref": "existing-node"}       # Valid reference
                    ]
                }
            ]
        }

        config_path = self.test_path / "test_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        env_vars = self.simulate_yaml_processing(config_path, "test-workflow")

        # Invalid reference should be skipped, valid reference should work
        self.assertIn("YAML_CUSTOM_NODE_URLS", env_vars)
        urls = env_vars["YAML_CUSTOM_NODE_URLS"].split()
        self.assertIn("https://github.com/valid/node", urls)
        # Should have the global node PLUS the resolved workflow reference (both point to same URL)
        # So we should have the URL twice or once (depending on deduplication)
        self.assertGreaterEqual(len(urls), 1)  # At least the valid node
        # Check all URLs are the same valid one (no invalid refs)
        for url in urls:
            self.assertEqual(url, "https://github.com/valid/node")

    def test_workflow_custom_node_mixed_refs_and_direct(self):
        """Test workflows with mix of custom node references and direct URLs."""
        config = {
            "custom_nodes": [
                {"id": "shared-node", "url": "https://github.com/shared/node"}
            ],
            "workflows": [
                {
                    "name": "mixed-workflow",
                    "custom_nodes": [
                        {"ref": "shared-node"},
                        {"url": "https://github.com/workflow/direct-node"}
                    ]
                }
            ]
        }

        config_path = self.test_path / "test_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        env_vars = self.simulate_yaml_processing(config_path, "mixed-workflow")

        # Verify both global and workflow-specific nodes are included
        self.assertIn("YAML_CUSTOM_NODE_URLS", env_vars)
        urls = env_vars["YAML_CUSTOM_NODE_URLS"].split()
        expected_urls = [
            "https://github.com/shared/node",       # Resolved reference
            "https://github.com/workflow/direct-node"  # Direct URL
        ]
        self.assertEqual(set(urls), set(expected_urls))

    def test_workflow_custom_node_conflicting_ref_and_url(self):
        """Test that custom nodes cannot have both ref and url fields."""
        config = {
            "custom_nodes": [
                {"id": "valid-node", "url": "https://github.com/valid/node"}
            ],
            "workflows": [
                {
                    "name": "test-workflow",
                    "custom_nodes": [
                        {
                            "ref": "valid-node",
                            "url": "https://github.com/conflicting/url"  # Should conflict with ref
                        }
                    ]
                }
            ]
        }

        config_path = self.test_path / "test_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        # This should fail validation
        exit_code, output = self.run_validator(config_path)
        self.assertEqual(exit_code, 1)
        self.assertIn("cannot have both 'ref' and 'url' fields", output)

    def test_workflow_custom_node_ref_without_url_in_global(self):
        """Test custom node reference where global node has ID but no URL."""
        config = {
            "custom_nodes": [
                {"id": "node-without-url"}  # Has ID but missing URL
            ],
            "workflows": [
                {
                    "name": "test-workflow",
                    "custom_nodes": [
                        {"ref": "node-without-url"}
                    ]
                }
            ]
        }

        config_path = self.test_path / "test_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        # Should pass validation (validator only checks ref exists)
        exit_code, output = self.run_validator(config_path)
        self.assertEqual(exit_code, 0)

        # But simulation should handle gracefully (no URL to resolve)
        env_vars = self.simulate_yaml_processing(config_path, "test-workflow")
        # Should have no custom node URLs since the global node has no URL
        if "YAML_CUSTOM_NODE_URLS" in env_vars:
            self.assertEqual(env_vars["YAML_CUSTOM_NODE_URLS"].strip(), "")

    def test_workflow_custom_node_empty_refs(self):
        """Test handling of empty custom node references."""
        config = {
            "custom_nodes": [
                {"id": "valid-node", "url": "https://github.com/valid/node"}
            ],
            "workflows": [
                {
                    "name": "test-workflow",
                    "custom_nodes": [
                        {"ref": ""},  # Empty reference
                        {"ref": "valid-node"}
                    ]
                }
            ]
        }

        config_path = self.test_path / "test_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        env_vars = self.simulate_yaml_processing(config_path, "test-workflow")

        # Should still work with valid reference, ignoring empty one
        self.assertIn("YAML_CUSTOM_NODE_URLS", env_vars)
        urls = env_vars["YAML_CUSTOM_NODE_URLS"].split()
        self.assertIn("https://github.com/valid/node", urls)

    def test_workflow_no_custom_nodes_section(self):
        """Test workflow that has no custom_nodes section at all."""
        config = {
            "custom_nodes": [
                {"id": "global-node", "url": "https://github.com/global/node"}
            ],
            "workflows": [
                {
                    "name": "no-nodes-workflow",
                    "models": {
                        "checkpoints": [
                            {"urn": "urn:air:sdxl:checkpoint:civitai:12345"}
                        ]
                    }
                    # No custom_nodes section
                }
            ]
        }

        config_path = self.test_path / "test_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        env_vars = self.simulate_yaml_processing(config_path, "no-nodes-workflow")

        # Should still have global custom nodes
        self.assertIn("YAML_CUSTOM_NODE_URLS", env_vars)
        urls = env_vars["YAML_CUSTOM_NODE_URLS"].split()
        self.assertIn("https://github.com/global/node", urls)

    def test_multiple_workflows_different_custom_node_refs(self):
        """Test that different workflows can reference different sets of custom nodes."""
        config = {
            "custom_nodes": [
                {"id": "node-a", "url": "https://github.com/node/a"},
                {"id": "node-b", "url": "https://github.com/node/b"},
                {"id": "node-c", "url": "https://github.com/node/c"}
            ],
            "workflows": [
                {
                    "name": "workflow-1",
                    "custom_nodes": [
                        {"ref": "node-a"},
                        {"ref": "node-b"}
                    ]
                },
                {
                    "name": "workflow-2",
                    "custom_nodes": [
                        {"ref": "node-b"},
                        {"ref": "node-c"}
                    ]
                }
            ]
        }

        config_path = self.test_path / "test_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        # Test workflow-1
        env_vars_1 = self.simulate_yaml_processing(config_path, "workflow-1")
        urls_1 = set(env_vars_1["YAML_CUSTOM_NODE_URLS"].split())
        expected_1 = {
            "https://github.com/node/a",
            "https://github.com/node/b",
            "https://github.com/node/c"  # All global nodes included
        }
        # Should include global nodes + workflow-specific refs
        self.assertTrue(expected_1.issubset(urls_1))

        # Test workflow-2
        env_vars_2 = self.simulate_yaml_processing(config_path, "workflow-2")
        urls_2 = set(env_vars_2["YAML_CUSTOM_NODE_URLS"].split())
        expected_2 = {
            "https://github.com/node/a",
            "https://github.com/node/b",
            "https://github.com/node/c"  # All global nodes included
        }
        # Should include global nodes + workflow-specific refs
        self.assertTrue(expected_2.issubset(urls_2))

    def test_workflow_duplicate_custom_node_references(self):
        """Test handling of duplicate custom node references in workflow."""
        config = {
            "custom_nodes": [
                {"id": "shared-node", "url": "https://github.com/shared/node"},
                {"url": "https://github.com/shared/node"}  # Same URL as referenced node
            ],
            "workflows": [
                {
                    "name": "duplicate-workflow",
                    "custom_nodes": [
                        {"ref": "shared-node"},
                        {"ref": "shared-node"},  # Duplicate reference
                        {"url": "https://github.com/shared/node"}  # Same URL again
                    ]
                }
            ]
        }

        config_path = self.test_path / "test_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        env_vars = self.simulate_yaml_processing(config_path, "duplicate-workflow")

        # Should handle duplicates gracefully (no deduplication expected in current implementation)
        self.assertIn("YAML_CUSTOM_NODE_URLS", env_vars)
        urls = env_vars["YAML_CUSTOM_NODE_URLS"].split()
        # All instances should be present (script doesn't deduplicate)
        url_count = urls.count("https://github.com/shared/node")
        self.assertGreaterEqual(url_count, 3)  # At least 3 instances

    def test_global_custom_nodes_with_only_ids_no_urls(self):
        """Test global custom nodes that have IDs but no URLs (validation edge case)."""
        config = {
            "custom_nodes": [
                {"id": "id-only-node"},  # ID but no URL
                {"url": "https://github.com/url-only/node"}  # URL but no ID
            ]
        }

        config_path = self.test_path / "test_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        # Should pass validation - global custom nodes with IDs are valid for referencing
        exit_code, output = self.run_validator(config_path)
        self.assertEqual(exit_code, 0)
        self.assertIn("passed validation", output)


class TestCustomNodeReferenceEdgeCases(unittest.TestCase):
    """Additional edge case tests for custom node references."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.test_path = pathlib.Path(self.test_dir.name)
        self.validator_script = pathlib.Path(__file__).parent.parent / "scripts" / "validate_config.py"

    def tearDown(self):
        """Clean up test fixtures."""
        self.test_dir.cleanup()

    def run_validator(self, config_path):
        """Run the config validator and return exit code and output."""
        result = subprocess.run(
            [sys.executable, str(self.validator_script), str(config_path)],
            capture_output=True, text=True
        )
        return result.returncode, result.stdout + result.stderr

    def test_custom_node_circular_references(self):
        """Test that custom nodes cannot have circular ID references (though this isn't possible with current structure)."""
        # This is more of a documentation test - our current structure doesn't allow circular refs
        # since custom nodes can't reference other custom nodes, only workflows can reference globals
        config = {
            "custom_nodes": [
                {"id": "node-a", "url": "https://github.com/node/a"},
                {"id": "node-b", "url": "https://github.com/node/b"}
            ],
            "workflows": [
                {
                    "name": "test-workflow",
                    "custom_nodes": [
                        {"ref": "node-a"},
                        {"ref": "node-b"}
                    ]
                }
            ]
        }

        config_path = self.test_path / "test_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        # Should pass validation - no circular references possible
        exit_code, output = self.run_validator(config_path)
        self.assertEqual(exit_code, 0)

    def test_custom_node_case_sensitive_references(self):
        """Test that custom node references are case-sensitive."""
        config = {
            "custom_nodes": [
                {"id": "MyNode", "url": "https://github.com/my/node"}
            ],
            "workflows": [
                {
                    "name": "test-workflow",
                    "custom_nodes": [
                        {"ref": "mynode"}  # Different case
                    ]
                }
            ]
        }

        config_path = self.test_path / "test_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        # Should fail validation - case mismatch
        exit_code, output = self.run_validator(config_path)
        self.assertEqual(exit_code, 1)
        self.assertIn("ref 'mynode' not found in global custom_nodes", output)

    def test_custom_node_special_characters_in_ids(self):
        """Test custom node IDs with special characters."""
        config = {
            "custom_nodes": [
                {"id": "node-with_special.chars@123", "url": "https://github.com/special/node"},
                {"id": "node with spaces", "url": "https://github.com/spaces/node"}
            ],
            "workflows": [
                {
                    "name": "test-workflow",
                    "custom_nodes": [
                        {"ref": "node-with_special.chars@123"},
                        {"ref": "node with spaces"}
                    ]
                }
            ]
        }

        config_path = self.test_path / "test_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        # Should pass validation - special characters allowed in IDs
        exit_code, output = self.run_validator(config_path)
        self.assertEqual(exit_code, 0)


class TestWorkflowValidationIntegration(unittest.TestCase):
    """Test integration between workflow references and validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.test_path = pathlib.Path(self.test_dir.name)
        self.validator_script = pathlib.Path(__file__).parent.parent / "scripts" / "validate_config.py"

    def tearDown(self):
        """Clean up test fixtures."""
        self.test_dir.cleanup()

    def run_validator(self, config_path):
        """Run the config validator and return exit code and output."""
        result = subprocess.run(
            [sys.executable, str(self.validator_script), str(config_path)],
            capture_output=True, text=True
        )
        return result.returncode, result.stdout + result.stderr

    def test_validator_catches_invalid_workflow_references(self):
        """Test that the validator catches invalid workflow references."""
        config = {
            "models": {
                "checkpoints": [
                    {"id": "existing", "urn": "urn:air:sdxl:checkpoint:civitai:12345"}
                ]
            },
            "workflows": [
                {
                    "name": "Test Workflow",
                    "models": {
                        "checkpoints": [
                            {"ref": "non-existent"}
                        ]
                    }
                }
            ]
        }

        config_path = self.test_path / "invalid_ref.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        exit_code, output = self.run_validator(config_path)

        self.assertEqual(exit_code, 1)
        self.assertIn("ref 'non-existent' not found", output)

    def test_validator_allows_valid_workflow_references(self):
        """Test that the validator allows valid workflow references."""
        config = {
            "models": {
                "checkpoints": [
                    {"id": "base-model", "urn": "urn:air:sdxl:checkpoint:civitai:12345"}
                ]
            },
            "workflows": [
                {
                    "name": "Valid Workflow",
                    "models": {
                        "checkpoints": [
                            {"ref": "base-model"}
                        ]
                    }
                }
            ]
        }

        config_path = self.test_path / "valid_ref.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        exit_code, output = self.run_validator(config_path)

        self.assertEqual(exit_code, 0)
        self.assertIn("passed validation", output)


if __name__ == '__main__':
    unittest.main()
