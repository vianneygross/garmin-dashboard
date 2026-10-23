"""Temporary probe: prints only the shape of Garmin Personal API responses."""
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
        return e.code, e.read().decode()[:200]
    except Exception as e:
        return 0, str(e)[:200]


def shape(o, depth=0):
    if isinstance(o, dict):
        if depth >= 2:
            return "{%d keys}" % len(o)
        return {k: shape(v, depth + 1) for k, v in list(o.items())[:60]}
    if isinstance(o, list):
        return ["len=%d" % len(o), shape(o[0], depth + 1)] if o else ["len=0"]
    return type(o).__name__


code, body = call("POST", "/personalapitoken-service/personal-api/personal-api-key/token", {"Authorization": "ApiKey " + KEY})
print("token:", code)
if code != 200:
    print(body[:200])
    sys.exit(1)
tok = json.loads(body)
print("token response keys:", list(tok.keys()) if isinstance(tok, dict) else type(tok).__name__)
access = tok.get("access_token") or tok.get("accessToken") or tok.get("token")
if not access:
    sys.exit("no access token field found")
H = {"Authorization": "Bearer " + access}

TESTS = [
    ("activities", "/activitylist-service/activities/search/activities", "?start=0&limit=3&activityType=running"),
    ("hrv_daily", f"/hrv-service/hrv/daily/{d(7)}/{d(1)}", ""),
    ("hrv_day", f"/hrv-service/hrv/{d(1)}", ""),
    ("sleep_daily", "/sleep-service/sleep/dailySleepSummariesByDate", f"?startDate={d(7)}&endDate={d(1)}"),
    ("dailyHeartRate", "/wellness-service/wellness/dailyHeartRate", f"?date={d(1)}"),
    ("fitnessage", f"/fitnessage-service/fitnessage/v2/{d(1)}", ""),
    ("dailysummaries", "/usersummary-service/v2/dailysummaries", f"?startDate={d(3)}&endDate={d(1)}"),
    ("activity_range", f"/wellnessactivity-service/activity/summary/range/{d(7)}/{d(0)}", ""),
]
first_id = None
for name, path, q in TESTS:
    code, body = call("GET", path, H, q)
    print(f"\n== {name}: HTTP {code}")
    try:
        j = json.loads(body)
        if name == "activities" and isinstance(j, (list, dict)):
            lst = j if isinstance(j, list) else next((v for v in j.values() if isinstance(v, list)), [])
            if lst:
                first_id = lst[0].get("activityId")
        print(json.dumps(shape(j), indent=1)[:2500])
    except Exception:
        print(body[:200])
if first_id:
    code, body = call("GET", f"/activity-service/activity/{first_id}", H)
    print(f"\n== activity detail: HTTP {code}")
    try:
        print(json.dumps(shape(json.loads(body)), indent=1)[:3500])
    except Exception:
        print(body[:200])
