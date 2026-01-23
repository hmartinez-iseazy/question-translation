import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import io


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_root_endpoint(self, client):
        """Test basic health check."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "question-translation"

    def test_live_endpoint(self, client):
        """Test liveness probe."""
        response = client.get("/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    def test_health_endpoint_healthy(self, client, mock_translator):
        """Test detailed health check when healthy."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "checks" in data

    def test_languages_endpoint(self, client):
        """Test languages list endpoint."""
        response = client.get("/languages")
        assert response.status_code == 200
        data = response.json()
        assert "languages" in data
        assert data["total"] > 0


class TestAuthentication:
    """Test API authentication."""

    def test_translate_without_api_key(self, client, sample_excel_bytes):
        """Test that translate endpoint requires API key."""
        response = client.post(
            "/translate",
            files={"file": ("test.xlsx", sample_excel_bytes)},
            data={"target_language": "en"},
        )
        assert response.status_code == 401

    def test_translate_with_invalid_api_key(self, client, sample_excel_bytes):
        """Test that invalid API key is rejected."""
        response = client.post(
            "/translate",
            files={"file": ("test.xlsx", sample_excel_bytes)},
            data={"target_language": "en"},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 403

    def test_usage_requires_auth(self, client):
        """Test that usage endpoint requires authentication."""
        response = client.get("/usage")
        assert response.status_code == 401


class TestValidation:
    """Test input validation."""

    def test_invalid_file_type(self, client, auth_headers):
        """Test that non-Excel files are rejected."""
        response = client.post(
            "/translate",
            files={"file": ("test.txt", b"not an excel file")},
            data={"target_language": "en"},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]

    def test_invalid_language_code(self, client, auth_headers, sample_excel_bytes):
        """Test that invalid language codes are rejected."""
        response = client.post(
            "/translate",
            files={"file": ("test.xlsx", sample_excel_bytes)},
            data={"target_language": "invalid_lang"},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Unknown language code" in response.json()["detail"]

    def test_batch_empty_languages(self, client, auth_headers, sample_excel_bytes):
        """Test that empty language list is rejected."""
        response = client.post(
            "/translate/batch",
            files={"file": ("test.xlsx", sample_excel_bytes)},
            data={"target_languages": ""},
            headers=auth_headers,
        )
        assert response.status_code == 400


class TestTranslation:
    """Test translation endpoints."""

    def test_translate_single_language(
        self, client, auth_headers, sample_excel_bytes
    ):
        """Test single language translation."""
        # Mock the processor
        with patch("src.main.get_excel_processor") as mock_processor:
            processor = MagicMock()
            processor.process_excel = AsyncMock(
                return_value=(sample_excel_bytes, "es", 1)
            )
            mock_processor.return_value = processor

            response = client.post(
                "/translate",
                files={"file": ("test.xlsx", sample_excel_bytes)},
                data={"target_language": "en"},
                headers=auth_headers,
            )

            assert response.status_code == 200
            assert (
                response.headers["content-type"]
                == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            assert "X-Rows-Translated" in response.headers

    def test_translate_batch(self, client, auth_headers, sample_excel_bytes):
        """Test batch translation to multiple languages."""
        with patch("src.main.get_excel_processor") as mock_processor:
            processor = MagicMock()
            processor.process_excel = AsyncMock(
                return_value=(sample_excel_bytes, "es", 1)
            )
            mock_processor.return_value = processor

            response = client.post(
                "/translate/batch",
                files={"file": ("test.xlsx", sample_excel_bytes)},
                data={"target_languages": "en,fr"},
                headers=auth_headers,
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/zip"
            assert "X-Files-Generated" in response.headers


class TestRateLimiting:
    """Test rate limiting."""

    def test_rate_limit_headers(self, client, auth_headers, sample_excel_bytes):
        """Test that rate limit headers are included."""
        with patch("src.main.get_excel_processor") as mock_processor:
            processor = MagicMock()
            processor.process_excel = AsyncMock(
                return_value=(sample_excel_bytes, "es", 1)
            )
            mock_processor.return_value = processor

            response = client.post(
                "/translate",
                files={"file": ("test.xlsx", sample_excel_bytes)},
                data={"target_language": "en"},
                headers=auth_headers,
            )

            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
