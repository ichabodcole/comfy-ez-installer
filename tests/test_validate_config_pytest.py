"""Pytest-based tests for validate_config.py using fixtures and test data."""

import pathlib
import subprocess
import sys

import pytest


class TestConfigValidationPytest:
    """Pytest-based configuration validation tests."""

    @pytest.fixture
    def validator_script(self):
        """Path to the validation script."""
        return pathlib.Path(__file__).parent.parent / "scripts" / "validate_config.py"

    def run_validator(self, validator_script, config_path):
        """Run the validator script and return (exit_code, stdout, stderr)."""
        result = subprocess.run(
            [sys.executable, str(validator_script), str(config_path)],
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout, result.stderr

    def test_valid_minimal_config(
        self, validator_script, valid_minimal_config, write_config_file
    ):
        """Test that a minimal valid config passes."""
        config_path = write_config_file(valid_minimal_config)
        exit_code, stdout, stderr = self.run_validator(validator_script, config_path)

        assert exit_code == 0
        assert "passed validation" in stdout

    def test_valid_full_config(
        self, validator_script, valid_full_config, write_config_file
    ):
        """Test that a comprehensive valid config passes."""
        config_path = write_config_file(valid_full_config)
        exit_code, stdout, stderr = self.run_validator(validator_script, config_path)

        assert exit_code == 0
        assert "passed validation" in stdout

    def test_invalid_config_structure(
        self, validator_script, invalid_config, write_config_file
    ):
        """Test that invalid config structure is rejected."""
        config_path = write_config_file(invalid_config)
        exit_code, stdout, stderr = self.run_validator(validator_script, config_path)

        assert exit_code == 1
        # Should contain validation errors
        output = stdout + stderr
        assert any(keyword in output for keyword in ["validation", "error", "invalid"])

    def test_unknown_top_level_key(self, validator_script, write_config_file):
        """Test that unknown top-level keys are rejected."""
        config = {"invalid_key": "value"}
        config_path = write_config_file(config)
        exit_code, stdout, stderr = self.run_validator(validator_script, config_path)

        assert exit_code == 1
        assert "Unknown top-level key: invalid_key" in stdout

    def test_invalid_install_section(self, validator_script, write_config_file):
        """Test validation of install section."""
        config = {"install": {"cpu_only": "not_a_boolean", "unknown_field": "value"}}
        config_path = write_config_file(config)
        exit_code, stdout, stderr = self.run_validator(validator_script, config_path)

        assert exit_code == 1
        assert "install.cpu_only must be boolean" in stdout
        assert "install: unknown key unknown_field" in stdout

    def test_missing_required_model_fields(self, validator_script, write_config_file):
        """Test validation of models section."""
        config = {
            "models": {
                "checkpoints": [
                    {"name": "missing urn/url/id"}  # Missing required field
                ]
            }
        }
        config_path = write_config_file(config)
        exit_code, stdout, stderr = self.run_validator(validator_script, config_path)

        assert exit_code == 1
        assert "must have 'urn', 'url', 'id', or 'ref' field" in stdout

    def test_conflicting_ref_and_content_fields(
        self, validator_script, write_config_file
    ):
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
        config_path = write_config_file(config)
        exit_code, stdout, stderr = self.run_validator(validator_script, config_path)

        assert exit_code == 1
        assert "cannot have both 'ref' and direct content fields" in stdout

    def test_invalid_workflow_reference(self, validator_script, write_config_file):
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
        config_path = write_config_file(config)
        exit_code, stdout, stderr = self.run_validator(validator_script, config_path)

        assert exit_code == 1
        assert "ref 'non-existent-model' not found in models.checkpoints" in stdout

    def test_workflow_missing_name(self, validator_script, write_config_file):
        """Test that workflows must have a name field."""
        config = {"workflows": [{"description": "Missing name field"}]}
        config_path = write_config_file(config)
        exit_code, stdout, stderr = self.run_validator(validator_script, config_path)

        assert exit_code == 1
        assert "missing 'name' field" in stdout

    def test_custom_nodes_missing_url(self, validator_script, write_config_file):
        """Test validation of custom_nodes section."""
        config = {
            "custom_nodes": [
                {"name": "Missing URL"}  # Missing required url field
            ]
        }
        config_path = write_config_file(config)
        exit_code, stdout, stderr = self.run_validator(validator_script, config_path)

        assert exit_code == 1
        assert "missing 'url' field" in stdout

    def test_nonexistent_file(self, validator_script, temp_dir):
        """Test handling of non-existent config file."""
        nonexistent_path = temp_dir / "does_not_exist.yml"
        exit_code, stdout, stderr = self.run_validator(
            validator_script, nonexistent_path
        )

        assert exit_code == 2
        assert "Please supply a valid path" in stderr

    def test_malformed_yaml(self, validator_script, temp_dir):
        """Test handling of malformed YAML."""
        config_path = temp_dir / "invalid.yml"
        config_path.write_text("invalid: yaml: content: [")  # Malformed YAML
        exit_code, stdout, stderr = self.run_validator(validator_script, config_path)

        assert exit_code == 1
        assert "YAML parsing error" in stderr
