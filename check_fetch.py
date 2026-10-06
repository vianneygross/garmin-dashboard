"""Stops the refresh when Garmin rate-limits or rejects the session, so partial data is never published."""
import glob, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCK = re.compile(r"\b(429|401|403)\b|too many requests|rate.?limit|unauthorized|forbidden", re.I)

bad = []
for p in glob.glob(os.path.join(HERE, "raw", "*.json")):
    head = open(p, encoding="utf-8").read(400)
    if '"error"' in head and BLOCK.search(head):
        bad.append(p)
        os.remove(p)
for p in glob.glob(os.path.join(HERE, "raw", "cache", "*.json")):
    head = open(p, encoding="utf-8").read(300)
    if head.startswith("ERR") and BLOCK.search(head):
        bad.append(p)
        os.remove(p)

if bad:
    print(f"Garmin a refuse {len(bad)} requete(s) (429/401/403). Arret sans publier.")
    sys.exit(1)
print("Fetch OK")
