"""Normalises ./raw/* and ./raw/cache/* into data.js (window.DATA) consumed by index.html."""
import json, os, glob, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
CACHE = os.path.join(RAW, "cache")


def load(name):
    p = os.path.join(RAW, name + ".json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def parse(txt):
    try:
        return json.loads(txt) if isinstance(txt, str) else txt
    except Exception:
        return None


def cache(key):
    p = os.path.join(CACHE, key + ".json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return parse(f.read())


def cache_glob(prefix):
    for p in sorted(glob.glob(os.path.join(CACHE, prefix + "*.json"))):
        with open(p, encoding="utf-8") as f:
            yield parse(f.read())


def merged(name, key):
    out, seen = [], set()
    for chunk in load(name) or []:
        j = parse(chunk)
        for row in (j or {}).get(key, []) or []:
            if row.get("date") not in seen:
                seen.add(row["date"])
                out.append(row)
    return sorted(out, key=lambda r: r["date"])


def rnd(v, n=1):
    return round(v, n) if isinstance(v, (int, float)) else None


acts = (load("activities") or {}).get("activities", [])
runs = []
for a in acts:
    if "running" not in (a.get("type") or ""):
        continue
    dist, mov = a.get("distance_meters") or 0, a.get("moving_duration_seconds") or a.get("duration_seconds") or 0
    if dist < 500:
        continue
    r = {
        "id": a["id"],
        "date": a["start_time"][:10],
        "time": a["start_time"][11:16],
        "name": a.get("name"),
        "type": a.get("type"),
        "event": a.get("event_type"),
        "km": round(dist / 1000, 3),
        "sec": round(mov),
        "hr": a.get("avg_hr_bpm"),
        "hrmax": a.get("max_hr_bpm"),
        "elev": a.get("elevation_gain_meters"),
        "kcal": a.get("calories"),
        "steps": a.get("steps"),
    }
    det = cache(f"a_{a['id']}")
    if isinstance(det, dict):
        r.update({
            "cad": rnd(det.get("avg_cadence")),
            "stride": rnd(det.get("avg_stride_length_cm")),
            "gct": rnd(det.get("avg_ground_contact_time_ms"), 0),
            "vo": rnd(det.get("avg_vertical_oscillation_cm"), 2),
            "pow": rnd(det.get("avg_power_watts"), 0),
            "te": rnd(det.get("training_effect")),
            "ate": rnd(det.get("anaerobic_training_effect")),
            "tl": rnd(det.get("training_load"), 0),
            "tlabel": det.get("training_effect_label"),
            "vig": det.get("vigorous_intensity_minutes"),
            "mod": det.get("moderate_intensity_minutes"),
            "bb": det.get("body_battery_impact"),
        })
    z = cache(f"z_{a['id']}")
    if isinstance(z, list) and z:
        zs = sorted(z, key=lambda x: x["zoneNumber"])
        r["zones"] = [round(x.get("secsInZone") or 0) for x in zs]
        r["zlow"] = [x.get("zoneLowBoundary") for x in zs]
    w = cache(f"w_{a['id']}")
    if isinstance(w, dict) and w.get("temperature") is not None:
        r["temp"] = w.get("temperature")
        r["hum"] = w.get("humidity_percent")
        r["wind"] = w.get("wind_speed")
        r["wx"] = w.get("weather_description")
    sp = cache(f"s_{a['id']}")
    if isinstance(sp, dict) and sp.get("laps"):
        r["laps"] = [[rnd(l.get("distance_meters"), 0), rnd(l.get("moving_duration_seconds") or l.get("duration_seconds"), 1), l.get("avg_hr_bpm"), rnd(l.get("avg_cadence"), 0), rnd(l.get("avg_power_watts"), 0), l.get("intensity_type")] for l in sp["laps"]]
    runs.append(r)
runs.sort(key=lambda r: (r["date"], r["time"]))
by_id = {r["id"]: r for r in runs}

sleep_by = {}
for n in ((parse(load("sleep_range")) or {}).get("nights")) or []:
    sleep_by[n["date"]] = n
for j in cache_glob("r_sleep_"):
    for n in (j or {}).get("nights", []) or []:
        sleep_by[n["date"]] = n
sleep = [{k: n.get(k) for k in ("date", "sleep_hours", "sleep_score", "deep_sleep_percent", "rem_sleep_percent", "avg_overnight_hrv", "avg_sleep_stress")} for _, n in sorted(sleep_by.items()) if n.get("sleep_hours")]

rhr = []
for p in sorted(glob.glob(os.path.join(CACHE, "rhr_*.json"))):
    j = parse(open(p, encoding="utf-8").read())
    try:
        v = j["allMetrics"]["metricsMap"]["WELLNESS_RESTING_HEART_RATE"][0]
        rhr.append({"date": v["calendarDate"], "bpm": v["value"]})
    except Exception:
        pass

bb = {}
for j in cache_glob("r_body_battery_"):
    for row in j if isinstance(j, list) else []:
        bb[row["date"]] = {"date": row["date"], "charged": row.get("charged"), "drained": row.get("drained"), "level": row.get("body_battery_level")}
steps = {}
for j in cache_glob("r_steps_"):
    for row in j if isinstance(j, list) else []:
        steps[row["calendarDate"]] = {"date": row["calendarDate"], "steps": row.get("totalSteps"), "goal": row.get("stepGoal")}

records = []
for rec in cache("g_personal_record") or []:
    if rec.get("type_id") in range(1, 8):
        a = by_id.get(rec.get("activity_id"))
        records.append({"type": rec["record_type"], "value": rec["value"], "raw": rec["raw_value"], "date": a["date"] if a else None, "activity": rec.get("activity_id")})

weigh = ((cache("g_weigh") or {}).get("measurements")) or []
intensity = ((cache("g_intensity") or {}).get("weekly_data")) or []
wstress = ((cache("g_weekly_stress") or {}).get("weekly_data")) or []
lact = cache("g_lactate") or {}

data = {
    "generated": dt.datetime.now().isoformat(timespec="minutes"),
    "runs": runs,
    "load": merged("load_trend", "trend"),
    "hrv": merged("hrv_trend", "trend"),
    "vo2": merged("vo2max_trend", "trend"),
    "sleep": sleep,
    "rhr": rhr,
    "bodybattery": sorted(bb.values(), key=lambda r: r["date"]),
    "steps": sorted(steps.values(), key=lambda r: r["date"]),
    "weight": sorted([{"date": m["date"], "kg": m["weight_kg"]} for m in weigh], key=lambda r: r["date"]),
    "intensity": sorted(intensity, key=lambda r: r["week_start"]),
    "wstress": sorted(wstress, key=lambda r: r["week_start"]),
    "records": records,
    "lactate": lact if isinstance(lact, dict) else {},
    "fitnessage": cache("g_fitnessage") or {},
    "predictions": (parse(load("race_predictions")) or {}),
    "status": parse(load("training_status")) or {},
    "balance": parse(load("load_balance")) or {},
}

with open(os.path.join(HERE, "data.js"), "w", encoding="utf-8") as f:
    f.write("window.DATA=" + json.dumps(data, ensure_ascii=False) + ";")
print({k: (len(v) if isinstance(v, list) else "ok") for k, v in data.items() if k != "generated"})
print("with details:", sum(1 for r in runs if "cad" in r), "zones:", sum(1 for r in runs if "zones" in r), "weather:", sum(1 for r in runs if "temp" in r), "laps:", sum(1 for r in runs if "laps" in r))
