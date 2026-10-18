from http.server import BaseHTTPRequestHandler, HTTPServer
import json


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = {"status": "ok"}
            self.send_response(200)
        elif self.path == "/metrics/summary":
            body = {"active_users": 120, "revenue": 5400}
            self.send_response(200)
        elif self.path == "/version":
            body = {"version": "1.0.0"}
            self.send_response(200)
        else:
            body = {"error": "not_found"}
            self.send_response(404)

        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()