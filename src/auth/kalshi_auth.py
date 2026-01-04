"""RSA-PSS authentication for Kalshi API."""

import base64
import time
from pathlib import Path
from typing import Dict

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from src.utils.logger import get_logger

logger = get_logger("kalshi_bot.auth")


class KalshiAuth:
    """Handles RSA-PSS authentication for Kalshi API requests."""

    HEADER_KEY = "KALSHI-ACCESS-KEY"
    HEADER_SIGNATURE = "KALSHI-ACCESS-SIGNATURE"
    HEADER_TIMESTAMP = "KALSHI-ACCESS-TIMESTAMP"

    def __init__(self, api_key: str, private_key_path: Path) -> None:
        """
        Initialize authentication handler.

        Args:
            api_key: Kalshi API key
            private_key_path: Path to the RSA private key PEM file
        """
        self.api_key = api_key
        self._private_key = self._load_private_key(private_key_path)
        logger.info("Authentication handler initialized")

    def _load_private_key(self, key_path: Path):
        """
        Load RSA private key from PEM file.

        Args:
            key_path: Path to the PEM file

        Returns:
            Loaded private key object

        Raises:
            FileNotFoundError: If key file doesn't exist
            ValueError: If key is invalid
        """
        if not key_path.exists():
            raise FileNotFoundError(f"Private key not found: {key_path}")

        with open(key_path, "rb") as f:
            key_data = f.read()

        private_key = serialization.load_pem_private_key(
            key_data,
            password=None,  # Assumes unencrypted key
        )
        logger.debug("Private key loaded successfully")
        return private_key

    def _get_timestamp_ms(self) -> int:
        """Get current timestamp in milliseconds."""
        return int(time.time() * 1000)

    def _sign_message(self, message: str) -> str:
        """
        Sign a message using RSA-PSS with SHA256.

        Args:
            message: The message to sign

        Returns:
            Base64-encoded signature
        """
        message_bytes = message.encode("utf-8")

        signature = self._private_key.sign(
            message_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )

        return base64.b64encode(signature).decode("utf-8")

    def get_auth_headers(self, method: str, path: str) -> Dict[str, str]:
        """
        Generate authentication headers for an API request.

        The message to sign is: f"{timestamp_ms}{method}{path}"
        Note: path should NOT include query parameters.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            path: API path (e.g., /trade-api/v2/markets)

        Returns:
            Dictionary of authentication headers
        """
        timestamp_ms = self._get_timestamp_ms()

        # Kalshi expects: timestamp + method + path (no query params)
        message = f"{timestamp_ms}{method.upper()}{path}"

        signature = self._sign_message(message)

        headers = {
            self.HEADER_KEY: self.api_key,
            self.HEADER_SIGNATURE: signature,
            self.HEADER_TIMESTAMP: str(timestamp_ms),
        }

        logger.debug(f"Generated auth headers for {method} {path}")
        return headers

    def get_ws_auth_headers(self) -> Dict[str, str]:
        """
        Generate authentication headers for WebSocket connection.

        For WebSocket, the path is typically /trade-api/ws/v2 with GET method.

        Returns:
            Dictionary of authentication headers
        """
        return self.get_auth_headers("GET", "/trade-api/ws/v2")
