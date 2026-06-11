# Production Readiness Plan: Maestro Cerebro Escrow

This document outlines the steps to move the local Escrow Service to a production-grade environment.

## Phase 1: Containerization (Local Development)
- [ ] Create a `Dockerfile` to package the FastAPI app.
- [ ] Create a `.dockerignore` to exclude local environment files.

## Phase 2: GCP Infrastructure Preparation (Cloud)
- [ ] **Crucial**: Ensure Billing is enabled on `maestro-cerebro-escrow-123456`.
- [ ] **Crucial**: Grant `maestrocerebro01@gmail.com` the `Editor` role on the project.
- [ ] Enable Artifact Registry to store the container image.
- [ ] Enable Cloud Run to host the service.

## Phase 3: Secure Configuration
- [ ] Migrate PayPal and Sentient Protocol keys to **GCP Secret Manager**.
- [ ] Configure Environment Variables for production URLs.

## Phase 4: Deployment
- [ ] Build and push the container to Artifact Registry.
- [ ] Deploy the service to Cloud Run.
- [ ] Map the custom domain: `escrow.maestro-cerebro.com`.

## Phase 5: Institutional Handshake
- [ ] Configure the secure gateway/VPN provided by the federal institution.
- [ ] Execute the final "Push" via an authorized production terminal.
