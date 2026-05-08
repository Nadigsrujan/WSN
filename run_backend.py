"""
run_backend.py
--------------
Quick launcher for the WSN backend orchestrator.
Run this FIRST before starting the dashboard.

Usage:
    python run_backend.py
"""
import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.main import main

if __name__ == "__main__":
    main()
