import os
import unittest
from unittest.mock import patch

# Minimal env required by core.config.Settings at import time
os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "https://s3.amazonaws.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")

from fastapi import HTTPException
from utils import auth


class TestAppleAudienceValidation(unittest.TestCase):
    @patch("utils.auth.get_apple_keys")
    @patch("utils.auth.jwt.algorithms.RSAAlgorithm.from_jwk")
    @patch("utils.auth.jwt.get_unverified_header")
    @patch("utils.auth.jwt.decode")
    def test_main_app_audience_is_accepted(self, mock_decode, mock_header, mock_from_jwk, mock_get_keys):
        mock_get_keys.return_value = [{"kid": "kid-1", "kty": "RSA"}]
        mock_header.return_value = {"kid": "kid-1", "alg": "RS256"}
        mock_from_jwk.return_value = "rsa-key"
        mock_decode.return_value = {
            "sub": "apple-sub-main",
            "email": "main@example.com",
            "is_private_email": False,
        }

        with patch.object(
            auth.settings,
            "apple_allowed_audiences",
            "com.example.mainapp,org.example.project.appmensajeros3978ubka75",
        ):
            result = auth.verify_apple("token-main")

        self.assertEqual(result["sub"], "apple-sub-main")
        self.assertEqual(
            mock_decode.call_args.kwargs["audience"],
            ["com.example.mainapp", "org.example.project.appmensajeros3978ubka75"],
        )

    @patch("utils.auth.get_apple_keys")
    @patch("utils.auth.jwt.algorithms.RSAAlgorithm.from_jwk")
    @patch("utils.auth.jwt.get_unverified_header")
    @patch("utils.auth.jwt.decode")
    def test_messenger_app_audience_is_accepted(self, mock_decode, mock_header, mock_from_jwk, mock_get_keys):
        mock_get_keys.return_value = [{"kid": "kid-1", "kty": "RSA"}]
        mock_header.return_value = {"kid": "kid-1", "alg": "RS256"}
        mock_from_jwk.return_value = "rsa-key"
        mock_decode.return_value = {
            "sub": "apple-sub-messenger",
            "email": "messenger@example.com",
            "is_private_email": True,
        }

        with patch.object(
            auth.settings,
            "apple_allowed_audiences",
            "com.example.mainapp,org.example.project.appmensajeros3978ubka75",
        ):
            result = auth.verify_apple("token-messenger")

        self.assertEqual(result["sub"], "apple-sub-messenger")
        self.assertEqual(
            mock_decode.call_args.kwargs["audience"],
            ["com.example.mainapp", "org.example.project.appmensajeros3978ubka75"],
        )

    @patch("utils.auth.get_apple_keys")
    @patch("utils.auth.jwt.algorithms.RSAAlgorithm.from_jwk")
    @patch("utils.auth.jwt.get_unverified_header")
    @patch("utils.auth.jwt.decode")
    def test_unknown_audience_is_rejected(self, mock_decode, mock_header, mock_from_jwk, mock_get_keys):
        mock_get_keys.return_value = [{"kid": "kid-1", "kty": "RSA"}]
        mock_header.return_value = {"kid": "kid-1", "alg": "RS256"}
        mock_from_jwk.return_value = "rsa-key"
        mock_decode.side_effect = Exception("Audience doesn't match")

        with patch.object(
            auth.settings,
            "apple_allowed_audiences",
            "com.example.mainapp,org.example.project.appmensajeros3978ubka75",
        ):
            with self.assertRaises(HTTPException) as ctx:
                auth.verify_apple("token-unknown")

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("Invalid Apple token", ctx.exception.detail)

    @patch("utils.auth.get_apple_keys")
    @patch("utils.auth.jwt.algorithms.RSAAlgorithm.from_jwk")
    @patch("utils.auth.jwt.get_unverified_header")
    @patch("utils.auth.jwt.decode")
    def test_invalid_or_expired_token_is_rejected(self, mock_decode, mock_header, mock_from_jwk, mock_get_keys):
        mock_get_keys.return_value = [{"kid": "kid-1", "kty": "RSA"}]
        mock_header.return_value = {"kid": "kid-1", "alg": "RS256"}
        mock_from_jwk.return_value = "rsa-key"
        mock_decode.side_effect = Exception("Signature has expired")

        with patch.object(
            auth.settings,
            "apple_allowed_audiences",
            "com.example.mainapp,org.example.project.appmensajeros3978ubka75",
        ):
            with self.assertRaises(HTTPException) as ctx:
                auth.verify_apple("expired-token")

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("Invalid Apple token", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
