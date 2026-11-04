"""Phase 9 fake responses-shape endpoint (loopback only). Test fixture.

  fake_responses.py <port_file> <mode_file> <hits_file> <key_sha256> <fixtures_dir>

Bodies come from the REAL task-021 probe replies (fixtures/probe*.json, the
body_json of work/021-probe/probe<n>.record.json, verbatim):
  probe2   200, "Blue", usage 38/5           (real, verbatim)
  probe3   200, link inside the model text   (real, verbatim)
  probe1   400, model "sonar" not supported  (real, verbatim)
Variants are the real probe3 body with ONE named change each. Every variant is
SYNTHETIC: the probes never returned it; it tests the adapter's refusal or
counting rule, not a claim about the vendor:
  cited      + annotations on the output_text, top-level citations and
               search_results, and a non-message output item (structured
               citations were NOT seen live; this checks they never reach --out)
  incomplete status "incomplete", incomplete_details.reason max_output_tokens
  failed     status "failed"
  vendorerr  error object set
  nousage    usage removed
  badusage   usage.input_tokens a string
  extratotal usage.total_tokens 1000 above input+output
  nomessage  output []
  garbage    non-JSON body
  error500 / redirect / hang  transport failures
Per request it appends ONE line to hits_file: path, method, content-type,
whether sha256(bearer) matched, the request's key names, model,
max_output_tokens and sha256 of input. Never the key or the header itself.
"""
import copy, hashlib, http.server, json, os, sys, time

port_file, mode_file, hits_file, key_sha, fxdir = sys.argv[1:6]
FX = {n: json.load(open(os.path.join(fxdir, "%s.json" % f)))
      for n, f in (("probe1", "probe1_400"), ("probe2", "probe2_ok"), ("probe3", "probe3_ok"))}

def variant(mode):
    b = copy.deepcopy(FX["probe3"]["body"])
    if mode == "cited":
        part = b["output"][0]["content"][0]
        part["annotations"] = [
            {"type": "url_citation", "url": "https://synthetic.example/a", "title": "SYNTH-A", "start_index": 0, "end_index": 6},
            {"type": "url_citation", "url": "https://synthetic.example/b", "title": "SYNTH-B", "start_index": 7, "end_index": 9}]
        b["citations"] = ["https://synthetic.example/a", "https://synthetic.example/b", "https://synthetic.example/c"]
        b["search_results"] = [{"title": "SYNTH-SR", "url": "https://synthetic.example/sr", "snippet": "SYNTH-SNIPPET"}]
        b["output"].insert(0, {"type": "search_results", "id": "synth", "results": [{"url": "https://synthetic.example/sr"}]})
    elif mode == "incomplete":
        b["status"] = "incomplete"; b["incomplete_details"] = {"reason": "max_output_tokens"}
    elif mode == "failed":
        b["status"] = "failed"
    elif mode == "vendorerr":
        b["error"] = {"code": "synthetic", "message": "synthetic vendor error"}
    elif mode == "nousage":
        del b["usage"]
    elif mode == "badusage":
        b["usage"]["input_tokens"] = "42"
    elif mode == "extratotal":
        b["usage"]["total_tokens"] = b["usage"]["input_tokens"] + b["usage"]["output_tokens"] + 1000
    elif mode == "nomessage":
        b["output"] = []
    return b

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
        inp = req.get("input")
        with open(hits_file, "a") as f:
            f.write(json.dumps({"path": self.path, "method": "POST", "auth_match": match,
                                "content_type": self.headers.get("Content-Type"),
                                "keys": sorted(req), "model": req.get("model"),
                                "max_output_tokens": req.get("max_output_tokens"),
                                "input_type": type(inp).__name__,
                                "input_sha256": hashlib.sha256(inp.encode()).hexdigest() if isinstance(inp, str) else None,
                                "mode": mode}) + "\n")
        if mode == "hang":
            time.sleep(30); return
        if mode == "redirect":
            self.send_response(307); self.send_header("Location", "http://127.0.0.1:1/x")
            self.send_header("Content-Length", "0"); self.end_headers(); return
        code = 200
        if mode == "error500":
            code, b = 500, b'{"error":"boom"}'
        elif mode == "probe1":
            code, b = FX["probe1"]["status"], json.dumps(FX["probe1"]["body"]).encode()
        elif mode == "garbage":
            b = b"not json"
        elif mode in ("probe2", "probe3"):
            b = json.dumps(FX[mode]["body"]).encode()
        else:
            b = json.dumps(variant(mode)).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
open(port_file + ".tmp", "w").write(str(s.server_address[1]))
os.replace(port_file + ".tmp", port_file)
s.serve_forever()
