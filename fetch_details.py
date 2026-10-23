"""Fetches the details the Personal API does not expose (zones, weather, splits, records...) through garmin_mcp.
Everything is cached in ./raw/cache so reruns are incremental. Failures are tolerated."""
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
        print(f"WARN {key}: {e}", flush=True)
        return
    if not txt.strip() or txt.lstrip().startswith('{"error"'):
        return
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
                ("intensity", "get_weekly_intensity_minutes", {"end_date": d(0), "weeks": 52}),
                ("weekly_stress", "get_weekly_stress", {"end_date": d(0), "weeks": 52}),
                ("lactate", "get_lactate_threshold", {"start_date": d(365), "end_date": d(0)}),
            ]
            for key, tool, args in glob:
                await cached(s, "g_" + key, tool, args, ttl_days=0)
                print(key, flush=True)
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


try:
    asyncio.run(main())
except Exception as e:
    print(f"WARN MCP indisponible: {e}", flush=True)
