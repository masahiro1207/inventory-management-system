#!/usr/bin/env python3
"""
Railway/本番用: PORT を確実に読み取り Gunicorn を起動する。
シェルでの $PORT 展開に依存しない。exec で PID 1 を gunicorn に渡す。
"""
import os
import sys


def main() -> None:
    port = os.environ.get("PORT", "5000")
    try:
        port_int = int(port)
    except ValueError:
        port_int = 5000
    bind = f"0.0.0.0:{port_int}"
    print(f"Starting gunicorn on {bind} (PORT={port})", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    args = [
        sys.executable,
        "-m",
        "gunicorn",
        "--bind",
        bind,
        "--workers",
        "1",
        "--timeout",
        "120",
        "--access-logfile",
        "-",
        "--error-logfile",
        "-",
        "--log-level",
        "info",
        "run:app",
    ]
    os.execvp(sys.executable, args)


if __name__ == "__main__":
    main()
