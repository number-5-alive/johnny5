"""Phase 6 fake OpenAI-compatible endpoint (loopback only). Test fixture.

  fake_api.py <port_file> <mode_file> <hits_file> <key_sha256>

Writes the bound port to port_file. Per request it appends ONE line to
hits_file: path, whether sha256(bearer) matched, the model asked for, and
max_tokens. It never stores the key or the Authorization header itself.
Modes (read from mode_file per request): ok, nousage, length, error500,
redirect, hang, reasoning, garbage.
"""
import hashlib, http.server, json, sys, time

port_file, mode_file, hits_file, key_sha = sys.argv[1:5]

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        auth = self.headers.get("Authorization") or ""
        tok = auth[7:] if auth.startswith("Bearer ") else ""
        match = hashlib.sha256(tok.encode()).hexdigest() == key_sha
        try: req = json.loads(body)
        except Exception: req = {}
        mode = open(mode_file).read().strip()
        with open(hits_file, "a") as f:
            f.write(json.dumps({"path": self.path, "auth_match": match, "model": req.get("model"),
                                "max_tokens": req.get("max_tokens"), "mode": mode}) + "\n")
        if mode == "hang":
            time.sleep(30); return
        if mode == "redirect":
            self.send_response(307); self.send_header("Location", "http://127.0.0.1:1/x")
            self.send_header("Content-Length", "0"); self.end_headers(); return
        if mode == "error500":
            b = b'{"error":"boom"}'
            self.send_response(500); self.send_header("Content-Length", str(len(b))); self.end_headers()
            self.wfile.write(b); return
        if mode == "garbage":
            b = b"not json"
        else:
            r = {"model": "fake-" + str(req.get("model")),
                 "choices": [{"message": {"role": "assistant", "content": "fake reply text"},
                              "finish_reason": "length" if mode == "length" else "stop"}]}
            if mode != "nousage":
                r["usage"] = {"prompt_tokens": 1234, "completion_tokens": 567, "total_tokens": 1801}
            if mode == "reasoning":
                r["usage"]["total_tokens"] = 2801      # 1000 reasoning tokens outside completion
            b = json.dumps(r).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
open(port_file + ".tmp", "w").write(str(s.server_address[1]))
import os; os.replace(port_file + ".tmp", port_file)
s.serve_forever()
