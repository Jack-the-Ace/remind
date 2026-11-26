"""Launched by services.ps1 using the base interpreter with -I -S (no global packages)."""
import os
import site
import sys
from pathlib import Path

backend = Path(__file__).resolve().parent
site.addsitedir(str(backend.parent / ".venv" / "Lib" / "site-packages"))
sys.path.insert(0, str(backend))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(sys.argv[1]), access_log=False)
