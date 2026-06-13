import os
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

# Global config instance
config = Config()
