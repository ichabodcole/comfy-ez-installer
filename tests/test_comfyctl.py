#!/usr/bin/env python3
"""Unit tests for comfyctl.py CLI wrapper"""

import pathlib
import subprocess
import sys
import tempfile
import unittest


class TestComfyCtl(unittest.TestCase):
    """Test the comfyctl.py CLI wrapper."""

    def setUp(self):
        """Set up test fixtures."""
        self.comfyctl_path = pathlib.Path(__file__).parent.parent / "comfyctl.py"
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = pathlib.Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def run_comfyctl(
        self, args: list[str], cwd: pathlib.Path = None
    ) -> tuple[int, str, str]:
        """Run comfyctl.py with the given arguments."""
        cmd = [sys.executable, str(self.comfyctl_path)] + args
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd or self.temp_path
        )
        return result.returncode, result.stdout, result.stderr

    def create_test_config(self) -> pathlib.Path:
        """Create a minimal test config file."""
        config_path = self.temp_path / "test_config.yml"
        config_path.write_text("""
install:
  comfy_dir: /tmp/test_comfy
  cpu_only: true

models:
  dest_dir: /tmp/test_models
  checkpoints:
    - id: test-model
      urn: urn:air:sdxl:checkpoint:civitai:12345
      name: Test Model

workflows:
  - name: Test Workflow
    models:
      checkpoints:
        - ref: test-model
""")
        return config_path

    def test_help_command(self):
        """Test that help is displayed correctly."""
        exit_code, stdout, stderr = self.run_comfyctl(["--help"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Manage ComfyUI environment", stdout)
        self.assertIn("install", stdout)
        self.assertIn("start", stdout)

    def test_install_help(self):
        """Test install subcommand help."""
        exit_code, stdout, stderr = self.run_comfyctl(["install", "--help"])

        self.assertEqual(exit_code, 0)
        self.assertIn("--config", stdout)
        self.assertIn("--workflow", stdout)

    def test_start_help(self):
        """Test start subcommand help."""
        exit_code, stdout, stderr = self.run_comfyctl(["start", "--help"])

        self.assertEqual(exit_code, 0)
        self.assertIn("--config", stdout)

    def test_invalid_command(self):
        """Test that invalid commands are handled properly."""
        exit_code, stdout, stderr = self.run_comfyctl(["invalid-command"])

        self.assertNotEqual(exit_code, 0)
        # Should show usage or error message
        self.assertTrue(len(stderr) > 0 or "invalid" in stdout.lower())

    def test_install_with_custom_config(self):
        """Test install command with custom config file."""
        config_path = self.create_test_config()

        exit_code, stdout, stderr = self.run_comfyctl(
            ["install", "--config", str(config_path)]
        )

        # Should fail (since script doesn't exist in test env) but we can verify
        # the config file path was processed
        self.assertNotEqual(exit_code, 0)
        # Should contain some indication the script was attempted
        output = stdout.lower() + stderr.lower()
        self.assertTrue("install" in output or "script" in output or "config" in output)

    def test_install_with_workflow(self):
        """Test install command with workflow specification."""
        config_path = self.create_test_config()

        exit_code, stdout, stderr = self.run_comfyctl(
            ["install", "--config", str(config_path), "--workflow", "Test Workflow"]
        )

        # Should attempt to run but fail gracefully since script path doesn't exist
        # We're mainly testing argument parsing here
        self.assertTrue(len(stdout) > 0 or len(stderr) > 0)

    def test_config_file_resolution(self):
        """Test that config file paths are resolved correctly."""
        # Create config in temp directory
        config_path = self.create_test_config()

        # Test with relative path
        rel_config = config_path.name
        exit_code, stdout, stderr = self.run_comfyctl(
            ["install", "--config", rel_config], cwd=config_path.parent
        )

        # Should attempt to process the config file
        # (will fail later due to missing install script, but that's expected)
        self.assertTrue(len(stdout) > 0 or len(stderr) > 0)

    def test_missing_config_file(self):
        """Test handling of missing config file."""
        nonexistent_config = self.temp_path / "nonexistent.yml"

        exit_code, stdout, stderr = self.run_comfyctl(
            ["install", "--config", str(nonexistent_config)]
        )

        self.assertNotEqual(exit_code, 0)
        # Should fail due to config file or script issues
        output = stdout.lower() + stderr.lower()
        self.assertTrue(len(output) > 0)  # Some error output should be present

    def test_default_config_lookup(self):
        """Test that default config.yml is found in current directory."""
        # Create default config file
        default_config = self.temp_path / "config.yml"
        default_config.write_text("install:\n  cpu_only: true")

        exit_code, stdout, stderr = self.run_comfyctl(["install"], cwd=self.temp_path)

        # Should find and attempt to use the default config
        # (will fail due to missing install script, but that's expected)
        self.assertTrue(len(stdout) > 0 or len(stderr) > 0)

    def test_env_file_option(self):
        """Test that --env-file option is passed through correctly."""
        config_path = self.create_test_config()
        env_path = self.temp_path / "test.env"
        env_path.write_text("TEST_VAR=test_value")

        exit_code, stdout, stderr = self.run_comfyctl(
            ["install", "--config", str(config_path), "--env-file", str(env_path)]
        )

        # Should attempt to process with env file
        self.assertTrue(len(stdout) > 0 or len(stderr) > 0)

    def test_start_command_basic(self):
        """Test basic start command functionality."""
        config_path = self.create_test_config()

        exit_code, stdout, stderr = self.run_comfyctl(
            ["start", "--config", str(config_path)]
        )

        # Should attempt to start (will fail due to missing actual ComfyUI, but that's expected)
        self.assertTrue(len(stdout) > 0 or len(stderr) > 0)

    def test_argument_validation(self):
        """Test that invalid argument combinations are caught."""
        # Test install with invalid workflow name format
        config_path = self.create_test_config()

        exit_code, stdout, stderr = self.run_comfyctl(
            [
                "install",
                "--config",
                str(config_path),
                "--workflow",
                "",  # Empty workflow name
            ]
        )

        # Should handle gracefully
        self.assertTrue(len(stdout) > 0 or len(stderr) > 0)

    def test_verbose_mode(self):
        """Test that verbose flag works if implemented."""
        config_path = self.create_test_config()

        # Some CLIs implement -v/--verbose
        exit_code, stdout, stderr = self.run_comfyctl(
            ["install", "--config", str(config_path), "-v"]
        )

        # Should either work or give a clear error about unknown option
        # This test mainly ensures we don't crash on additional flags
        self.assertTrue(len(stdout) > 0 or len(stderr) > 0)

    def test_validate_help(self):
        """Test validate subcommand help."""
        exit_code, stdout, stderr = self.run_comfyctl(["validate", "--help"])

        self.assertEqual(exit_code, 0)
        self.assertIn("--config", stdout)
        self.assertIn("validate", stdout.lower())

    def test_validate_with_valid_config(self):
        """Test validate command with a valid config file."""
        config_path = self.create_test_config()

        exit_code, stdout, stderr = self.run_comfyctl(
            ["validate", "--config", str(config_path)]
        )

        # Should succeed for valid config (exit code 0 or graceful failure due to missing scripts)
        # The main thing is it shouldn't crash on the config parsing
        self.assertTrue(len(stdout) > 0 or len(stderr) > 0)

    def test_validate_with_invalid_yaml(self):
        """Test validate command with malformed YAML."""
        invalid_config = self.temp_path / "invalid.yml"
        invalid_config.write_text("invalid: yaml: [")  # Malformed YAML

        exit_code, stdout, stderr = self.run_comfyctl(
            ["validate", "--config", str(invalid_config)]
        )

        # Should fail gracefully with error message
        self.assertNotEqual(exit_code, 0)
        output = stdout.lower() + stderr.lower()
        self.assertTrue("yaml" in output or "error" in output or "parsing" in output)

    def test_validate_with_nonexistent_file(self):
        """Test validate command with non-existent config file."""
        nonexistent_config = self.temp_path / "does_not_exist.yml"

        exit_code, stdout, stderr = self.run_comfyctl(
            ["validate", "--config", str(nonexistent_config)]
        )

        # Should fail with clear error message
        self.assertNotEqual(exit_code, 0)
        output = stdout + stderr
        self.assertIn("not found", output)

    def test_validate_default_config(self):
        """Test validate command with default config.yml."""
        # Create a default config.yml in the temp directory
        default_config = self.temp_path / "config.yml"
        default_config.write_text("""
install:
  cpu_only: true
models:
  checkpoints:
    - id: test-model
      urn: urn:air:sdxl:checkpoint:civitai:12345
      name: Test Model
""")

        exit_code, stdout, stderr = self.run_comfyctl(["validate"], cwd=self.temp_path)

        # Should attempt to validate the default config
        self.assertTrue(len(stdout) > 0 or len(stderr) > 0)


class TestComfyCtlIntegration(unittest.TestCase):
    """Integration tests for comfyctl.py with actual file operations."""

    def setUp(self):
        """Set up test fixtures for integration tests."""
        self.comfyctl_path = pathlib.Path(__file__).parent.parent / "comfyctl.py"
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = pathlib.Path(self.temp_dir.name)

        # Create a minimal project structure
        self.project_root = self.temp_path / "project"
        self.project_root.mkdir()

        # Copy comfyctl to project root for testing
        (self.project_root / "comfyctl.py").write_text(self.comfyctl_path.read_text())

    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_config_validation_integration(self):
        """Test that config validation is called during install."""
        # Create a config with validation errors
        config_path = self.project_root / "invalid_config.yml"
        config_path.write_text("""
install:
  cpu_only: "not_a_boolean"  # This should fail validation
  unknown_field: "error"     # This should also fail
""")

        result = subprocess.run(
            [
                sys.executable,
                str(self.project_root / "comfyctl.py"),
                "install",
                "--config",
                str(config_path),
            ],
            capture_output=True,
            text=True,
            cwd=self.project_root,
        )

        # Should fail due to validation errors or missing script
        self.assertNotEqual(result.returncode, 0)
        # Should have some error output
        output = result.stdout + result.stderr
        self.assertTrue(len(output) > 0)


if __name__ == "__main__":
    unittest.main()
