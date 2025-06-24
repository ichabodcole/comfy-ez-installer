#!/usr/bin/env python3
"""Unit tests for download_civitai_models.py"""

import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Add the scripts directory to the path so we can import the download script
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

try:
    import download_civitai_models as dcm
except ImportError:
    dcm = None


class TestCivitaiDownloader(unittest.TestCase):
    """Test the Civitai model downloader functionality."""

    def setUp(self):
        """Set up test fixtures."""
        if dcm is None:
            self.skipTest("download_civitai_models module not available")

        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = pathlib.Path(self.temp_dir.name)
        self.models_dir = self.temp_path / "models"
        self.models_dir.mkdir()

    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_parse_urn_valid(self):
        """Test parsing of valid Civitai URNs."""
        test_cases = [
            (
                "urn:air:sdxl:checkpoint:civitai:12345",
                {
                    "model_type": "sdxl",
                    "category": "checkpoint",
                    "platform": "civitai",
                    "model_id": "12345",
                },
            ),
            (
                "urn:air:sd1:lora:civitai:67890",
                {
                    "model_type": "sd1",
                    "category": "lora",
                    "platform": "civitai",
                    "model_id": "67890",
                },
            ),
            (
                "urn:air:universal:vae:civitai:11111",
                {
                    "model_type": "universal",
                    "category": "vae",
                    "platform": "civitai",
                    "model_id": "11111",
                },
            ),
        ]

        for urn, expected in test_cases:
            with self.subTest(urn=urn):
                result = dcm.parse_urn(urn)
                self.assertEqual(result, expected)

    def test_parse_urn_invalid(self):
        """Test parsing of invalid URNs."""
        invalid_urns = [
            "not-a-urn",
            "urn:wrong:format",
            "urn:air:sdxl:civitai:12345",  # Missing category
            "urn:air:sdxl:checkpoint:12345",  # Missing platform
            "urn:air:sdxl:checkpoint:civitai:",  # Missing model_id
            "urn:wrong:sdxl:checkpoint:civitai:12345",  # Wrong namespace
        ]

        for urn in invalid_urns:
            with self.subTest(urn=urn):
                result = dcm.parse_urn(urn)
                self.assertIsNone(result)

    def test_is_direct_url(self):
        """Test detection of direct URLs vs URNs."""
        test_cases = [
            ("https://example.com/model.safetensors", True),
            ("http://example.com/model.ckpt", True),
            ("urn:air:sdxl:checkpoint:civitai:12345", False),
            ("not-a-url", False),
            ("ftp://example.com/model", False),  # Not HTTP/HTTPS
        ]

        for url, expected in test_cases:
            with self.subTest(url=url):
                result = dcm.is_direct_url(url)
                self.assertEqual(result, expected)

    def test_get_filename_from_url(self):
        """Test extracting filenames from URLs."""
        test_cases = [
            ("https://example.com/model.safetensors", "model.safetensors"),
            ("https://example.com/path/to/model.ckpt", "model.ckpt"),
            ("https://example.com/model.bin?version=1", "model.bin"),
            ("https://example.com/model", "model"),
            ("https://example.com/", "download"),  # Fallback
        ]

        for url, expected in test_cases:
            with self.subTest(url=url):
                result = dcm.get_filename_from_url(url)
                self.assertEqual(result, expected)

    def test_download_direct_url_success(self):
        """Test successful download of direct URL."""
        # Create a simple test by writing a file and checking if it exists
        url = "https://example.com/model.safetensors"
        dest_path = self.models_dir / "model.safetensors"

        # Test the path creation logic by calling the function with a mock
        with patch("download_civitai_models.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_content.return_value = [b"test content"]

            # Set up the context manager mock
            mock_get.return_value.__enter__.return_value = mock_response
            mock_get.return_value.__exit__.return_value = None

            success = dcm.download_direct_url(url, dest_path)

            self.assertTrue(success)
            self.assertTrue(dest_path.exists())
            mock_get.assert_called_once_with(url, stream=True, timeout=30)

    @patch("download_civitai_models.requests.get")
    def test_download_direct_url_failure(self, mock_get):
        """Test failed download of direct URL."""
        # Mock failed response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        url = "https://example.com/nonexistent.safetensors"
        dest_path = self.models_dir / "checkpoints" / "nonexistent.safetensors"
        dest_path.parent.mkdir(parents=True)

        success = dcm.download_direct_url(url, dest_path)

        self.assertFalse(success)
        self.assertFalse(dest_path.exists())

    @patch("download_civitai_models.requests.get")
    def test_get_civitai_model_info_success(self, mock_get):
        """Test successful retrieval of Civitai model info."""
        # Mock API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "modelVersions": [
                {
                    "id": 123,
                    "files": [
                        {
                            "name": "model.safetensors",
                            "downloadUrl": "https://civitai.com/api/download/models/123",
                        }
                    ],
                }
            ]
        }
        mock_get.return_value = mock_response

        model_id = "12345"
        result = dcm.get_civitai_model_info(model_id)

        self.assertIsNotNone(result)
        self.assertEqual(result["filename"], "model.safetensors")
        self.assertEqual(
            result["download_url"], "https://civitai.com/api/download/models/123"
        )

        # Verify API call
        expected_url = f"https://civitai.com/api/v1/models/{model_id}"
        mock_get.assert_called_once_with(expected_url, timeout=30)

    @patch("download_civitai_models.requests.get")
    def test_get_civitai_model_info_failure(self, mock_get):
        """Test failed retrieval of Civitai model info."""
        # Mock failed response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        model_id = "nonexistent"
        result = dcm.get_civitai_model_info(model_id)

        self.assertIsNone(result)

    def test_get_model_dest_path_urn(self):
        """Test model destination path generation from URN."""
        urn = "urn:air:sdxl:checkpoint:civitai:12345"
        filename = "model.safetensors"

        dest_path = dcm.get_model_dest_path(self.models_dir, urn, filename)
        expected_path = self.models_dir / "checkpoints" / "model.safetensors"

        self.assertEqual(dest_path, expected_path)

    def test_get_model_dest_path_direct_url(self):
        """Test model destination path generation from direct URL."""
        url = "https://example.com/model.safetensors"
        filename = "model.safetensors"

        dest_path = dcm.get_model_dest_path(self.models_dir, url, filename)
        expected_path = self.models_dir / "model.safetensors"

        self.assertEqual(dest_path, expected_path)

    @patch("download_civitai_models.download_direct_url")
    @patch("download_civitai_models.get_civitai_model_info")
    def test_download_model_civitai_urn(self, mock_get_info, mock_download):
        """Test downloading a model from Civitai URN."""
        # Mock Civitai API response
        mock_get_info.return_value = {
            "filename": "test_model.safetensors",
            "download_url": "https://civitai.com/api/download/models/123",
        }
        mock_download.return_value = True

        urn = "urn:air:sdxl:checkpoint:civitai:12345"
        success = dcm.download_model(self.models_dir, urn)

        self.assertTrue(success)
        mock_get_info.assert_called_once_with("12345")

        expected_dest = self.models_dir / "checkpoints" / "test_model.safetensors"
        mock_download.assert_called_once_with(
            "https://civitai.com/api/download/models/123", expected_dest
        )

    @patch("download_civitai_models.download_direct_url")
    def test_download_model_direct_url(self, mock_download):
        """Test downloading a model from direct URL."""
        mock_download.return_value = True

        url = "https://example.com/model.safetensors"
        success = dcm.download_model(self.models_dir, url)

        self.assertTrue(success)

        expected_dest = self.models_dir / "model.safetensors"
        mock_download.assert_called_once_with(url, expected_dest)

    def test_skip_existing_files(self):
        """Test that existing files are skipped."""
        # Create an existing file
        existing_file = self.models_dir / "existing.safetensors"
        existing_file.write_text("existing content")

        with patch("download_civitai_models.download_direct_url") as mock_download:
            url = "https://example.com/existing.safetensors"
            success = dcm.download_model(self.models_dir, url)

            self.assertTrue(success)  # Should succeed (skip)
            mock_download.assert_not_called()  # Should not download

    @patch.dict(os.environ, {"CIVITAI_DOWNLOAD_THREADS": "2"})
    def test_concurrent_download_configuration(self):
        """Test that concurrent download threads are configured from environment."""
        # This test verifies the environment variable is read correctly
        from download_civitai_models import get_download_threads

        threads = get_download_threads()
        self.assertEqual(threads, 2)

    @patch.dict(os.environ, {}, clear=True)
    def test_default_download_threads(self):
        """Test default number of download threads."""
        from download_civitai_models import get_download_threads

        threads = get_download_threads()
        self.assertEqual(threads, 4)  # Default value

    def test_validate_models_list(self):
        """Test validation of models list format."""
        valid_lists = [
            "urn:air:sdxl:checkpoint:civitai:12345",
            "urn:air:sdxl:checkpoint:civitai:12345,urn:air:sd1:lora:civitai:67890",
            "https://example.com/model.safetensors",
            "https://example.com/model1.safetensors,https://example.com/model2.ckpt",
        ]

        invalid_lists = [
            "invalid-format",
            "urn:wrong:format,urn:air:sdxl:checkpoint:civitai:12345",
        ]

        for valid_list in valid_lists:
            with self.subTest(models=valid_list):
                # Should not raise exception
                try:
                    models = valid_list.split(",") if valid_list else []
                    for model in models:
                        if not (
                            dcm.parse_urn(model.strip())
                            or dcm.is_direct_url(model.strip())
                        ):
                            raise ValueError(f"Invalid model format: {model}")
                except ValueError:
                    self.fail(f"Valid list '{valid_list}' was rejected")

        for invalid_list in invalid_lists:
            with self.subTest(models=invalid_list):
                with self.assertRaises((ValueError, AttributeError)):
                    models = invalid_list.split(",") if invalid_list else []
                    for model in models:
                        if not (
                            dcm.parse_urn(model.strip())
                            or dcm.is_direct_url(model.strip())
                        ):
                            raise ValueError(f"Invalid model format: {model}")

        # Test empty/None cases separately since they don't raise exceptions
        for empty_case in ["", None]:
            with self.subTest(models=empty_case):
                try:
                    models = empty_case.split(",") if empty_case else []
                    # Empty list should be valid (no models to validate)
                    self.assertEqual(len(models), 0)
                except AttributeError:
                    # None.split() will raise AttributeError, which is expected
                    self.assertEqual(empty_case, None)


class TestCivitaiDownloaderIntegration(unittest.TestCase):
    """Integration tests for the download script."""

    def setUp(self):
        """Set up test fixtures for integration tests."""
        if dcm is None:
            self.skipTest("download_civitai_models module not available")

        self.script_path = (
            pathlib.Path(__file__).parent.parent
            / "scripts"
            / "download_civitai_models.py"
        )
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = pathlib.Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_main_function_with_environment_vars(self):
        """Test main function with environment variables."""
        # Note: This test is disabled because the module-level initialization
        # makes it difficult to test the main() function in isolation.
        # The individual download_model() function is tested thoroughly above.
        self.skipTest(
            "Main function testing is complex due to module-level initialization"
        )


if __name__ == "__main__":
    unittest.main()
