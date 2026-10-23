"""Pulls data from the official Garmin Connect Personal API (GARMIN_API_KEY) into ./raw.

Responses are normalised to the shapes build.py already consumes.
Core data (activities, HRV, sleep) must succeed, the rest only logs a warning.
"""
import os, sys, json, time, datetime as dt, urllib.request, urllib.error

BASE = "https://personal.connectapi.garmin.com"
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
CACHE = os.path.join(RAW, "cache")
os.makedirs(CACHE, exist_ok=True)
today = dt.date.today()
d = lambda n: (today - dt.timedelta(days=n)).isoformat()

_token = None


def _request(method, path, headers, query=""):
    req = urllib.request.Request(BASE + path + query, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode()


def refresh_token():
    global _token
    key = os.environ.get("GARMIN_API_KEY", "").strip()
    if not key:
        raise SystemExit("GARMIN_API_KEY manquante")
    try:
        _token = _request("POST", "/personalapitoken-service/personal-api/personal-api-key/token", {"Authorization": "ApiKey " + key}).strip()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Echange de token refuse (HTTP {e.code}): cle expiree ou invalide ?")


def get(path, query=""):
    """GET with retries; returns parsed JSON (None for an empty body)."""
    global _token
    if _token is None:
        refresh_token()
    reauth = False
    for attempt in range(4):
        try:
            body = _request("GET", path, {"Authorization": "Bearer " + _token, "Accept": "application/json"}, query)
            return json.loads(body) if body.strip() else None
        except urllib.error.HTTPError as e:
            if e.code == 401 and not reauth:
                reauth = True
                refresh_token()
                continue
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                delay = 5 * (attempt + 1) * (3 if e.code == 429 else 1)
                print(f"HTTP {e.code} sur {path}; nouvel essai dans {delay}s", flush=True)
                time.sleep(delay)
                continue
            raise RuntimeError(f"HTTP {e.code} sur {path}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if attempt == 3:
                raise RuntimeError(f"{type(e).__name__} sur {path}")
            time.sleep(3 * (attempt + 1))


def save_raw(name, obj):
    with open(os.path.join(RAW, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(obj, f)
    print("saved", name, flush=True)


def save_cache(key, obj):
    with open(os.path.join(CACHE, key + ".json"), "w", encoding="utf-8") as f:
        json.dump(obj, f)


def windows(total, step):
    """(start_offset, end_offset) day windows going back `total` days, oldest last."""
    off = 0
    while off < total:
        a = min(off + step, total)
        yield a, off
        off = a + 1


def soft(name, fn):
    try:
        fn()
    except Exception as e:
        print(f"WARN {name}: {e} (donnees precedentes conservees)", flush=True)


def activity_row(a):
    return {
        "id": a["activityId"],
        "name": a.get("activityName"),
        "type": (a.get("activityType") or {}).get("typeKey"),
        "start_time": a.get("startTimeLocal"),
        "distance_meters": a.get("distance"),
        "duration_seconds": a.get("duration"),
        "moving_duration_seconds": a.get("movingDuration"),
        "avg_hr_bpm": a.get("averageHR"),
        "max_hr_bpm": a.get("maxHR"),
        "elevation_gain_meters": a.get("elevationGain"),
        "calories": a.get("calories"),
        "steps": a.get("steps"),
        "event_type": (a.get("eventType") or {}).get("typeKey"),
    }


def fetch_activities():
    raw, start = [], 0
    while start <= 700:
        page = get("/activitylist-service/activities/search/activities", f"?start={start}&limit=100") or []
        raw += page
        if len(page) < 100:
            break
        start += 100
    if not raw:
        raise RuntimeError("aucune activite retournee")
    save_raw("activities", {"activities": [activity_row(a) for a in raw if a.get("startTimeLocal")]})
    return raw


def fetch_run_details(raw):
    runs = [a for a in raw if "running" in ((a.get("activityType") or {}).get("typeKey") or "") and (a.get("distance") or 0) >= 800]
    new = [a for a in runs if not os.path.exists(os.path.join(CACHE, f"a_{a['activityId']}.json"))]
    print(f"{len(new)} nouvelle(s) sortie(s) a detailler", flush=True)
    for a in new:
        try:
            s = (get(f"/activity-service/activity/{a['activityId']}") or {}).get("summaryDTO") or {}
        except RuntimeError as e:
            print("WARN detail", a["activityId"], e, flush=True)
            continue
        save_cache(f"a_{a['activityId']}", {
            "avg_cadence": a.get("averageRunningCadenceInStepsPerMinute"),
            "avg_stride_length_cm": a.get("avgStrideLength"),
            "avg_ground_contact_time_ms": a.get("avgGroundContactTime"),
            "avg_vertical_oscillation_cm": a.get("avgVerticalOscillation"),
            "avg_power_watts": a.get("avgPower"),
            "training_effect": a.get("aerobicTrainingEffect") if a.get("aerobicTrainingEffect") is not None else s.get("trainingEffect"),
            "anaerobic_training_effect": a.get("anaerobicTrainingEffect"),
            "training_load": a.get("activityTrainingLoad") if a.get("activityTrainingLoad") is not None else s.get("activityTrainingLoad"),
            "training_effect_label": a.get("trainingEffectLabel") or s.get("trainingEffectLabel"),
            "vigorous_intensity_minutes": s.get("vigorousIntensityMinutes"),
            "moderate_intensity_minutes": s.get("moderateIntensityMinutes"),
            "body_battery_impact": s.get("differenceBodyBattery"),
        })


def fetch_hrv():
    rows = {}
    for a, off in windows(150, 28):
        j = get(f"/hrv-service/hrv/daily/{d(a)}/{d(off)}") or {}
        for h in j.get("hrvSummaries") or []:
            rows[h["calendarDate"]] = {
                "date": h["calendarDate"],
                "last_night_avg_hrv_ms": h.get("lastNightAvg"),
                "weekly_avg_hrv_ms": h.get("weeklyAvg"),
                "last_night_5min_high_hrv_ms": h.get("lastNight5MinHigh"),
                "status": h.get("status"),
                "feedback": h.get("feedbackPhrase"),
            }
    if not rows:
        raise RuntimeError("aucune donnee VFC")
    save_raw("hrv_trend", [json.dumps({"trend": sorted(rows.values(), key=lambda r: r["date"])})])
    return rows


def fetch_sleep(hrv):
    nights = {}
    for a, off in windows(180, 28):
        for n in get("/sleep-service/sleep/dailySleepSummariesByDate", f"?startDate={d(a)}&endDate={d(off)}") or []:
            tot = n.get("sleepTimeSeconds") or 0
            if not tot:
                continue
            date = n["calendarDate"]
            score = ((n.get("sleepScores") or {}).get("overall") or {}).get("value")
            nights[date] = {
                "date": date,
                "sleep_hours": round(tot / 3600, 2),
                "sleep_score": score,
                "deep_sleep_percent": round((n.get("deepSleepSeconds") or 0) / tot * 100, 1),
                "rem_sleep_percent": round((n.get("remSleepSeconds") or 0) / tot * 100, 1),
                "avg_overnight_hrv": float(hrv[date]["last_night_avg_hrv_ms"]) if date in hrv and hrv[date].get("last_night_avg_hrv_ms") is not None else None,
                "avg_sleep_stress": n.get("avgSleepStress"),
            }
    if not nights:
        raise RuntimeError("aucune nuit de sommeil")
    save_cache("r_sleep_api", {"nights": sorted(nights.values(), key=lambda r: r["date"])})


def fetch_rhr():
    for n in range(0, 120):
        p = os.path.join(CACHE, f"rhr_{d(n)}.json")
        if n >= 2 and os.path.exists(p):
            continue
        v = (get("/wellness-service/wellness/dailyHeartRate", f"?date={d(n)}") or {}).get("restingHeartRate")
        if v is not None:
            save_cache(f"rhr_{d(n)}", {"allMetrics": {"metricsMap": {"WELLNESS_RESTING_HEART_RATE": [{"calendarDate": d(n), "value": v}]}}})


def fetch_steps():
    rows = []
    for a, off in windows(90, 27):
        rows += get(f"/usersummary-service/stats/steps/daily/{d(a)}/{d(off)}") or []
    save_cache("r_steps_api", rows)


def fetch_body_battery():
    rows = []
    for a, off in windows(90, 27):
        for r in get("/wellness-service/wellness/bodyBattery/reports/daily", f"?startDate={d(a)}&endDate={d(off)}") or []:
            if r.get("charged") is None:
                continue
            rows.append({
                "date": r["date"],
                "charged": r.get("charged"),
                "drained": r.get("drained"),
                "body_battery_level": (r.get("endOfDayBodyBatteryDynamicFeedbackEvent") or {}).get("bodyBatteryLevel"),
            })
    save_cache("r_body_battery_api", rows)


def fetch_weight():
    j = get(f"/weight-service/weight/range/{d(365)}/{d(0)}") or {}
    out = []
    for w in j.get("dailyWeightSummaries") or []:
        v = (w.get("latestWeight") or {}).get("weight")
        if v:
            out.append({"date": w["summaryDate"], "weight_kg": round(v / 1000 if v > 500 else v, 1)})
    save_cache("g_weigh", {"measurements": out})


def fetch_fitnessage():
    j = get(f"/fitnessage-service/fitnessage/v2/{d(1)}") or {}
    if j.get("fitnessAge") is None:
        raise RuntimeError("pas d'age de forme")
    p = os.path.join(CACHE, "g_fitnessage.json")
    try:
        old = json.load(open(p, encoding="utf-8"))
    except Exception:
        old = {}
    chrono, fit = j.get("chronologicalAge"), j["fitnessAge"]
    save_cache("g_fitnessage", {
        "date": d(1),
        "fitness_age_years": round(fit, 1),
        "chronological_age_years": chrono,
        "age_difference_years": round(chrono - fit, 1) if chrono is not None else None,
        "achievable_fitness_age_years": old.get("achievable_fitness_age_years") if isinstance(old, dict) else None,
        "previous_fitness_age_years": round(j["previousFitnessAge"], 1) if j.get("previousFitnessAge") is not None else None,
        "last_updated": j.get("lastUpdated"),
    })


if __name__ == "__main__":
    acts = fetch_activities()
    fetch_run_details(acts)
    hrv = fetch_hrv()
    fetch_sleep(hrv)
    soft("rhr", fetch_rhr)
    soft("steps", fetch_steps)
    soft("body_battery", fetch_body_battery)
    soft("weight", fetch_weight)
    soft("fitnessage", fetch_fitnessage)
    print("API OK", flush=True)
