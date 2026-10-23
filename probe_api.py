"""Temporary probe 2: undocumented metrics endpoints, prints status codes and shapes only."""
import os, json, sys, datetime as dt, urllib.request, urllib.error

BASE = "https://personal.connectapi.garmin.com"
KEY = os.environ["GARMIN_API_KEY"]
today = dt.date.today()
d = lambda n: (today - dt.timedelta(days=n)).isoformat()


def call(method, path, headers, query=""):
    req = urllib.request.Request(BASE + path + query, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:150]
    except Exception as e:
        return 0, str(e)[:150]


def shape(o, depth=0):
    if isinstance(o, dict):
        if depth >= 2:
            return "{%d keys}" % len(o)
        return {k: shape(v, depth + 1) for k, v in list(o.items())[:40]}
    if isinstance(o, list):
        return ["len=%d" % len(o), shape(o[0], depth + 1)] if o else ["len=0"]
    return type(o).__name__


code, body = call("POST", "/personalapitoken-service/personal-api/personal-api-key/token", {"Authorization": "ApiKey " + KEY})
if code != 200:
    sys.exit("token failed %s" % code)
H = {"Authorization": "Bearer " + body.strip()}

code, body = call("GET", "/userprofile-service/userprofile/settings", H)
print("settings:", code)
name = None
try:
    j = json.loads(body)
    print(json.dumps(shape(j), indent=1)[:800])
except Exception:
    pass
code, body = call("GET", "/activitylist-service/activities/search/activities", H, "?start=0&limit=1")
try:
    name = json.loads(body)[0].get("ownerDisplayName")
except Exception:
    pass
print("displayName found:", bool(name))

P = [
    f"/metrics-service/metrics/racepredictions/latest/{name}",
    f"/metrics-service/metrics/racepredictions/daily/{name}?fromCalendarDate={d(7)}&toCalendarDate={d(0)}",
    "/metrics-service/metrics/racepredictions/latest",
    f"/metrics-service/metrics/trainingstatus/aggregated/{d(1)}",
    f"/metrics-service/metrics/trainingstatus/daily/{d(1)}",
    f"/metrics-service/metrics/trainingreadiness/{d(1)}",
    f"/metrics-service/metrics/trainingloadbalance/latest/{d(1)}",
    f"/metrics-service/metrics/maxmet/daily/{d(14)}/{d(0)}",
    f"/metrics-service/metrics/maxmet/latest/{d(1)}",
    f"/metrics-service/metrics/endurancescore?startDate={d(14)}&endDate={d(0)}&aggregation=daily",
    f"/mobile-gateway/usersummary/trainingreadiness/{d(1)}",
]
for p in P:
    code, body = call("GET", p, H)
    label = p.replace(name or "@@", "<name>")
    print(f"\n{code} {label}")
    if code == 200:
        try:
            print(json.dumps(shape(json.loads(body)), indent=1)[:1500])
        except Exception:
            print(body[:150])
