"""Launch the local app from a repository checkout; creates no global service."""
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:41732'


def ready():
    try:
        with urllib.request.urlopen(URL + '/api/status', timeout=1) as response:
            return 'capture_source' in json.load(response)
    except (OSError, ValueError):
        return False


def main():
    if not ready():
        (ROOT / 'data').mkdir(exist_ok=True)
        with (ROOT / 'data/server.log').open('a', encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'src.api.server:app',
                '--host', '127.0.0.1', '--port', '41732', '--loop', 'asyncio'], cwd=ROOT,
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        for _ in range(120):
            if ready():
                break
            if process.poll() is not None:
                raise RuntimeError('Server failed to start. See data/server.log.')
            time.sleep(.25)
        else:
            raise RuntimeError('Server startup timed out. See data/server.log.')
    webbrowser.open(URL)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('BLE Tracker Search', str(exc))
        root.destroy()
