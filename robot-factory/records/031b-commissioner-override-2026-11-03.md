# Commissioner's override: code shelf wiring (2026-11-03)

Gate record: task 030b, analysis.json in work/030b-code-shelf-gate/.
Verdict: DO NOT WIRE (G1 fail: wired 100.0 vs bare 100.0, +10 margin
unreachable on a saturated set; G2 pass: agreed accuracy 100.0, 39
agreed; G3 fail: control table 80.0 delta -3.8, prose 100.0 delta
+22.0, tolerance +/-3). The verdict stands unedited.

Ruling (Dan, commissioner, 2026-11-03 ~02:04 CT, in chat with the
moderator): wire the shelf anyway, unverified, with safeguards.
Basis: the gate showed no evidence of harm; it declined to certify
a gain. Safeguards as commissioned in task 031b: feature flag
(default off), fallback to unwired behaviour on any shelf failure,
service-log marking code_shelf=unverified, provenance on every
shelf-informed answer, no public claim that the shelf improves
answers, staged build only with deployment a separate approval.

Task: queue/031b-code-wiring-override.md. A harder gate remains
the only road to certification.
