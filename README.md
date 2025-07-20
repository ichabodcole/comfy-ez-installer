./# ComfyUI Docker Project

A complete Docker-based deployment solution for [ComfyUI](https://github.com/comfyanonymous/ComfyUI) with automated installation, YAML-driven configuration, and comprehensive model management.

## 🚀 Features

- **🐳 Docker Support**: Pre-configured containers for Mac (CPU) and GPU environments
- **📝 YAML Configuration**: Centralized, validated configuration system
- **🤖 Automated Installation**: One-command setup with dependency management
- **📦 Model Management**: Automated downloading from Civitai with concurrent downloads
- **🔗 Reference System**: Reusable model definitions and workflow-specific dependencies
- **🧪 Comprehensive Testing**: 59+ unit tests with pytest and coverage reporting
- **🔧 Code Quality**: Automated linting and formatting with ruff and pre-commit hooks
- **⚡ CLI Wrapper**: Simple `comfyctl` command for installation and management

## 📋 Quick Start

### Prerequisites

- **Docker & Docker Compose** (for containerized deployment)
- **Python 3.12+** and **uv** (for local development)
- **Git** (for cloning repositories)

### 1. Clone and Setup

```bash
git clone <your-repo-url> comfy_docker_project
cd comfy_docker_project

# Install dependencies
uv sync --dev
```

### 2. Configure Your Setup

Copy the example configuration:

```bash
cp config.example.yml config.yml
```

Edit `config.yml` to customize:
- **Install settings** (ComfyUI directory, CPU vs GPU)
- **Model definitions** (checkpoints, LoRAs, VAE, etc.)
- **Custom nodes** (additional ComfyUI extensions)
- **Workflows** (named collections of dependencies)

### 3. Deploy with Docker

#### For Mac (CPU-only):
```bash
docker-compose --profile mac up --build
```

#### For GPU environments:
```bash
docker-compose --profile gpu up --build
```

### 4. Local Installation

```bash
# Install ComfyUI and dependencies
./scripts/install_comfy_and_models.sh

# Or use the CLI wrapper
uv run python comfyctl.py install
```

## 🏗️ Project Structure

```
comfy_docker_project/
├── 📁 scripts/                 # Core installation and utility scripts
│   ├── install_comfy_and_models.sh    # Main installation script
│   ├── download_civitai_models.py     # Model download utility
│   ├── validate_config.py             # Configuration validator
│   └── entrypoint.sh                  # Docker container entrypoint
├── 📁 docker/                  # Docker configuration
│   ├── Dockerfile.mac                 # CPU-optimized for Mac
│   └── Dockerfile.runpod              # GPU-optimized container
├── 📁 tests/                   # Comprehensive test suite
│   ├── 📁 data/                       # Test YAML fixtures
│   ├── conftest.py                    # pytest configuration
│   └── test_*.py                      # Unit test modules
├── comfyctl.py                 # CLI wrapper for easy management
├── config.yml                 # Your configuration (create from example)
├── config.example.yml          # Example configuration with documentation
├── docker-compose.yml          # Docker orchestration
└── pyproject.toml             # Python project configuration
```

## ⚙️ Configuration

The system uses YAML configuration files for all setup. Here's a minimal example:

```yaml
# Minimal config.yml
install:
  comfy_dir: /workspace/ComfyUI
  cpu_only: false

models:
  dest_dir: /workspace/models
  checkpoints:
    - id: sdxl-base
      urn: urn:air:sdxl:checkpoint:civitai:101055
      name: SDXL Base 1.0

workflows:
  - name: basic-generation
    description: Basic image generation workflow
    models:
      checkpoints:
        - ref: sdxl-base
```

### Key Configuration Sections:

- **`install`**: ComfyUI installation settings
- **`models`**: Model definitions organized by category (checkpoints, loras, vae, etc.)
- **`custom_nodes`**: Additional ComfyUI extensions
- **`workflows`**: Named dependency collections for specific use cases

See `config.example.yml` for comprehensive documentation and examples.

## 🖥️ Usage

### CLI Commands

```bash
# Install ComfyUI with default config
uv run python comfyctl.py install

# Install with custom config
uv run python comfyctl.py install --config my-config.yml

# Install dependencies for specific workflow only
uv run python comfyctl.py install --workflow basic-generation

# Validate configuration file
uv run python comfyctl.py validate
uv run python comfyctl.py validate --config my-config.yml

# Start ComfyUI
uv run python comfyctl.py start
```

### Direct Script Usage

```bash
# Run installer directly
./scripts/install_comfy_and_models.sh

# Validate configuration (via CLI or direct script)
uv run python comfyctl.py validate --config config.yml
python scripts/validate_config.py config.yml

# Download models manually (new CLI interface)
python scripts/download_civitai_models.py --api-key YOUR_KEY --dest-dir models --checkpoints "model1,model2"

# Or use environment variables (backward compatible)
CIVITAI_API_KEY=your_key python scripts/download_civitai_models.py
```

### Environment Variables

Key environment variables for customization:

```bash
# Core settings
export COMFY_DIR="/path/to/ComfyUI"
export CPU_ONLY="true"                    # Force CPU-only installation
export AUTO_START="true"                  # Start ComfyUI after installation

# Model downloads (used by CLI and environment fallback)
export CIVITAI_API_KEY="your-api-key"     # For faster downloads
export CIVITAI_DOWNLOAD_THREADS="8"       # Concurrent downloads (default: 4)
# Note: CLI arguments take precedence over environment variables

# Configuration
export CONFIG_FILE="custom-config.yml"    # Use specific config file
export WORKFLOW="workflow-name"            # Install specific workflow only
```

## 🧪 Testing & Code Quality

### Run Tests with pytest (Recommended)

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=scripts --cov-report=html

# Run specific test modules
uv run pytest tests/test_validate_config.py -v

# Run tests matching pattern
uv run pytest -k "yaml or config"
```

### Linting & Formatting with Ruff

```bash
# Check for linting issues
uv run ruff check .

# Auto-fix issues where possible
uv run ruff check --fix .

# Format code
uv run ruff format .

# Run all checks + format + test (convenience script)
./scripts/lint.sh
```

### Pre-commit Hooks (Optional)

Automatically run linting and tests before each commit:

```bash
# Install pre-commit hooks
uv run pre-commit install

# Run hooks manually on all files
uv run pre-commit run --all-files

# Skip hooks for a specific commit (use sparingly)
git commit --no-verify -m "commit message"
```

### Alternative: Custom Test Runner

```bash
# Run all tests
python tests/test_runner.py

# Run specific module with verbose output
python tests/test_runner.py --test test_validate_config --verbose

# Run tests matching pattern
python tests/test_runner.py --pattern "*yaml*"
```

### Test Coverage

The project includes comprehensive tests covering:
- ✅ **Configuration validation** (23 tests)
- ✅ **YAML processing and references** (5 tests)  
- ✅ **CLI functionality** (14 tests)
- ✅ **Model download system** (17 tests)

**Current status: 59 passed, 1 skipped** 

## 🐳 Docker Deployment

### Mac Development (CPU-only)

```bash
# Build and run CPU-optimized container
docker-compose --profile mac up --build

# Access ComfyUI at http://localhost:8188
```

### GPU Production (RunPod/CUDA)

```bash
# Build and run GPU-optimized container  
docker-compose --profile gpu up --build

# Mount local models directory
docker-compose --profile gpu up -v ./models:/home/comfyuser/ComfyUI/models
```

### Container Features

- **Non-root user** (`comfyuser`) for security
- **Automatic dependency installation** from your config.yml
- **Model persistence** via volume mounts
- **Health checks** and proper signal handling
- **Multi-architecture support** (x86_64, arm64)

## 🔧 Development

### Setup Development Environment

```bash
# Clone repository
git clone <repo-url> && cd comfy_docker_project

# Install with development dependencies
uv sync --dev

# Optional: Set up pre-commit hooks for automatic code quality
uv run pre-commit install

# Run tests
uv run pytest --tb=short -v

# Check code quality
./scripts/lint.sh
```

### Adding New Features

1. **Add tests first** in `tests/test_*.py`
2. **Use test data fixtures** from `tests/data/`
3. **Run tests frequently** with `uv run pytest`
4. **Lint and format code** with `./scripts/lint.sh`
5. **Validate configs** with `uv run python comfyctl.py validate`
6. **Update documentation** as needed

### Code Organization

- **`scripts/`**: Core functionality (install, download, validate)
- **`tests/`**: Comprehensive test suite with fixtures
- **`docker/`**: Container definitions for different environments
- **Configuration**: YAML-based with validation and references

## 📚 Model Management

### Supported Sources

- **Civitai URNs**: `urn:air:sdxl:checkpoint:civitai:101055`
- **Direct URLs**: `https://example.com/model.safetensors`
- **Reference system**: Define once, reuse everywhere

### Model Categories

- `checkpoints` - Base models (SDXL, SD1.5, etc.)
- `loras` - LoRA adapters for style/concept training
- `vae` - Variational autoencoders for better image quality
- `embeddings` - Textual inversions and embeddings
- `controlnet` - ControlNet models for guided generation
- **Custom categories** - Define your own model types

### Concurrent Downloads

```bash
# Configure download threads (default: 4)
export CIVITAI_DOWNLOAD_THREADS=8

# Downloads are automatically parallelized
python scripts/download_civitai_models.py --download-threads 8 --api-key YOUR_KEY --dest-dir models
```

## 🚀 Roadmap

Planned enhancements (see `docs/enhancements/high_value_improvements.md`):

- [ ] **Idempotent custom node installation** (4/10 effort)
- [ ] **Model integrity verification** (4/10 effort)  
- [ ] **Shared download cache** (5/10 effort)
- [ ] **Auto-update system** (6/10 effort)
- [ ] **Web dashboard** (7/10 effort)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Add tests for your changes
4. Ensure all tests pass: `uv run pytest`
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) - The amazing node-based UI for Stable Diffusion
- [Civitai](https://civitai.com/) - Community model sharing platform
- [uv](https://github.com/astral-sh/uv) - Fast Python package manager

---

**Ready to get started?** Copy `config.example.yml` to `config.yml`, customize your setup, and run `uv run python comfyctl.py install`! 🎨
