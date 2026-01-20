"""Entry point for running the backend server."""

import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).parent / ".env")

if __name__ == "__main__":
    debug = os.getenv("DEBUG", "false").lower() == "true"

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=debug,
    )
