"""Phase 8 fake TypeSafe SystemOne endpoint (loopback only). Test fixture (task 016b).

  fake_systemone.py <port_file> <mode_file> <hits_file> <key_sha256> <fixtures_dir>

REAL bodies (fixtures/, the response.body_json of work/016-probe/probe<n>.record.json, verbatim):
  probe3   200 {"model":"jev-1.14.0","answers":{"q1":{"type":"noul","noul":0.92}},"usage":{284,21}}
  probe1   422 questions sent as a list (FastAPI dict_type detail)
  probe2   400 api_usage_error "Invalid request."
DOCUMENTED-SYNTHETIC (built from the TypeSafe docs' answer shapes; never seen live):
  auto     answers every question in the request: noul 0.92 (as probe 3);
           choice = first option, probabilities {opt1: 0.7, opt2: 0.3}, confidence 0.8;
           score = highest level, probabilities 0.6 highest / 0.4 next, legend = the
           levels, confidence 0.8; usage 284/21 (as probe 3)
Variants of auto, ONE named change each (SYNTHETIC, they test the adapter's rules):
  nousage badusage nousage_bad(no usage AND a wrong answer type) wrongtype notoffered
  scorerange legendbad badprobkey missing extra vendorerr garbage error500 redirect hang
LIVE-SEMANTICS score fixtures (task 016c; the semantics task 019 proved live: a 5-level
Score came back as the NUMBER 3.95, logs/019-jev-smoke@20261101T150034-0600.meta.json;
19's 35 output tokens vs probe 3's 21 suggest a bare answer, so these carry ONLY
type + score, no legend/probabilities/confidence; noul stays 0.92 as in probe 3):
  score019 (3.95)  score_zero (0.0)  score_top (float n-1)
  refused: score_over (n-1 + 0.01)  score_neg (-0.1)  score_str ("3.95")  score_missing
  keyecho  a non-JSON body that echoes the bearer it received (tests the raw-file key scrub)
REAL smoke-019b reply (task 016d; fixtures/live019b_reply.json, byte-for-byte the preserved
work/jev-raw/019b-jev-verify@20261101T150856-0600.reply.json; answers the 019b prompt,
fixtures/live019b_prompt.md: q1 noul, q2 5-level score, q3 3-option choice):
  live019b  served verbatim (legend is an OBJECT {"0": label, ...})
Variants of live019b, ONE named change each to q2's legend (SYNTHETIC):
  accepted: lg_array (the same labels as an array, the documented shape)
  refused:  lg_missing (no "2")  lg_extra (adds "5")  lg_gap ("4" renamed "5")
            lg_wronglabel ("3" = "Very high")  lg_nonstring ("1" = 1)
            lg_padded ("1" renamed "01")  lg_array_wronglabel  lg_array_short
Per request ONE line goes to hits_file: path, method, content-type, auth_match
(sha256 of the bearer compared; never the key), the body's key names, model,
state, and questions exactly as received.
"""
import copy, hashlib, http.server, json, os, sys, time

port_file, mode_file, hits_file, key_sha, fxdir = sys.argv[1:6]
FX = {n: json.load(open(os.path.join(fxdir, f + ".json")))
      for n, f in (("probe1", "probe1_422"), ("probe2", "probe2_400"), ("probe3", "probe3_ok"))}
USAGE = FX["probe3"]["body"]["usage"]
LIVE019B = open(os.path.join(fxdir, "live019b_reply.json"), "rb").read()

def live019b(mode):
    if mode == "live019b": return LIVE019B
    b = json.loads(LIVE019B); lg = b["answers"]["q2"]["legend"]
    labels = [lg[str(i)] for i in range(len(lg))]
    if mode == "lg_array": b["answers"]["q2"]["legend"] = labels
    elif mode == "lg_missing": del lg["2"]
    elif mode == "lg_extra": lg["5"] = "Beyond complete"
    elif mode == "lg_gap": lg["5"] = lg.pop("4")
    elif mode == "lg_wronglabel": lg["3"] = "Very high"
    elif mode == "lg_nonstring": lg["1"] = 1
    elif mode == "lg_padded": lg["01"] = lg.pop("1")
    elif mode == "lg_array_wronglabel": b["answers"]["q2"]["legend"] = labels[:3] + ["Very high"] + labels[4:]
    elif mode == "lg_array_short": b["answers"]["q2"]["legend"] = labels[:4]
    else: raise ValueError(mode)
    return json.dumps(b).encode()

