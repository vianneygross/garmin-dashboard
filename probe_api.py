import os, json, sys, datetime as dt, urllib.request, urllib.error
BASE="https://personal.connectapi.garmin.com"
today=dt.date.today(); d=lambda n:(today-dt.timedelta(days=n)).isoformat()
def call(m,p,h,q=""):
    r=urllib.request.Request(BASE+p+q,method=m,headers=h)
    try:
        with urllib.request.urlopen(r,timeout=30) as x: return x.status,x.read().decode()
    except urllib.error.HTTPError as e: return e.code,e.read().decode()[:150]
def shape(o,dep=0):
    if isinstance(o,dict):
        return {k:shape(v,dep+1) for k,v in o.items()} if dep<4 else "{...}"
    if isinstance(o,list): return ["len=%d"%len(o),shape(o[0],dep+1)] if o else ["len=0"]
    return type(o).__name__
c,b=call("POST","/personalapitoken-service/personal-api/personal-api-key/token",{"Authorization":"ApiKey "+os.environ["GARMIN_API_KEY"]})
H={"Authorization":"Bearer "+b.strip()}
for name,p,q in [("sleep","/sleep-service/sleep/dailySleepSummariesByDate",f"?startDate={d(2)}&endDate={d(1)}"),
 ("sleepDaily","/sleep-service/sleep/dailySleep",f"?date={d(1)}"),
 ("hrvdaily",f"/hrv-service/hrv/daily/{d(3)}/{d(1)}",""),
 ("fitnessage",f"/fitnessage-service/fitnessage/v2/{d(1)}",""),
 ("bodybattery","/wellness-service/wellness/bodyBattery/reports/daily",f"?startDate={d(3)}&endDate={d(1)}"),
 ("steps",f"/usersummary-service/stats/steps/daily/{d(3)}/{d(1)}",""),
 ("weight",f"/weight-service/weight/range/{d(60)}/{d(0)}","")]:
    c,b=call("GET",p,H,q); print("\n==",name,c)
    try: print(json.dumps(shape(json.loads(b)),indent=1)[:2800])
    except Exception: print(b[:150])
c,b=call("GET","/activitylist-service/activities/search/activities",H,"?start=0&limit=5")
j=json.loads(b); print("\ntypes:",sorted({(a["activityType"]["typeKey"],a["eventType"]["typeKey"]) for a in j}))
print("sample unit check: stride",j[0].get("avgStrideLength"),"vo",j[0].get("avgVerticalOscillation"),"dist",j[0].get("distance"),"dur",j[0].get("duration"),"start",j[0].get("startTimeLocal"))
