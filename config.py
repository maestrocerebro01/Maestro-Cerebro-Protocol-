import os
import json
import logging
from google.cloud import secretmanager
from google.auth.exceptions import DefaultCredentialsError
from dotenv import load_dotenv

load_dotenv()

class Config:
    def __init__(self):
        self.project_id = os.getenv("GCP_PROJECT", "project-38af5abf-32a0-48ad-9a4")
        self.client = None
        try:
            self.client = secretmanager.SecretManagerServiceClient()
        except (DefaultCredentialsError, Exception):
            logging.warning("Secret Manager client could not be initialized. Falling back to environment variables.")

    def get_secret(self, secret_id, default=None):
        """
        Retrieves a secret from GCP Secret Manager.
        Falls back to environment variables if Secret Manager is unavailable or secret is not found.
        """
        if self.client:
            try:
                name = f"projects/{self.project_id}/secrets/{secret_id}/versions/latest"
                response = self.client.access_secret_version(request={"name": name})
                return response.payload.data.decode("UTF-8")
            except Exception as e:
                logging.debug(f"Could not fetch secret {secret_id} from Secret Manager: {str(e)}")
        
        # Fallback to env var
        return os.getenv(secret_id, default)

    @property
    def paypal_client_id(self):
        return self.get_secret("PAYPAL_CLIENT_ID")

    @property
    def paypal_client_secret(self):
        return self.get_secret("PAYPAL_CLIENT_SECRET")

    @property
    def sentient_protocol_project(self):
        return self.get_secret("GCP_PROJECT", self.project_id)

    @property
    def jwt_secret_key(self):
        return self.get_secret("JWT_SECRET_KEY")

    @property
    def global_api_secret(self):
        return self.get_secret("GLOBAL_API_SECRET")

    @property
    def stripe_api_key(self):
        return self.get_secret("STRIPE_API_KEY")

    @property
    def stripe_webhook_secret(self):
        return self.get_secret("STRIPE_WEBHOOK_SECRET")

    @property
    def stripe_mode(self):
        """Active Stripe environment: 'sandbox' (default) or 'live'."""
        return os.getenv("STRIPE_MODE", "sandbox").lower()

    def stripe_profile(self):
        """
        Load the non-secret Stripe config profile for the active environment.
        Profiles live in config/<sandbox|live>.json and hold only non-secret
        settings (secret *names*, destination reference, tax set-aside rate,
        FX source). Secrets themselves are never stored here.
        """
        profile_name = "live" if self.stripe_mode == "live" else "sandbox"
        path = os.path.join(os.path.dirname(__file__), "config", f"{profile_name}.json")
        try:
            with open(path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

# Global config instance
config = Config()
