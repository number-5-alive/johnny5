"""Maps shelf packet API: geocode, reverse, route and nearby as JSON data packets for the harness tool layer.

Backends (localhost only): Photon (geocode/reverse), Valhalla (route: car / foot / bike), SQLite R*Tree of named POIs
(nearby). OSRM was the briefed router but its US preprocessing does not fit argo's RAM (DESIGN.md, maps shelf).
Every response carries provenance: the data source and its vintage. Bound to argo's tailnet address only.

Run: uvicorn laya_qwen.maps_api:app --host 100.108.252.74 --port 8210
Config: ~/maps-data/maps.json (optional) overrides DEFAULTS.
"""

import json
import math
import os
import re
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query

DATA = Path(os.environ.get("MAPS_DATA", "~/maps-data")).expanduser()
DEFAULTS = {
    "photon": "http://127.0.0.1:2322",
    "valhalla": "http://127.0.0.1:8002",
    "poi_db": str(DATA / "poi.db"),
    "extract": {"source": "OpenStreetMap, Geofabrik US extract (us-latest.osm.pbf)",
                "vintage": "2026-10-15T20:21:00Z"},
    "geocoder": {"source": "OpenStreetMap via Photon USA dump (GraphHopper photon-db-usa-release-261011)",
                 "vintage": "2026-10-11"},
}
M_PER_MILE = 1609.344

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky",
    "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota",
    "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico", "GU": "Guam", "VI": "United States Virgin Islands", "AS": "American Samoa",
    "MP": "Northern Mariana Islands",
}
STATE_CODES = {v.lower(): k for k, v in STATES.items()}

# nearby categories -> OSM tags (key=value); any "key=value" is also accepted directly
CATEGORIES = {
    "coffee": ["amenity=cafe", "shop=coffee", "cuisine=coffee_shop"],
    "cafe": ["amenity=cafe", "cuisine=coffee_shop"],
    "restaurant": ["amenity=restaurant"], "fast_food": ["amenity=fast_food"],
    "bar": ["amenity=bar", "amenity=pub"], "fuel": ["amenity=fuel"], "gas": ["amenity=fuel"],
    "ev_charging": ["amenity=charging_station"], "pharmacy": ["amenity=pharmacy", "healthcare=pharmacy"],
    "hospital": ["amenity=hospital", "healthcare=hospital"], "urgent_care": ["healthcare=clinic", "amenity=clinic"],
    "doctor": ["amenity=doctors", "healthcare=doctor"], "dentist": ["amenity=dentist", "healthcare=dentist"],
    "grocery": ["shop=supermarket", "shop=grocery", "shop=convenience"], "supermarket": ["shop=supermarket"],
    "hotel": ["tourism=hotel", "tourism=motel", "tourism=guest_house"], "atm": ["amenity=atm"],
    "bank": ["amenity=bank"], "parking": ["amenity=parking"], "library": ["amenity=library"],
    "school": ["amenity=school"], "park": ["leisure=park"], "museum": ["tourism=museum"],
    "post_office": ["amenity=post_office"], "police": ["amenity=police"], "fire_station": ["amenity=fire_station"],
    "veterinary": ["amenity=veterinary"], "car_repair": ["shop=car_repair"],
    "hardware": ["shop=hardware", "shop=doityourself"], "place_of_worship": ["amenity=place_of_worship"],
}

app = FastAPI(title="maps shelf (geocode / reverse / route / nearby) and code shelf (/code/search)")

from .code_api import router as code_router  # noqa: E402  (code shelf shares this service's tailnet binding)

app.include_router(code_router)
_local = threading.local()


@lru_cache(maxsize=1)
def _file_cfg() -> dict:
    p = DATA / "maps.json"
    return json.loads(p.read_text()) if p.exists() else {}


def cfg(key: str):
    return _file_cfg().get(key, DEFAULTS[key])


_photon_status: dict = {}


def photon_status() -> dict:
    """The geocoder index's own import date (Photon /status), cached once read."""
    if not _photon_status:
        try:
            st = client().get(f"{cfg('photon')}/status", timeout=5).json()
            _photon_status.update(vintage=st["import_date"], engine=f"Photon {st.get('version', '')}".strip())
        except Exception:
            return {}
    return _photon_status


