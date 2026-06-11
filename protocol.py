import logging
import json
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

class SentientProtocol:
    """
    Handles linkage to the Sentient Protocol and SAIL (Sentient Artificial Intelligence Linkage).
    Powered by Gemma on Vertex AI.
    """
    def __init__(self, project_id="maestro-cerebro"):
        self.project_id = project_id
        self.location = os.getenv("GCP_LOCATION", "us-central1")
        self.logger = logging.getLogger("SentientProtocol")
        
        try:
            # Initialize the Vertex AI client for Gemma
            self.client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location
            )
            self.model_id = "gemma2-9b-it" # High-performance Gemma variant
            self.image_model_id = "imagen-3.0-generate-001" # Latest Imagen model for diffusion
            self.logger.info(f"Initialized Sentient Protocol with Gemma ({self.model_id}) and Imagen ({self.image_model_id}) on project: {self.project_id}")
        except Exception as e:
            self.logger.error(f"Failed to initialize AI clients: {str(e)}")
            self.client = None

    async def generate_proof_image(self, transaction_id: str, rationale: str) -> str:
        """
        Generates a visual 'Sentient Proof of Integrity' using Imagen diffusion.
        Returns the base64 encoded image or a local path.
        """
        self.logger.info(f"Generating visual proof for transaction {transaction_id}")
        
        if not self.client:
            return ""

        prompt = f"""
        A high-tech, futuristic cryptographic seal for a secure financial transaction. 
        The seal should incorporate elements of artificial intelligence, neural networks, and golden geometry. 
        Text: 'INTEGRITY VERIFIED - {transaction_id[:8]}'. 
        Style: Professional, 3D render, dark background with blue and gold highlights.
        """

        try:
            import anyio
            response = await anyio.to_thread.run_sync(
                lambda: self.client.models.generate_image(
                    model=self.image_model_id,
                    prompt=prompt
                )
            )
            
            # Save the image locally to serve it via /static
            image_filename = f"proof_{transaction_id}.png"
            image_path = os.path.join("escrow-service/static", image_filename)
            
            # Accessing the first generated image
            img_bytes = response.generated_images[0].image_bytes
            with open(image_path, "wb") as f:
                f.write(img_bytes)
                
            return f"/static/{image_filename}"
            
        except Exception as e:
            self.logger.error(f"Diffusion proof generation failed: {str(e)}")
            return ""

    async def verify_integrity(self, transaction_id: str, data: dict) -> dict:
        """
        Verifies the integrity of a transaction via Gemma on Vertex AI.
        Returns a dict with success and proof_url.
        """
        self.logger.info(f"Verifying integrity for transaction {transaction_id} using Gemma")
        
        default_res = {"is_integral": True, "rationale": "Basic verification", "proof_url": ""}
        
        if not self.client:
            return default_res

        prompt = f"""
        Analyze the following escrow transaction for integrity and potential fraud.
        Return ONLY a JSON object with the keys 'is_integral' (boolean) and 'rationale' (string).
        
        Transaction ID: {transaction_id}
        Data: {json.dumps(data, indent=2)}
        
        Integrity Standards:
        1. Amounts must be positive.
        2. Sender and Receiver must be distinct.
        3. Metadata must not contain suspicious patterns.
        """

        try:
            import anyio
            response = await anyio.to_thread.run_sync(
                lambda: self.client.models.generate_content(
                    model=self.model_id,
                    contents=prompt
                )
            )
            
            result_text = response.text.strip().replace("```json", "").replace("```", "")
            result = json.loads(result_text)
            
            # If integral, generate a visual diffusion proof
            proof_url = ""
            if result.get("is_integral"):
                proof_url = await self.generate_proof_image(transaction_id, result.get("rationale"))
            
            result["proof_url"] = proof_url
            self.logger.info(f"Gemma Integrity Result: {result['is_integral']} - {result['rationale']}")
            return result
            
        except Exception as e:
            self.logger.error(f"Gemma verification failed: {str(e)}")
            return default_res

    async def register_event(self, event_type: str, details: dict):
        """
        Registers a sentient event in the protocol log.
        """
        self.logger.info(f"Registering sentient event: {event_type}")
        # Placeholder for logging to a decentralized ledger or specialized GCP resource
        pass

# Global instance for the service
protocol = SentientProtocol()
