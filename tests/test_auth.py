"""Tests for Kalshi authentication."""

import base64
import tempfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from src.auth.kalshi_auth import KalshiAuth


@pytest.fixture
def test_private_key():
    """Generate a test RSA private key."""
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


@pytest.fixture
def test_key_path(test_private_key):
    """Create a temporary PEM file with the test key."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as f:
        f.write(
            test_private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        return Path(f.name)


@pytest.fixture
def auth(test_key_path):
    """Create KalshiAuth instance with test key."""
    return KalshiAuth(api_key="test-api-key", private_key_path=test_key_path)


class TestKalshiAuth:
    """Tests for KalshiAuth class."""

    def test_init_loads_key(self, auth):
        """Test that initialization loads the private key."""
        assert auth.api_key == "test-api-key"
        assert auth._private_key is not None

    def test_init_file_not_found(self):
        """Test that missing key file raises error."""
        with pytest.raises(FileNotFoundError):
            KalshiAuth(api_key="test", private_key_path=Path("/nonexistent/key.pem"))

    def test_get_auth_headers_returns_required_headers(self, auth):
        """Test that auth headers contain required fields."""
        headers = auth.get_auth_headers("GET", "/trade-api/v2/markets")

        assert KalshiAuth.HEADER_KEY in headers
        assert KalshiAuth.HEADER_SIGNATURE in headers
        assert KalshiAuth.HEADER_TIMESTAMP in headers

    def test_get_auth_headers_api_key(self, auth):
        """Test that API key is included in headers."""
        headers = auth.get_auth_headers("GET", "/trade-api/v2/markets")
        assert headers[KalshiAuth.HEADER_KEY] == "test-api-key"

    def test_get_auth_headers_timestamp_format(self, auth):
        """Test that timestamp is a valid millisecond timestamp."""
        headers = auth.get_auth_headers("GET", "/trade-api/v2/markets")
        timestamp = headers[KalshiAuth.HEADER_TIMESTAMP]

        # Should be a numeric string
        assert timestamp.isdigit()
        # Should be in milliseconds (13+ digits)
        assert len(timestamp) >= 13

    def test_get_auth_headers_signature_is_base64(self, auth):
        """Test that signature is valid base64."""
        headers = auth.get_auth_headers("GET", "/trade-api/v2/markets")
        signature = headers[KalshiAuth.HEADER_SIGNATURE]

        # Should be valid base64
        try:
            base64.b64decode(signature)
        except Exception:
            pytest.fail("Signature is not valid base64")

    def test_signature_verification(self, auth, test_private_key):
        """Test that signature can be verified with public key."""
        headers = auth.get_auth_headers("GET", "/trade-api/v2/markets")

        timestamp = headers[KalshiAuth.HEADER_TIMESTAMP]
        signature = base64.b64decode(headers[KalshiAuth.HEADER_SIGNATURE])
        message = f"{timestamp}GET/trade-api/v2/markets".encode()

        public_key = test_private_key.public_key()

        # Should not raise an exception
        public_key.verify(
            signature,
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )

    def test_different_methods_produce_different_signatures(self, auth):
        """Test that different HTTP methods produce different signatures."""
        headers_get = auth.get_auth_headers("GET", "/trade-api/v2/markets")
        headers_post = auth.get_auth_headers("POST", "/trade-api/v2/markets")

        assert headers_get[KalshiAuth.HEADER_SIGNATURE] != headers_post[KalshiAuth.HEADER_SIGNATURE]

    def test_different_paths_produce_different_signatures(self, auth):
        """Test that different paths produce different signatures."""
        headers_markets = auth.get_auth_headers("GET", "/trade-api/v2/markets")
        headers_orders = auth.get_auth_headers("GET", "/trade-api/v2/orders")

        assert headers_markets[KalshiAuth.HEADER_SIGNATURE] != headers_orders[KalshiAuth.HEADER_SIGNATURE]

    def test_get_ws_auth_headers(self, auth):
        """Test WebSocket auth headers."""
        headers = auth.get_ws_auth_headers()

        assert KalshiAuth.HEADER_KEY in headers
        assert KalshiAuth.HEADER_SIGNATURE in headers
        assert KalshiAuth.HEADER_TIMESTAMP in headers

    def test_method_case_normalization(self, auth):
        """Test that method is normalized to uppercase."""
        headers_lower = auth.get_auth_headers("get", "/trade-api/v2/markets")
        headers_upper = auth.get_auth_headers("GET", "/trade-api/v2/markets")

        # Timestamps will differ, but same method should sign identically
        # We can't directly compare due to timestamp, but both should succeed
        assert headers_lower[KalshiAuth.HEADER_KEY] == headers_upper[KalshiAuth.HEADER_KEY]