def provenance(*kinds: str) -> list[dict]:
    out = []
    for k in kinds:
        if k == "geocoder":
            out.append({"tool": "geocoder (Photon)", **cfg("geocoder"), **photon_status()})
        elif k == "route":
            out.append({"tool": "router (Valhalla)", **cfg("extract")})
        elif k == "nearby":
            out.append({"tool": "POI index (OSM amenity/shop/tourism/leisure/healthcare/craft/office)",
                        **cfg("extract")})
    return out


def client() -> httpx.Client:
    if not hasattr(_local, "c"):
        _local.c = httpx.Client(timeout=20)
    return _local.c


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


# ---------------------------------------------------------------- geocoding

def split_state(q: str, state: str | None) -> tuple[str, str | None]:
    """'Ocean Springs, MS' -> ('Ocean Springs', 'Mississippi'); an explicit state wins."""
    if state:
        return q, STATES.get(state.upper(), state.title())
    m = re.match(r"^(.*?),\s*([A-Za-z .]+)$", q.strip())
    if m:
        tail = m.group(2).strip().rstrip(".")
        if tail.upper() in STATES:
            return m.group(1), STATES[tail.upper()]
        if tail.lower() in STATE_CODES:
            return m.group(1), tail.title()
    return q, None


def place(feat: dict, origin: tuple[float, float] | None = None) -> dict:
    p, (lon, lat) = feat["properties"], feat["geometry"]["coordinates"]
    state = p.get("state")
    out = {
        "name": p.get("name") or " ".join(x for x in (p.get("housenumber"), p.get("street")) if x) or None,
        "lat": round(lat, 6), "lon": round(lon, 6),
        "kind": p.get("type"), "osm_tag": f"{p.get('osm_key')}={p.get('osm_value')}",
        "street": " ".join(x for x in (p.get("housenumber"), p.get("street")) if x) or None,
        "locality": p.get("city") or p.get("locality") or p.get("district") or (
            p.get("name") if p.get("type") in ("city", "locality", "district") else None),
        "county": p.get("county"), "state": state, "state_code": STATE_CODES.get((state or "").lower()),
        "postcode": p.get("postcode"), "country": p.get("country"), "country_code": p.get("countrycode"),
        "osm": f"{p.get('osm_type', '')}{p.get('osm_id', '')}",
    }
    if origin:
        out["distance_m"] = round(haversine_m(origin[0], origin[1], lat, lon))
    return {k: v for k, v in out.items() if v is not None}


