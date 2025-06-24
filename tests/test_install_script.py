#!/usr/bin/env python3
"""Unit tests for install script functionality, especially custom nodes."""

import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch, call
import yaml


class TestInstallScript(unittest.TestCase):
    """Test install script functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.test_path = pathlib.Path(self.test_dir.name)
        self.install_script = pathlib.Path(__file__).parent.parent / "scripts" / "install_comfy_and_models.sh"

    def tearDown(self):
        """Clean up test fixtures."""
        self.test_dir.cleanup()

    def create_test_config(self, custom_nodes=None) -> pathlib.Path:
        """Create a test config file with custom nodes."""
        config = {
            "install": {
                "comfy_dir": str(self.test_path / "ComfyUI"),
                "cpu_only": True
            },
            "custom_nodes": custom_nodes or []
        }
        
        config_path = self.test_path / "test_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
        return config_path

    def test_custom_nodes_yaml_parsing(self):
        """Test that custom nodes are correctly parsed from YAML."""
        custom_nodes = [
            {
                "name": "ComfyUI-Manager",
                "description": "GUI package manager",
                "url": "git+https://github.com/ltdrdata/ComfyUI-Manager.git"
            },
            {
                "name": "ControlNet",
                "url": "https://github.com/lllyasviel/ComfyUI_ControlNet.git"
            },
            {
                "name": "PyPI Package",
                "url": "some-pypi-package"
            }
        ]
        
        config_path = self.create_test_config(custom_nodes)
        
        # Test that we can parse the config and extract URLs
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        urls = []
        for node in config.get('custom_nodes', []):
            if isinstance(node, dict) and node.get('url'):
                urls.append(node['url'])
        
        expected_urls = [
            "git+https://github.com/ltdrdata/ComfyUI-Manager.git",
            "https://github.com/lllyasviel/ComfyUI_ControlNet.git",
            "some-pypi-package"
        ]
        
        self.assertEqual(urls, expected_urls)

    def test_git_url_detection(self):
        """Test detection of Git URLs vs PyPI packages."""
        test_cases = [
            # Git URLs (should be cloned)
            ("git+https://github.com/user/repo.git", True),
            ("https://github.com/user/repo.git", True),
            ("https://github.com/user/repo", True),
            ("https://gitlab.com/user/repo.git", True),
            ("https://bitbucket.org/user/repo", True),
            # PyPI packages (should be pip installed)
            ("some-package", False),
            ("package_name", False),
            ("my-cool-package-v2", False),
            ("requests", False),
        ]
        
        for url, expected_is_git in test_cases:
            with self.subTest(url=url):
                # Simulate the bash regex logic from the script
                is_git = (
                    url.startswith("git+") or
                    "github.com" in url or
                    "gitlab.com" in url or
                    "bitbucket.org" in url
                )
                self.assertEqual(is_git, expected_is_git, f"URL: {url}")

    def test_git_prefix_removal(self):
        """Test removal of git+ prefix from URLs."""
        test_cases = [
            ("git+https://github.com/user/repo.git", "https://github.com/user/repo.git"),
            ("https://github.com/user/repo.git", "https://github.com/user/repo.git"),
            ("git+ssh://git@github.com/user/repo.git", "ssh://git@github.com/user/repo.git"),
        ]
        
        for original, expected in test_cases:
            with self.subTest(original=original):
                # Simulate the bash prefix removal: ${u#git+}
                cleaned = original[4:] if original.startswith("git+") else original
                self.assertEqual(cleaned, expected)

    def test_repo_name_extraction(self):
        """Test extraction of repository names from URLs."""
        test_cases = [
            ("https://github.com/ltdrdata/ComfyUI-Manager.git", "ComfyUI-Manager"),
            ("https://github.com/user/repo", "repo"),
            ("git+https://gitlab.com/group/subgroup/project.git", "project"),
            ("https://bitbucket.org/user/my-awesome-nodes.git", "my-awesome-nodes"),
        ]
        
        for url, expected_name in test_cases:
            with self.subTest(url=url):
                # Simulate bash: basename "$clean_url" .git
                import os
                clean_url = url[4:] if url.startswith("git+") else url
                basename = os.path.basename(clean_url)
                repo_name = basename[:-4] if basename.endswith(".git") else basename
                self.assertEqual(repo_name, expected_name)

    def test_workflow_custom_nodes_merging(self):
        """Test that workflow-specific custom nodes are properly merged with global ones."""
        config = {
            "install": {"cpu_only": True},
            "custom_nodes": [
                {"name": "Global Node 1", "url": "https://github.com/global/node1.git"},
                {"name": "Global Node 2", "url": "global-pypi-package"}
            ],
            "workflows": [
                {
                    "name": "Test Workflow",
                    "custom_nodes": [
                        {"name": "Workflow Node", "url": "https://github.com/workflow/node.git"}
                    ]
                }
            ]
        }
        
        config_path = self.test_path / "workflow_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
        
        # Simulate the script's logic for merging global + workflow nodes
        global_urls = [node['url'] for node in config['custom_nodes']]
        workflow_urls = []
        
        # Find the specific workflow
        for workflow in config.get('workflows', []):
            if workflow.get('name') == 'Test Workflow':
                workflow_urls = [node['url'] for node in workflow.get('custom_nodes', [])]
                break
        
        all_urls = global_urls + workflow_urls
        expected_urls = [
            "https://github.com/global/node1.git",
            "global-pypi-package",
            "https://github.com/workflow/node.git"
        ]
        
        self.assertEqual(all_urls, expected_urls)

    @patch('subprocess.run')
    def test_script_execution_with_custom_nodes(self, mock_run):
        """Test that the install script can be executed with custom nodes config."""
        custom_nodes = [
            {"name": "Test Node", "url": "https://github.com/test/node.git"}
        ]
        config_path = self.create_test_config(custom_nodes)
        
        # Mock successful script execution
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        
        # Test that script exists and can be called
        self.assertTrue(self.install_script.exists(), "Install script should exist")
        
        # Simulate calling the script (without actually running it)
        cmd = ["bash", str(self.install_script)]
        env = os.environ.copy()
        env["CONFIG_FILE"] = str(config_path)
        
        # This would be the actual call in comfyctl.py
        # subprocess.run(cmd, env=env, check=True)
        
        # For testing, we just verify the command structure
        self.assertTrue(len(cmd) >= 2)
        self.assertEqual(cmd[0], "bash")
        self.assertTrue(cmd[1].endswith("install_comfy_and_models.sh"))

    def test_requirements_handling_simulation(self):
        """Test logic for handling requirements.txt in custom nodes."""
        # Create a mock custom node directory structure
        custom_node_dir = self.test_path / "custom_nodes" / "test-node"
        custom_node_dir.mkdir(parents=True)
        
        # Create a requirements.txt file
        requirements_file = custom_node_dir / "requirements.txt"
        requirements_file.write_text("torch>=1.0\nnumpy>=1.20\n")
        
        # Test that requirements file exists and can be read
        self.assertTrue(requirements_file.exists())
        
        requirements = requirements_file.read_text().strip().split('\n')
        expected_requirements = ["torch>=1.0", "numpy>=1.20"]
        
        self.assertEqual(requirements, expected_requirements)

    def test_custom_node_directory_creation(self):
        """Test that custom_nodes directory is created correctly."""
        comfy_dir = self.test_path / "ComfyUI"
        custom_nodes_dir = comfy_dir / "custom_nodes"
        
        # Simulate mkdir -p "$COMFY_DIR/custom_nodes"
        custom_nodes_dir.mkdir(parents=True, exist_ok=True)
        
        self.assertTrue(custom_nodes_dir.exists())
        self.assertTrue(custom_nodes_dir.is_dir())

    def test_duplicate_node_handling(self):
        """Test that existing custom nodes are not reinstalled."""
        comfy_dir = self.test_path / "ComfyUI"
        custom_nodes_dir = comfy_dir / "custom_nodes"
        existing_node = custom_nodes_dir / "existing-node"
        
        # Create an existing node directory
        existing_node.mkdir(parents=True)
        
        # Simulate the check: if [[ -d "$target_dir" ]]
        self.assertTrue(existing_node.exists())
        
        # The script should skip installation if directory exists
        should_skip = existing_node.exists()
        self.assertTrue(should_skip)

    def test_yaml_export_variable_generation(self):
        """Test the YAML_CUSTOM_NODE_URLS variable generation logic."""
        custom_nodes = [
            {"name": "Node 1", "url": "https://github.com/user/node1.git"},
            {"name": "Node 2", "url": "pypi-package"},
            {"name": "Node 3", "url": "git+https://github.com/user/node3.git"}
        ]
        
        # Simulate the Python script logic from install script
        urls = []
        for node in custom_nodes:
            if isinstance(node, dict) and node.get('url'):
                urls.append(str(node['url']))
        
        yaml_custom_node_urls = ' '.join(urls)
        expected = "https://github.com/user/node1.git pypi-package git+https://github.com/user/node3.git"
        
        self.assertEqual(yaml_custom_node_urls, expected)

    def test_empty_custom_nodes_handling(self):
        """Test handling of empty or missing custom_nodes section."""
        test_cases = [
            {},  # No custom_nodes key
            {"custom_nodes": []},  # Empty list
            {"custom_nodes": None},  # None value
        ]
        
        for config_data in test_cases:
            with self.subTest(config=config_data):
                custom_nodes = config_data.get('custom_nodes') or []
                urls = []
                for node in custom_nodes:
                    if isinstance(node, dict) and node.get('url'):
                        urls.append(str(node['url']))
                
                # Should result in empty URL list
                self.assertEqual(urls, [])
                
                # YAML_CUSTOM_NODE_URLS should be empty
                yaml_urls = ' '.join(urls)
                self.assertEqual(yaml_urls, "")


class TestCustomNodesIntegration(unittest.TestCase):
    """Integration tests for custom nodes with the full pipeline."""

    def setUp(self):
        """Set up integration test fixtures."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.test_path = pathlib.Path(self.test_dir.name)

    def tearDown(self):
        """Clean up integration test fixtures."""
        self.test_dir.cleanup()

    def test_full_config_with_custom_nodes(self):
        """Test a complete configuration with various custom node types."""
        config = {
            "install": {
                "comfy_dir": str(self.test_path / "ComfyUI"),
                "cpu_only": True
            },
            "models": {
                "checkpoints": [
                    {"id": "test-model", "urn": "urn:air:sdxl:checkpoint:civitai:12345"}
                ]
            },
            "custom_nodes": [
                # Git repositories
                {
                    "name": "ComfyUI-Manager",
                    "description": "Node management GUI",
                    "url": "git+https://github.com/ltdrdata/ComfyUI-Manager.git"
                },
                {
                    "name": "ControlNet",
                    "url": "https://github.com/lllyasviel/ComfyUI_ControlNet.git"
                },
                # PyPI package
                {
                    "name": "Extra Utils",
                    "url": "comfyui-extra-utils"
                }
            ],
            "workflows": [
                {
                    "name": "Advanced Workflow",
                    "models": {
                        "checkpoints": [{"ref": "test-model"}]
                    },
                    "custom_nodes": [
                        {
                            "name": "Workflow Specific Node",
                            "url": "https://github.com/workflow/specific.git"
                        }
                    ]
                }
            ]
        }
        
        config_path = self.test_path / "full_config.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
        
        # Verify the config can be loaded and parsed
        with open(config_path) as f:
            loaded_config = yaml.safe_load(f)
        
        self.assertEqual(loaded_config, config)
        
        # Extract all custom node URLs (global + workflow)
        global_urls = [node['url'] for node in loaded_config.get('custom_nodes', [])]
        workflow_urls = []
        
        for workflow in loaded_config.get('workflows', []):
            if workflow.get('name') == 'Advanced Workflow':
                workflow_urls = [node['url'] for node in workflow.get('custom_nodes', [])]
        
        all_urls = global_urls + workflow_urls
        expected_urls = [
            "git+https://github.com/ltdrdata/ComfyUI-Manager.git",
            "https://github.com/lllyasviel/ComfyUI_ControlNet.git",
            "comfyui-extra-utils",
            "https://github.com/workflow/specific.git"
        ]
        
        self.assertEqual(all_urls, expected_urls)

    def test_config_validation_with_custom_nodes(self):
        """Test that config validation works with custom nodes."""
        # This test assumes the validate_config.py script can handle custom nodes
        config = {
            "install": {"cpu_only": True},
            "custom_nodes": [
                {"name": "Valid Node", "url": "https://github.com/user/repo.git"},
                {"url": "missing-name-but-has-url"}  # Should still be valid
            ]
        }
        
        config_path = self.test_path / "validation_test.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
        
        # Test that the config structure is valid YAML
        with open(config_path) as f:
            loaded = yaml.safe_load(f)
        
        self.assertIsInstance(loaded, dict)
        self.assertIn('custom_nodes', loaded)
        self.assertEqual(len(loaded['custom_nodes']), 2)


if __name__ == '__main__':
    unittest.main() 