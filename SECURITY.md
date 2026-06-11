# Security Checklist for Maestro Cerebro Escrow

Before deploying to production, ensure these items are addressed:

- [ ] **HTTPS/TLS**: Ensure the production domain has a valid SSL/TLS certificate.
- [ ] **Secret Manager**: Migrate all values from `.env` to **GCP Secret Manager**.
- [ ] **Authentication**: Add an authentication layer (e.g., Auth0, Firebase Auth) to `/transactions/` endpoints.
- [ ] **Origin Restriction**: In `paypal-wrapper.html`, update `TARGET` to *only* your production domain (remove the `localhost` fallback).
- [ ] **Content Security Policy (CSP)**: Implement a strict CSP header in FastAPI to prevent loading unauthorized scripts.
- [ ] **Rate Limiting**: Add a rate-limiting middleware (e.g., `slowapi`) to protect against brute-force or DoS attacks.
- [ ] **Audit Logging**: Ensure logs do not contain PII or sensitive API secrets.
- [ ] **Production Credentials**: Set `PAYPAL_MODE=live` and use production PayPal credentials.
