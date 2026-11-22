"""
Web server for the CSP map colouring site.

Uses only the Python standard library, so there is nothing to install.

    python app.py            -> open http://localhost:8000

API
    GET  /api/maps                list of maps
    GET  /api/maps/<id>           regions, SVG paths and neighbours of one map
    POST /api/solve               {"map", "colours", "method"} -> result + step trace
    POST /api/compare             {"map", "colours"} -> all methods side by side
"""

import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from csp.map_colouring import compare, list_maps, load_map, solve_map
from csp.solver import METHODS

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")

# Windows can report odd types for these, so set them explicitly
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")


class Handler(BaseHTTPRequestHandler):
    server_version = "CSPMap/1.0"

    # ------------------------------------------------------------ responses
    def send_json(self, data, status=200):
        body = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_file(self, path):
        with open(path, "rb") as f:
            body = f.read()
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 10000:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(length) or b"{}")

    # ------------------------------------------------------------ routes
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/maps":
            return self.send_json(list_maps())
        if path.startswith("/api/maps/"):
            try:
                return self.send_json(load_map(path.rsplit("/", 1)[1]))
            except KeyError:
                return self.send_json({"error": "unknown map"}, 404)

        # static files from web/
        rel = "index.html" if path == "/" else path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB, rel))
        if full.startswith(WEB + os.sep) and os.path.isfile(full):
            return self.send_file(full)
        self.send_json({"error": "not found"}, 404)

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        try:
            body = self.read_json()
            map_id = body.get("map")
            colours = [str(c)[:20] for c in body.get("colours", [])]
            load_map(map_id)  # raises KeyError for an unknown map
            if not 1 <= len(colours) <= 8 or len(set(colours)) != len(colours):
                raise ValueError("pick between 1 and 8 different colours")

            if self.path == "/api/solve":
                method = body.get("method")
                if method not in METHODS:
                    raise ValueError("unknown method")
                return self.send_json(solve_map(map_id, colours, method))
            if self.path == "/api/compare":
                return self.send_json(compare(map_id, colours))
            self.send_json({"error": "not found"}, 404)
        except KeyError:
            self.send_json({"error": "unknown map"}, 400)
        except (ValueError, TypeError, AttributeError) as e:
            self.send_json({"error": str(e)}, 400)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s  %s\n" % (self.log_date_time_string(), fmt % args))


def main():
    port = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"CSP map colouring running on http://localhost:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
