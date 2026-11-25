import datetime as dt
import gzip
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

# Fixed, publicly documented XMLTV endpoints intended for EPG clients.
SOURCES = [
    ("Greek TV EPG", "https://ext.greektv.app/epg/epg.xml.gz"),
    ("IPTV-EPG", "https://iptv-epg.org/files/epg-gr.xml"),
]
# Only basic factual scheduling fields; no descriptions, images or raw feed.
CHANNELS = {
    "ert1": "ΕΡΤ1", "ert2": "ΕΡΤ2", "ert3": "ΕΡΤ3", "ertnews": "ΕΡΤ News",
    "mega": "MEGA", "ant1": "ANT1", "alpha": "ALPHA", "star": "STAR",
    "skai": "ΣΚΑΪ", "open": "OPEN", "maktv": "ΜΑΚ TV", "makedoniatv": "ΜΑΚ TV",
}
def normalized(s):
    import unicodedata
    s = ''.join(c for c in unicodedata.normalize("NFKD",s.casefold()) if not unicodedata.combining(c))
    s = s.translate(str.maketrans({"ε":"e","ρ":"r","τ":"t","σ":"s","ς":"s","κ":"k","α":"a","ι":"i","μ":"m"}))
    return re.sub(r"[^a-z0-9]", "", s)
def match(name, cid):
    for item in (name,cid):
        key=normalized(item)
        key=re.sub(r"(hd|sd|gr|greece)+$", "", key)
        if key in CHANNELS: return CHANNELS[key]
    return None
def parse_time(s):
    try:
        return int(dt.datetime.strptime(s.strip(), "%Y%m%d%H%M%S %z").timestamp()*1000)
    except (ValueError, AttributeError): return None
def pull(url):
    req=urllib.request.Request(url, headers={"User-Agent":"TVGuide personal EPG client/1.0", "Accept":"application/xml,text/xml,application/gzip,*/*"})
    with urllib.request.urlopen(req, timeout=35) as r:
        raw=r.read(25_000_001)
    if len(raw)>25_000_000: raise ValueError("feed too large")
    if raw[:2]==b"\x1f\x8b":
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as f: raw=f.read(50_000_001)
        if len(raw)>50_000_000: raise ValueError("decompressed feed too large")
    return ET.fromstring(raw)
now=int(dt.datetime.now(dt.timezone.utc).timestamp()*1000)
for source,url in SOURCES:
    try:
        root=pull(url)
        if root.tag!="tv": raise ValueError("not XMLTV")
        channels={}
        for ch in root.findall("channel"):
            cid=ch.get("id","")
            name=next((n.text.strip() for n in ch.findall("display-name") if n.text),cid)
            label=match(name,cid)
            if cid and label: channels[cid]=label
        rows=[]
        for p in root.findall("programme"):
            cid=p.get("channel","")
            if cid not in channels: continue
            a,b=parse_time(p.get("start")),parse_time(p.get("stop"))
            title=(p.findtext("title") or "").strip()
            if not a or not b or not title or b<=a or b<now-86400000 or a>now+3*86400000: continue
            cats=[x.text.strip() for x in p.findall("category") if x.text]
            date=p.findtext("date") or ""
            year=re.match(r"(19\d{2}|20\d{2})", date)
            rows.append(dict(ch=cid,start=a,stop=b,title=title,categories=cats,year=year.group() if year else "",desc=""))
        live={r["ch"] for r in rows if r["start"]<=now<r["stop"]}
        if len({channels[x] for x in live})<4: raise ValueError("fewer than four national channels with current listings")
        # Deduplicate SD/HD by keeping the variant with the best coverage.
        selected={}
        for cid,label in channels.items():
            score=(cid in live, sum(r["ch"]==cid for r in rows))
            if label not in selected or score>selected[label][0]: selected[label]=(score,cid)
        keep={v[1] for v in selected.values()}
        channels={k:v for k,v in channels.items() if k in keep}
        rows=sorted([r for r in rows if r["ch"] in keep],key=lambda r:r["start"])
        data={"source":source,"sourceUrl":url,"at":now,"channels":channels,"rows":rows}
        path=Path("data/schedule.json");path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        print(f"{source}: {len(channels)} channels, {len(rows)} listings, {len(live)} current")
        sys.exit(0)
    except Exception as e:
        print(f"{source}: {type(e).__name__}: {e}",file=sys.stderr)
sys.exit("No usable current feed; previous schedule is not replaced.")
