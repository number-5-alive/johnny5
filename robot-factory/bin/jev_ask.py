#!/usr/bin/env python3
"""Render a Jev question template into an ordinary queue task (task 016b, 2026-11-01).

  jev_ask.py --template <name> --slot key=value [--slot key=@file ...] --out <path>
             [--title <text>] [--templates <dir>]

Templates are data files in templates/jev/<name>.md (see templates/jev/README.md).
Refused (exit 2, nothing written): unknown template, missing required slot,
unknown slot, repeated slot, empty slot value, a question-line slot that is
multi-line or contains "|", a slot value containing a JEV marker line, an
existing --out. Stdlib only. Makes no call; the runner routes the task to
seats/jev.sh because the task says SEAT: jev.
"""
import argparse, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.join(os.path.dirname(HERE), "templates", "jev")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
MARKERS = ("JEV-STATE:", "JEV-QUESTIONS:")

def fail(msg):
    print("jev_ask: %s" % msg, file=sys.stderr)
    sys.exit(2)

def load_template(tdir, name):
    if not NAME_RE.match(name or ""):
        fail("bad template name %r" % name)
    path = os.path.join(tdir, name + ".md")
    if not os.path.isfile(path):
        have = sorted(f[:-3] for f in os.listdir(tdir) if f.endswith(".md") and f != "README.md") \
            if os.path.isdir(tdir) else []
        fail("unknown template %r (have: %s)" % (name, ", ".join(have) or "none"))
    text = open(path, encoding="utf-8").read()
    def field(k):
        mm = re.search(r"^%s:[ \t]*(.*)$" % k, text, re.M)
        if mm is None: fail("template %s has no %s: line" % (name, k))
        return [s.strip() for s in mm.group(1).split(",") if s.strip()]
    req, opt = field("SLOTS"), field("OPTIONAL")
    blk = re.search(r"^```jev\n(.*?)^```", text, re.M | re.S)
    if blk is None: fail("template %s has no ```jev block" % name)
    return req, opt, blk.group(1)

def render(block, values, optional):
    lines = []
    for line in block.splitlines():
        mm = re.match(r"^\[if ([a-z0-9_]+)\](.*)$", line)
        if mm:
            if mm.group(1) not in optional: fail("template uses [if %s] on a non-optional slot" % mm.group(1))
            if mm.group(1) not in values: continue
            line = mm.group(2)
        lines.append(line)
    out, in_q = [], False
    for line in lines:
        if line.strip() == "JEV-QUESTIONS:": in_q = True
        used = re.findall(r"\{([a-z0-9_]+)\}", line)
        for k in used:
            if k not in values: fail("template references slot {%s} that was not given" % k)
            v = values[k]
            if in_q and ("\n" in v or "|" in v):
                fail("slot %r is used in a question line: it must be one line with no '|'" % k)
        out.append(re.sub(r"\{([a-z0-9_]+)\}", lambda mm: values[mm.group(1)], line))
    return "\n".join(out).rstrip("\n") + "\n"

def main(argv=None):
    ap = argparse.ArgumentParser(prog="jev_ask.py")
    ap.add_argument("--template", required=True)
    ap.add_argument("--slot", action="append", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--title")
    ap.add_argument("--templates", default=DEFAULT_DIR)
    a = ap.parse_args(argv)
    req, opt, block = load_template(a.templates, a.template)
    values = {}
    for s in a.slot:
        k, sep, v = s.partition("=")
        if not sep or not k: fail("--slot must be key=value (got %r)" % s[:40])
        if k not in req and k not in opt:
            fail("unknown slot %r for template %s (slots: %s)" % (k, a.template, ", ".join(req + opt)))
        if k in values: fail("slot %r given twice" % k)
        if v.startswith("@"):
            try: v = open(v[1:], encoding="utf-8").read()
            except Exception as e: fail("slot %r: cannot read %s (%s)" % (k, v[1:], type(e).__name__))
        v = v.strip()
        if not v: fail("slot %r is empty" % k)
        if any(l.strip() in MARKERS for l in v.splitlines()):
            fail("slot %r contains a JEV-STATE:/JEV-QUESTIONS: line" % k)
        values[k] = v
    missing = [k for k in req if k not in values]
    if missing: fail("missing slot(s) for template %s: %s" % (a.template, ", ".join(missing)))
    body = render(block, values, opt)
    title = a.title or "Jev %s audit" % a.template
    if "\n" in title: fail("--title must be one line")
    task = "# %s\n\nSEAT: jev\n\n<!-- rendered by bin/jev_ask.py from templates/jev/%s.md -->\n\n%s" % (
        title, a.template, body)
    try:
        with open(a.out, "x", encoding="utf-8") as f: f.write(task)
    except FileExistsError:
        fail("--out %s already exists; not overwritten" % a.out)
    print("jev_ask: wrote %s (template %s, %d slot(s))" % (a.out, a.template, len(values)))

if __name__ == "__main__":
    main()
