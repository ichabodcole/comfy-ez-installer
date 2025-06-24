# ComfyUI Docker Project Tests

This directory contains comprehensive unit tests for the ComfyUI Docker Project scripts and configuration system.

## Test Structure

- `test_validate_config.py` - Tests for the YAML configuration validation system
- `test_yaml_processing.py` - Tests for YAML processing and reference resolution
- `test_comfyctl.py` - Tests for the comfyctl.py CLI wrapper
- `test_download_civitai.py` - Tests for the Civitai model download functionality
- `test_runner.py` - Test runner script with reporting and filtering capabilities

## Running Tests

### With pytest (Recommended)

#### Run All Tests
```bash
uv run pytest                    # Run all tests
uv run pytest -v                 # Verbose output  
uv run pytest --tb=short         # Short traceback format
```

#### Run Specific Tests
```bash
uv run pytest tests/test_validate_config_pytest.py    # Specific file
uv run pytest -k "test_valid"                         # Tests matching pattern
uv run pytest tests/test_validate_config.py::TestConfigValidation::test_valid_minimal_config  # Specific test
```

#### Coverage and Reporting
```bash
uv run pytest --cov=scripts      # With coverage report
uv run pytest --cov=scripts --cov-report=html  # HTML coverage report
```

### With Custom Test Runner (Alternative)

#### Run All Tests
```bash
python tests/test_runner.py
```

#### Run Specific Test Module
```bash
python tests/test_runner.py --test test_validate_config
```

#### Run Tests with Different Verbosity
```bash
python tests/test_runner.py --quiet           # Minimal output
python tests/test_runner.py --verbose         # Detailed output
python tests/test_runner.py --verbosity 1     # Normal output
```

#### Run Tests Matching a Pattern
```bash
python tests/test_runner.py --pattern "*yaml*"    # Run YAML-related tests
python tests/test_runner.py --pattern "*config*"  # Run config-related tests
```

#### Other Options
```bash
python tests/test_runner.py --failfast        # Stop on first failure
python tests/test_runner.py --no-deps-check   # Skip dependency check
```

## Test Coverage

### Validation Tests (`test_validate_config.py`)
- Valid and invalid YAML configurations
- Schema validation rules
- Reference validation between workflows and models
- Error handling and reporting

### YAML Processing Tests (`test_yaml_processing.py`)
- Configuration parsing and environment variable export
- Model reference resolution
- Workflow-specific dependency merging
- Support for arbitrary model categories

### CLI Tests (`test_comfyctl.py`)
- Command-line argument parsing
- Help text generation
- Configuration file handling
- Error scenarios and validation integration

### Download Tests (`test_download_civitai.py`)
- URN parsing and validation
- Direct URL handling
- Civitai API interaction (mocked)
- File path generation and conflict handling
- Concurrent download configuration

## Dependencies

The tests require the following Python packages:
- `PyYAML` - for YAML processing tests
- `requests` - for download functionality tests

Missing dependencies will cause related tests to be skipped with appropriate warnings.

## Test Data

Tests use temporary directories and mock objects to avoid:
- Network requests during testing
- File system pollution
- Dependency on external services

## Known Issues

Some tests in `test_download_civitai.py` may be sensitive to exact mock configuration and could require adjustment if the underlying download implementation changes significantly.

## Contributing

When adding new functionality:
1. Add corresponding unit tests
2. Ensure tests are isolated and don't depend on external resources
3. Use descriptive test names that explain what is being tested
4. Mock external dependencies appropriately
5. Add any new test dependencies to this README 