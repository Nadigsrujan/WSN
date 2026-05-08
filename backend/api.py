"""
backend/api.py
--------------
FastAPI server bridging the WSN backend to the Vite React frontend.
Reads `data/network_state.json` and serves it via `/api/state`.
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.utils import read_network_state

app = FastAPI(title="WSN Hybrid Backend API")

# Allow requests from the Vite dev server (usually localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/state")
def get_state():
    """Returns the latest network state snapshot."""
    state = read_network_state()
    if not state:
        raise HTTPException(status_code=503, detail="Network state not available yet.")
    return state

@app.get("/api/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}