def auto(req):
    ans = {}
    for qid, q in (req.get("questions") or {}).items():
        t = q.get("type")
        if t == "noul":
            ans[qid] = {"type": "noul", "noul": 0.92}
        elif t == "choice":
            ks = list(q["criteria"])
            ans[qid] = {"type": "choice", "choice": ks[0], "probabilities": {ks[0]: 0.7, ks[1]: 0.3}, "confidence": 0.8}
        elif t == "score":
            lv = list(q["criteria"]); n = len(lv)
            ans[qid] = {"type": "score", "score": n - 1, "legend": lv,
                        "probabilities": {lv[n - 1]: 0.6, lv[n - 2]: 0.4}, "confidence": 0.8}
    return {"model": "jev-1.14.0", "answers": ans, "usage": dict(USAGE)}

def variant(mode, req):
    b = auto(req); a = b["answers"]; first = next(iter(a), None)
    kind = lambda t: next((k for k, v in a.items() if v["type"] == t), None)
    if mode == "nousage": del b["usage"]
    elif mode == "badusage": b["usage"]["input_tokens"] = "284"
    elif mode == "nousage_bad": del b["usage"]; a[first]["type"] = "bogus"
    elif mode == "wrongtype": a[first]["type"] = "score" if a[first]["type"] != "score" else "noul"
    elif mode == "notoffered": a[kind("choice")]["choice"] = "SYNTH-not-an-option"
    elif mode == "scorerange": a[kind("score")]["score"] = len(a[kind("score")]["legend"])
    elif mode == "legendbad": a[kind("score")]["legend"] = ["only-one"]
    elif mode == "badprobkey": a[kind("score")]["probabilities"]["SYNTH-level"] = 0.1
    elif mode == "missing": del a[first]
    elif mode == "extra": a["q99"] = {"type": "noul", "noul": 0.5}
    elif mode.startswith("score") and mode != "scorerange":
        k = kind("score"); n = len(a[k]["legend"])
        v = {"score019": 3.95, "score_zero": 0.0, "score_top": float(n - 1), "score_over": n - 1 + 0.01,
             "score_neg": -0.1, "score_str": "3.95"}
        a[k] = {"type": "score"}
        if mode != "score_missing": a[k]["score"] = v[mode]
    elif mode == "vendorerr": b["error"] = {"code": "synthetic", "message": "synthetic vendor error"}
    return b

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        auth = self.headers.get("Authorization") or ""
        tok = auth[7:] if auth.startswith("Bearer ") else ""
        try: req = json.loads(body)
        except Exception: req = {}
        mode = open(mode_file).read().strip()
        with open(hits_file, "a") as f:
            f.write(json.dumps({"path": self.path, "method": "POST",
                                "auth_match": hashlib.sha256(tok.encode()).hexdigest() == key_sha,
                                "content_type": self.headers.get("Content-Type"),
                                "keys": sorted(req), "model": req.get("model"), "state": req.get("state"),
                                "questions": req.get("questions"), "mode": mode}) + "\n")
        if mode == "hang": time.sleep(30); return
        if mode == "redirect":
            self.send_response(307); self.send_header("Location", "http://127.0.0.1:1/x")
            self.send_header("Content-Length", "0"); self.end_headers(); return
        code = 200
        if mode == "error500": code, b = 500, b'{"error":"boom"}'
        elif mode in ("probe1", "probe2"): code, b = FX[mode]["status"], json.dumps(FX[mode]["body"]).encode()
        elif mode == "probe3": b = json.dumps(FX["probe3"]["body"]).encode()
        elif mode == "garbage": b = b"not json"
        elif mode == "keyecho": b = b"<html>echo " + tok.encode() + b" end</html>"
        elif mode == "auto": b = json.dumps(auto(req)).encode()
        elif mode == "live019b" or mode.startswith("lg_"): b = live019b(mode)
        else: b = json.dumps(variant(mode, req)).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
open(port_file + ".tmp", "w").write(str(s.server_address[1]))
os.replace(port_file + ".tmp", port_file)
s.serve_forever()
