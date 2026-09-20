# MetaScreener

MetaScreener is an AI-powered systematic review and meta-analysis screening tool designed to accelerate the literature review process. It provides a secure, cross-platform interface for importing papers, identifying duplicates, and leveraging AI models (such as local Ollama, OpenAI, or Anthropic) for title and abstract screening.

## Architecture

The application is built using a modern decoupled Client-Server architecture:
- **Backend (`MetaScreener_Web`):** A secure Python Flask REST API handling data processing, database management, and AI inference. Secured with JWT authentication.
- **Frontend (`MetaScreener_UI`):** A responsive, cross-platform Single Page Application (SPA) built with React, TypeScript, Vite, and Tailwind CSS.

## Features

- **Import & Deduplication:** Upload RIS/CSV files and automatically flag or merge exact duplicate papers.
- **AI-Assisted Screening:** Connect to local or cloud-based LLMs to dramatically reduce screening workload while maintaining high recall.
- **PRISMA Flow Tracking:** Automatically generates and tracks PRISMA flowchart data.
- **Cross-Platform Ready:** The decoupled architecture allows the UI to be wrapped for Desktop (Tauri/Electron) or Mobile (Capacitor) easily.

## Getting Started

### 1. Start the API Backend
```bash
cd MetaScreener_Web
pip install -r requirements.txt
python app.py
```
*(Ensure you have set the `ADMIN_PASSWORD` environment variable for security).*

### 2. Start the Frontend UI
```bash
cd MetaScreener_UI
npm install
npm run dev
```

## Continuous Integration / Continuous Deployment (CI/CD)

This repository includes pre-configured GitHub Actions:
- **GitHub Pages Deploy (`pages.yml`):** Automatically builds and deploys the React frontend to GitHub Pages upon pushing to the `main` branch.
- **Automated Releases (`release.yml`):** Automatically creates clean `.zip` artifacts of the UI and Backend whenever a new version tag (e.g., `v1.0.0`) is pushed to the repository.
