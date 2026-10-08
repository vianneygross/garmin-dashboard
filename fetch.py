"""Pulls data from the garmin_mcp server (stdio) into ./raw/*.json."""
import asyncio, os, json, sys, datetime as dt
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
os.makedirs(RAW, exist_ok=True)
today = dt.date.today()
d = lambda n: (today - dt.timedelta(days=n)).isoformat()

SINGLE = [
    ("race_predictions", "get_race_predictions", {}),
    ("load_balance", "get_training_load_balance", {"date": d(1)}),
    ("training_status", "get_training_status", {"date": d(1)}),
    ("readiness", "get_training_readiness", {"date": d(1)}),
    ("sleep_range", "get_sleep_summary_range", {"start_date": d(30), "end_date": d(0)}),
]
# (name, tool, total days back, max window days)
RANGED = [
    ("hrv_trend", "get_hrv_trend", 150, 29),
    ("vo2max_trend", "get_vo2max_trend", 270, 89),
    ("load_trend", "get_training_load_trend", 150, 89),
]


def save(name, obj):
    with open(os.path.join(RAW, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(obj, f)
    print("saved", name, flush=True)


async def text(s, tool, args):
    try:
        res = await s.call_tool(tool, args)
        return res.content[0].text if res.content else ""
    except Exception as e:
        return json.dumps({"error": str(e)})


async def activities_page(s, start):
    for attempt in range(3):
        response = await text(s, "get_activities", {"start": start, "limit": 100})
        invalid_response = None
        if not response.strip():
            invalid_response = "an empty response"
        else:
            try:
                page = json.loads(response)
            except json.JSONDecodeError:
                invalid_response = "invalid JSON"

        if invalid_response:
            if attempt == 2:
                raise RuntimeError(f"get_activities returned {invalid_response} after 3 attempts")
            delay = 3 * (attempt + 1)
            print(f"get_activities returned {invalid_response}; retrying in {delay}s", flush=True)
            await asyncio.sleep(delay)
            continue

        if not isinstance(page, dict):
            raise RuntimeError("get_activities returned an unexpected response")
        if "error" in page:
            raise RuntimeError(f"get_activities failed: {page['error']}")
        if not isinstance(page.get("activities"), list) or not isinstance(page.get("has_more"), bool):
            raise RuntimeError("get_activities response is missing activities or has_more")
        if page["has_more"] and not isinstance(page.get("next_start"), int):
            raise RuntimeError("get_activities response is missing next_start")
        return page


async def main():
    only = set(sys.argv[1:])
    want = lambda n: not only or n in only
    params = StdioServerParameters(
        command="uvx",
        args=["--python", "3.12", "--from", "git+https://github.com/Taxuspt/garmin_mcp", "garmin-mcp"],
        env=dict(os.environ),
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            if want("activities"):
                acts, start = [], 0
                while True:
                    j = await activities_page(s, start)
                    acts += j.get("activities", [])
                    if not j.get("has_more") or start >= 600:
                        break
                    start = j["next_start"]
                save("activities", {"activities": acts})
            for name, tool, total, step in RANGED:
                if not want(name):
                    continue
                out, off = [], 0
                while off < total:
                    a = min(off + step, total)
                    out.append(await text(s, tool, {"start_date": d(a), "end_date": d(off)}))
                    off = a + 1
                save(name, out)
            for name, tool, args in SINGLE:
                if want(name):
                    save(name, await text(s, tool, args))


asyncio.run(main())
