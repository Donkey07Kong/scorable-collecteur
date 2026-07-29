"""
app.py - Point entree Render.com
Lance le collecteur CAF en arriere-plan + page statut.
"""
import sys
import json
import threading
import time
import os

try:
    from http.server import HTTPServer, BaseHTTPRequestHandler
except ImportError:
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler

import collecteur_live


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")

        fsize = 0
        if os.path.exists("live_data.csv"):
            fsize = os.path.getsize("live_data.csv")

        nrows = 0
        try:
            import csv as csv_mod
            with open("live_data.csv", "r") as f:
                nrows = sum(1 for _ in csv_mod.DictReader(f))
        except Exception:
            pass

        nrank = 0
        try:
            with open("rankings_per_round.json", "r") as f:
                nrank = len(json.load(f))
        except Exception:
            pass

        body = (
            "<html><body style='font-family:sans-serif;padding:2em'>"
            "<h1>SCORABLE Collecteur Live</h1>"
            "<p>Statut: <strong style='color:green'>ACTIF</strong></p>"
            "<table>"
            "<tr><td>Cycle</td><td><strong>%s</strong></td></tr>"
            "<tr><td>Dernier round</td><td><strong>%s</strong></td></tr>"
            "<tr><td>Matchs collectes</td><td><strong>%s</strong></td></tr>"
            "<tr><td>Classements</td><td><strong>%s rounds</strong></td></tr>"
            "<tr><td>Taille CSV</td><td><strong>%.1f KB</strong></td></tr>"
            "</table>"
            "<hr><p><small>Poll 30s. Scores + cotes + classements. %s</small></p>"
            "</body></html>"
        ) % (
            collecteur_live._cycle,
            collecteur_live._last_round or "en attente R1...",
            nrows,
            nrank,
            fsize / 1024,
            ts,
        )

        self.send_response(200)
        enc = body.encode("utf-8")
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(enc)))
        self.end_headers()
        self.wfile.write(enc)

    def log_message(self, fmt, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    t = threading.Thread(target=collecteur_live.main, daemon=True)
    t.start()
    time.sleep(2)
    server = HTTPServer(("0.0.0.0", port), Handler)
    print("[Web] Status: http://0.0.0.0:%d" % port)
    server.serve_forever()


if __name__ == "__main__":
    main()
