"""Pytest configuration and shared fixtures."""

import pathlib
import sys
import tempfile
from typing import Any

import pytest

# Add project modules to path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

try:
    import yaml
except ImportError:
    yaml = None


@pytest.fixture
def temp_dir():
    """Provide a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield pathlib.Path(tmpdir)


@pytest.fixture
def test_data_dir():
    """Provide the test data directory path."""
    return pathlib.Path(__file__).parent / "data"


@pytest.fixture
def valid_minimal_config(test_data_dir):
    """Load minimal valid config from test data."""
    config_path = test_data_dir / "valid_minimal_config.yml"
    if yaml and config_path.exists():
        return yaml.safe_load(config_path.read_text())
    return {}


@pytest.fixture
def valid_full_config(test_data_dir):
    """Load comprehensive valid config from test data."""
    config_path = test_data_dir / "valid_full_config.yml"
    if yaml and config_path.exists():
        return yaml.safe_load(config_path.read_text())
    return {}


@pytest.fixture
def invalid_config(test_data_dir):
    """Load invalid config from test data."""
    config_path = test_data_dir / "invalid_config.yml"
    if yaml and config_path.exists():
        return yaml.safe_load(config_path.read_text())
    return {}


@pytest.fixture
def workflow_config(test_data_dir):
    """Load workflow test config from test data."""
    config_path = test_data_dir / "workflow_config.yml"
    if yaml and config_path.exists():
        return yaml.safe_load(config_path.read_text())
    return {}


@pytest.fixture
def write_config_file(temp_dir):
    """Factory to write config data to a temporary file."""

    def _write_config(
        config_data: dict[str, Any], filename: str = "config.yml"
    ) -> pathlib.Path:
        if yaml is None:
            pytest.skip("PyYAML not available")

        config_path = temp_dir / filename
        config_path.write_text(yaml.dump(config_data))
        return config_path

    return _write_config


@pytest.fixture(autouse=True)
def skip_if_no_yaml():
    """Automatically skip YAML-related tests if PyYAML is not available."""
    if yaml is None:
        pytest.skip("PyYAML not available")


@pytest.fixture
def models_dir(temp_dir):
    """Provide a temporary models directory."""
    models_dir = temp_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir
