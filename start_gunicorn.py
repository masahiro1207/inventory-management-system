#!/usr/bin/env python3
"""
Railway/本番用: PORT を確実に読み取り Gunicorn を起動する。
シェルでの $PORT 展開に依存しない。
"""
import os
import sys
import subprocess

def main():
    port = os.environ.get("PORT", "5000")
    try:
        port_int = int(port)
    except ValueError:
        port_int = 5000
    bind = f"0.0.0.0:{port_int}"
    print(f"Starting gunicorn on {bind} (PORT={port})", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    subprocess.run([
        "gunicorn",
        "--bind", bind,
        "--workers", "1",
        "--timeout", "120",
        "run:app",
    ], check=True)

if __name__ == "__main__":
    main()
