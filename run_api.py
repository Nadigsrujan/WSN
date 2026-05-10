"""
run_api.py
----------
Launcher for the FastAPI server bridging the backend to the Vite dashboard.

Usage:
    python run_api.py
"""

import sys
import os
import uvicorn

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("Starting WSN API Server on http://localhost:8001 ...")
    uvicorn.run(
        "backend.api:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        reload_dirs=[os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")],
    )