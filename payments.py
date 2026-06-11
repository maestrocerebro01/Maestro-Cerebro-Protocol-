import os
import httpx
import logging
import uuid
from dotenv import load_dotenv

load_dotenv()

class PayPalClient:
    def __init__(self):
        self.logger = logging.getLogger("PayPalClient")
        self.client_id = os.getenv("PAYPAL_CLIENT_ID")
        self.client_secret = os.getenv("PAYPAL_CLIENT_SECRET")
        self.mode = os.getenv("PAYPAL_MODE", "sandbox")
        
        if self.mode == "live":
            self.base_url = "https://api-m.paypal.com"
        else:
            self.base_url = "https://api-m.sandbox.paypal.com"

    async def get_access_token(self):
        if self.client_id == "your_paypal_client_id_here":
            return "mock_access_token"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/oauth2/token",
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            return response.json().get("access_token")

    async def generate_client_token(self):
        token = await self.get_access_token()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/identity/generate-token",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )
            response.raise_for_status()
            return response.json().get("client_token")

    async def create_order(self, amount: float, currency: str = "USD"):
        if self.client_id == "your_paypal_client_id_here":
            class Map:
                def __init__(self, **entries): self.__dict__.update(entries)
            class Link:
                def __init__(self, rel, href): self.rel = rel; self.href = href
            return Map(id="MOCK_ORDER_ID", links=[Link("approve", "https://paypal.com/mock-approve")])

        token = await self.get_access_token()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v2/checkout/orders",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                },
                json={
                    "intent": "AUTHORIZE",
                    "purchase_units": [
                        {
                            "amount": {
                                "currency_code": currency,
                                "value": str(amount)
                            }
                        }
                    ]
                }
            )
            response.raise_for_status()
            result = response.json()
            
            class Map:
                def __init__(self, **entries): self.__dict__.update(entries)
            class Link:
                def __init__(self, rel, href): self.rel = rel; self.href = href
            
            links = [Link(l['rel'], l['href']) for l in result.get('links', [])]
            return Map(id=result['id'], links=links)

    async def capture_order(self, order_id: str):
        if self.client_id == "your_paypal_client_id_here":
            return self._mock_capture_response()

        token = await self.get_access_token()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v2/checkout/orders/{order_id}/capture",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                }
            )
            response.raise_for_status()
            result = response.json()
            
            capture_id = "unknown"
            try:
                capture_id = result['purchase_units'][0]['payments']['captures'][0]['id']
            except (KeyError, IndexError):
                self.logger.warning(f"Could not extract capture ID from response: {result}")
            
            class Wrapper:
                def __init__(self, capture_id):
                    self.id = capture_id
            return Wrapper(capture_id)

    async def verify_webhook(self, transmission_id, transmission_time, cert_url, auth_algo, transmission_sig, webhook_id, body):
        token = await self.get_access_token()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/notifications/verify-webhook-signature",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                },
                json={
                    "transmission_id": transmission_id,
                    "transmission_time": transmission_time,
                    "cert_url": cert_url,
                    "auth_algo": auth_algo,
                    "transmission_sig": transmission_sig,
                    "webhook_id": webhook_id,
                    "webhook_event": body.decode('utf-8') if isinstance(body, bytes) else body
                }
            )
            response.raise_for_status()
            return response.json().get("verification_status") == "SUCCESS"

    async def get_user_info(self, auth_code: str):
        token = await self.get_access_token()
        async with httpx.AsyncClient() as client:
            # Exchange auth_code for identity token
            response = await client.post(
                f"{self.base_url}/v1/identity/openidconnect/tokenservice",
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "authorization_code", "code": auth_code}
            )
            response.raise_for_status()
            id_token = response.json().get("id_token")
            
            # Fetch user profile using the access token from this exchange
            access_token = response.json().get("access_token")
            user_info_resp = await client.get(
                f"{self.base_url}/v1/identity/openidconnect/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_info_resp.raise_for_status()
            return user_info_resp.json()

    async def create_payout(self, recipient_email: str, amount: float, currency: str = "USD"):
        token = await self.get_access_token()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/payments/payouts",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json={
                    "sender_batch_header": {
                        "sender_batch_id": f"batch_{uuid.uuid4()}",
                        "email_subject": "You have received a payout!"
                    },
                    "items": [
                        {
                            "recipient_type": "EMAIL",
                            "amount": {
                                "value": str(amount),
                                "currency": currency
                            },
                            "receiver": recipient_email
                        }
                    ]
                }
            )
            response.raise_for_status()
            return response.json()

    def _mock_capture_response(self):
        class Wrapper:
            def __init__(self, capture_id):
                self.id = capture_id
        return Wrapper("MOCK_CAPTURE_ID")

paypal = PayPalClient()
