"""
Standalone entry point: runs backend and opens browser directly, without depending on external module resolution
"""
import sys
import os

# Add current directory to sys.path so 'src' is importable
base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import uvicorn
from src.api.server import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 41730))
    uvicorn.run(app, host="0.0.0.0", port=port)