def photon(path: str, **params) -> list[dict]:
    try:
        r = client().get(f"{cfg('photon')}{path}", params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(503, f"geocoder unavailable: {type(e).__name__}")
    return r.json().get("features", [])


def geocode_places(q: str, state: str | None = None, near: tuple[float, float] | None = None,
                   limit: int = 5) -> tuple[list[dict], str | None]:
    name, st = split_state(q, state)
    query = f"{name}, {st}" if st else name
    feats = photon("/api", q=query, limit=max(limit * 4, 10), lang="en",
                   lat=near[0] if near else None, lon=near[1] if near else None)
    places = [place(f, near) for f in feats]
    if st:  # a stated state is a hard constraint: never return Jackson, TN for "Jackson, Mississippi"
        places = [p for p in places if (p.get("state") or "").lower() == st.lower()]
    return places[:limit], st


@app.get("/geocode")
def geocode(q: str, state: str | None = Query(None, description="state name or code; a hard filter"),
            near: str | None = Query(None, description="'lat,lon' to bias results"), limit: int = 5):
    near_pt = parse_point(near) if near else None
    places, st = geocode_places(q, state, near_pt, min(limit, 20))
    return {"query": q, "state_filter": st, "results": places, "provenance": provenance("geocoder")}


@app.get("/reverse")
def reverse(lat: float, lon: float):
    feats = photon("/reverse", lat=lat, lon=lon, limit=1, lang="en")
    locality = photon("/reverse", lat=lat, lon=lon, limit=1, lang="en", radius=15, layer=["city", "locality"])
    result = place(feats[0], (lat, lon)) if feats else None
    loc = place(locality[0], (lat, lon)) if locality else None
    area = {k: (result or {}).get(k) or (loc or {}).get(k) for k in ("locality", "county", "state", "state_code")}
    if loc and loc.get("name"):
        area["nearest_locality"] = loc["name"]
        area["nearest_locality_distance_m"] = loc.get("distance_m")
    return {"query": {"lat": lat, "lon": lon}, "place": result, "area": area, "provenance": provenance("geocoder")}


# ---------------------------------------------------------------- routing

def parse_point(s: str) -> tuple[float, float] | None:
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", s)
    return (float(m.group(1)), float(m.group(2))) if m else None


def resolve(s: str, state: str | None) -> dict:
    pt = parse_point(s)
    if pt:
        return {"input": s, "lat": pt[0], "lon": pt[1]}
    places, _ = geocode_places(s, state, None, 1)
    if not places:
        raise HTTPException(404, f"could not geocode {s!r}")
    return {"input": s, **places[0]}


PROFILES = {"car": "auto", "foot": "pedestrian", "bike": "bicycle"}
ROUTE_REF = re.compile(r"^(I|US|[A-Z]{2}|CR|SR)[ -](\d+[A-Z]?)\b")


def road_label(names: list[str]) -> str | None:
    """A maneuver's road: the first route number (I 10 -> I-10, US 90 -> US-90), else its first street name."""
    for n in names:
        m = ROUTE_REF.match(n)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
    return names[0] if names else None


def corridor(maneuvers: list[dict], total_mi: float) -> list[dict]:
    """Roads carrying at least 3% of the route (or 5 miles), in driving order."""
    order, dist, ref_of = [], {}, {}
    for mv in maneuvers:  # names seen alongside a route number (MS 67 + "Scenic Expressway") take that number
        names = mv.get("street_names") or []
        ref = road_label(names)
        if ref and ROUTE_REF.match(names[0] if names else "") is None:
            continue
        for n in names:
            if ref and not ROUTE_REF.match(n):
                ref_of.setdefault(n, ref)
    for mv in maneuvers:
        names = mv.get("street_names") or []
        label = road_label(names)
        if label and not ROUTE_REF.match(names[0]):
            label = ref_of.get(names[0], label)
        if not label:
            continue
        if label not in dist:
            order.append(label)
            dist[label] = 0.0
        dist[label] += mv.get("length", 0.0)
    keep = [r for r in order if dist[r] >= min(0.03 * total_mi, 5)]
    return [{"road": r, "miles": round(dist[r], 1)} for r in keep]


def decode_polyline6(s: str) -> list[list[float]]:
    coords, idx, lat, lon = [], 0, 0, 0
    while idx < len(s):
        vals = []
        for _ in range(2):
            shift = result = 0
            while True:
                b = ord(s[idx]) - 63
                idx += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            vals.append(~(result >> 1) if result & 1 else result >> 1)
        lat, lon = lat + vals[0], lon + vals[1]
        coords.append([lon / 1e6, lat / 1e6])
    return coords


@app.get("/route")
def route(origin: str = Query(..., alias="from", description="place name or 'lat,lon'"),
          to: str = Query(..., description="place name or 'lat,lon'"),
          from_state: str | None = None, to_state: str | None = None,
          profile: str = Query("car", description="car | foot | bike"), geometry: bool = False):
    if profile not in PROFILES:
        raise HTTPException(400, f"profile must be one of {list(PROFILES)}")
    a, b = resolve(origin, from_state), resolve(to, to_state)
    req = {"locations": [{"lat": a["lat"], "lon": a["lon"]}, {"lat": b["lat"], "lon": b["lon"]}],
           "costing": PROFILES[profile], "units": "miles", "directions_options": {"units": "miles"}}
    try:
        r = client().post(f"{cfg('valhalla')}/route", json=req, timeout=60)
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise HTTPException(503, f"router unavailable: {type(e).__name__}")
    if "trip" not in data:
        raise HTTPException(422, f"no route: {data.get('error', data)}")
    trip = data["trip"]
    miles, seconds = trip["summary"]["length"], trip["summary"]["time"]
    maneuvers = [m for leg in trip["legs"] for m in leg.get("maneuvers", [])]
    roads = corridor(maneuvers, miles)
    minutes = round(seconds / 60)
    out = {
        "from": a, "to": b, "profile": profile,
        "distance_miles": round(miles, 1), "distance_km": round(miles * M_PER_MILE / 1000, 1),
        "duration_minutes": minutes, "duration": f"{minutes // 60}h{minutes % 60:02d}",
        "corridor": roads, "corridor_summary": " → ".join(x["road"] for x in roads),
        "note": "typical travel time from OSM road classes and speeds; no live traffic",
        "provenance": provenance(*(["geocoder"] if not (parse_point(origin) and parse_point(to)) else []), "route"),
    }
    if geometry:
        pts = [p for leg in trip["legs"] for p in decode_polyline6(leg["shape"])]
        step = max(1, len(pts) // 500)
        out["geometry"] = {"type": "LineString", "coordinates": pts[::step] + ([pts[-1]] if len(pts) % step else [])}
    return out


# ---------------------------------------------------------------- nearby

def osm_ref(osm: str) -> str:
    """osmium area ids (a<2*way id> or a<2*relation id + 1>) back to OSM ids: w123 / r456."""
    if osm.startswith("a") and osm[1:].isdigit():
        n = int(osm[1:])
        return f"r{(n - 1) // 2}" if n % 2 else f"w{n // 2}"
    return osm


def poi_db() -> sqlite3.Connection:
    if not hasattr(_local, "poi"):
        _local.poi = sqlite3.connect(f"file:{cfg('poi_db')}?mode=ro", uri=True, check_same_thread=False)
    return _local.poi


@app.get("/nearby")
def nearby(category: str = Query(..., description=f"one of {sorted(CATEGORIES)} or an OSM key=value"),
           at: str = Query(..., description="'lat,lon' or a place name"), state: str | None = None,
           radius_km: float = 5.0, limit: int = 10):
    centre = resolve(at, state)
    lat, lon = centre["lat"], centre["lon"]
    tags = CATEGORIES.get(category.lower().replace(" ", "_"))
    if tags is None:
        if "=" not in category:
            raise HTTPException(400, f"unknown category {category!r}; use one of {sorted(CATEGORIES)} or key=value")
        tags = [category]
    radius_km = min(max(radius_km, 0.1), 50)
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(0.01, math.cos(math.radians(lat))))
    rows = poi_db().execute(
        "SELECT p.osm, p.name, p.lat, p.lon, p.cats, p.tags FROM poi_rtree r JOIN poi p ON p.id = r.id "
        "WHERE r.min_lat >= ? AND r.max_lat <= ? AND r.min_lon >= ? AND r.max_lon <= ?",
        (lat - dlat, lat + dlat, lon - dlon, lon + dlon)).fetchall()
    found = []
    for osm, name, plat, plon, cats, tags_json in rows:
        if not any(f"|{t}|" in cats for t in tags):
            continue
        d = haversine_m(lat, lon, plat, plon)
        if d > radius_km * 1000:
            continue
        t = json.loads(tags_json)
        addr = " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x)
        found.append({k: v for k, v in {
            "name": name, "lat": round(plat, 6), "lon": round(plon, 6), "distance_m": round(d),
            "distance_miles": round(d / M_PER_MILE, 2), "category": next(x for x in tags if f"|{x}|" in cats),
            "brand": t.get("brand"), "address": addr or None, "city": t.get("addr:city"),
            "opening_hours": t.get("opening_hours"), "osm": osm_ref(osm)}.items() if v is not None})
    found.sort(key=lambda x: x["distance_m"])
    return {"category": category, "osm_tags": tags, "centre": centre, "radius_km": radius_km,
            "count": len(found[:limit]), "results": found[:limit],
            "provenance": provenance(*(["geocoder"] if not parse_point(at) else []), "nearby")}


@app.get("/health")
def health():
    status = {}
    for name, url in (("photon", f"{cfg('photon')}/status"), ("valhalla", f"{cfg('valhalla')}/status")):
        try:
            status[name] = client().get(url, timeout=5).status_code == 200
        except httpx.HTTPError:
            status[name] = False
    try:
        status["poi_db"] = poi_db().execute("SELECT value FROM meta WHERE key = 'pois'").fetchone()[0]
    except Exception:
        status["poi_db"] = False
    return {"ok": all(status.values()), "backends": status,
            "provenance": provenance("geocoder", "route", "nearby")}
