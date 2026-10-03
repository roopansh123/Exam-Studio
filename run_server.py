import uvicorn
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import init_db
from app.main import app

if __name__ == "__main__":
    init_db()
    print("=" * 60)
    print("  Lord Krishna Convent School - LKCS Exam Studio")
    print("  Local Desktop / Browser : http://127.0.0.1:8000")
    print("  Network / Teacher Portal: http://0.0.0.0:8000/portal")
    print("=" * 60)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
