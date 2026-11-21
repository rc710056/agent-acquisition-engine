#!/bin/bash
set -e
echo "Setting up Agent Acquisition Engine in Codespace..."
pip install -e .
sudo apt-get update && sudo apt-get install -y aria2 ffmpeg
cd apps/web && npm install && npm run build
echo "Setup complete. Start services with: npm run dev in apps/web and python -m uvicorn apps.api.app.main:app"
