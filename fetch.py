"""Pulls the data the Personal API does not expose (predictions, training status, load...) from garmin_mcp into ./raw/*.json.
Failures are tolerated: the previous file is kept."""
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
]
# (name, tool, total days back, max window days)
RANGED = [
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
        print(f"WARN {tool}: {e}", flush=True)
        return ""


def usable(txt):
    return bool(txt.strip()) and not txt.lstrip().startswith('{"error"')


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
            for name, tool, total, step in RANGED:
                if not want(name):
                    continue
                out, off = [], 0
                while off < total:
                    a = min(off + step, total)
                    t = await text(s, tool, {"start_date": d(a), "end_date": d(off)})
                    if usable(t):
                        out.append(t)
                    off = a + 1
                if out:
                    save(name, out)
                else:
                    print("WARN", name, "indisponible, fichier precedent conserve", flush=True)
            for name, tool, args in SINGLE:
                if want(name):
                    t = await text(s, tool, args)
                    if usable(t):
                        save(name, t)
                    else:
                        print("WARN", name, "indisponible, fichier precedent conserve", flush=True)


try:
    asyncio.run(main())
except Exception as e:
    print(f"WARN MCP indisponible: {e}", flush=True)
