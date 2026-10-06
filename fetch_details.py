"""Fetches per-run and daily details through garmin_mcp. Everything is cached in ./raw/cache so reruns are incremental."""
import asyncio, os, json, sys, datetime as dt
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
CACHE = os.path.join(RAW, "cache")
os.makedirs(CACHE, exist_ok=True)
today = dt.date.today()
d = lambda n: (today - dt.timedelta(days=n)).isoformat()

acts = json.load(open(os.path.join(RAW, "activities.json"), encoding="utf-8"))["activities"]
runs = sorted([a for a in acts if "running" in (a.get("type") or "") and (a.get("distance_meters") or 0) >= 800], key=lambda a: a["start_time"])
ids = [a["id"] for a in runs]


def cpath(key):
    return os.path.join(CACHE, key + ".json")


async def cached(s, key, tool, args, ttl_days=None):
    p = cpath(key)
    if os.path.exists(p):
        age = (dt.datetime.now().timestamp() - os.path.getmtime(p)) / 86400
        if ttl_days is None or age < ttl_days:
            return
    try:
        res = await s.call_tool(tool, args)
        txt = res.content[0].text if res.content else ""
    except Exception as e:
        txt = "ERR " + str(e)
    with open(p, "w", encoding="utf-8") as f:
        f.write(txt)


async def main():
    params = StdioServerParameters(
        command="uvx",
        args=["--python", "3.12", "--from", "git+https://github.com/Taxuspt/garmin_mcp", "garmin-mcp"],
        env=dict(os.environ),
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            # global, small calls (refreshed every run)
            glob = [
                ("personal_record", "get_personal_record", {}),
                ("fitnessage", "get_fitnessage_data", {"date": d(1), "details": False}),
                ("weigh", "get_weigh_ins", {"start_date": d(365), "end_date": d(0)}),
                ("intensity", "get_weekly_intensity_minutes", {"end_date": d(0), "weeks": 52}),
                ("weekly_stress", "get_weekly_stress", {"end_date": d(0), "weeks": 52}),
                ("lactate", "get_lactate_threshold", {"start_date": d(365), "end_date": d(0)}),
                ("acclimation", "get_acclimation", {"date": d(1)}),
            ]
            for key, tool, args in glob:
                await cached(s, "g_" + key, tool, args, ttl_days=0)
                print(key, flush=True)
            # ranged daily series in chunks
            for key, tool, total, step in [
                ("body_battery", "get_body_battery", 90, 29),
                ("resp", "get_respiration_trend", 90, 29),
                ("sleep", "get_sleep_summary_range", 180, 29),
                ("steps", "get_daily_steps", 90, 29),
            ]:
                off = 0
                while off < total:
                    a = min(off + step, total)
                    await cached(s, f"r_{key}_{d(a)}_{d(off)}", tool, {"start_date": d(a), "end_date": d(off)}, ttl_days=0 if off == 0 else None)
                    off = a + 1
                print(key, flush=True)
            # daily resting HR (cached by day)
            for n in range(0, 120):
                await cached(s, f"rhr_{d(n)}", "get_rhr_day", {"date": d(n)}, ttl_days=0 if n < 2 else None)
            print("rhr", flush=True)
            # per-run details
            for i, rid in enumerate(ids):
                await cached(s, f"a_{rid}", "get_activity", {"activity_id": rid})
                if i % 20 == 0:
                    print("activity", i, "/", len(ids), flush=True)
            recent = ids[-150:]
            for i, rid in enumerate(recent):
                await cached(s, f"z_{rid}", "get_activity_hr_in_timezones", {"activity_id": rid})
                if i % 20 == 0:
                    print("zones", i, "/", len(recent), flush=True)
            for i, rid in enumerate(ids[-80:]):
                await cached(s, f"w_{rid}", "get_activity_weather", {"activity_id": rid})
                await cached(s, f"s_{rid}", "get_activity_splits", {"activity_id": rid})
                if i % 10 == 0:
                    print("weather+splits", i, "/ 80", flush=True)
    print("DONE", flush=True)


asyncio.run(main())
