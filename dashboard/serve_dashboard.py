"""
serve_dashboard.py — Servidor HTTP minimo para el dashboard SIAVA.

Sirve los archivos estaticos del repo (dashboard.html + JSONs de evaluation/results/)
en http://localhost:8000/dashboard.html

Uso:
    python serve_dashboard.py          # puerto 8000 por defecto
    python serve_dashboard.py --port 9000
"""
from __future__ import annotations
import argparse
import http.server
import os
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # raiz del repo

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)
    def log_message(self, fmt, *args):
        pass  # silenciar logs de cada request

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()

    server = http.server.HTTPServer(('localhost', args.port), Handler)
    url = f'http://localhost:{args.port}/dashboard/dashboard.html'
    print(f'[dashboard] Servidor en {url}')
    print(f'[dashboard] Abre el link en tu browser. Ctrl+C para detener.')

    # Abrir browser automaticamente
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('[dashboard] Detenido.')

if __name__ == '__main__':
    main()
