"""Nearby index for the maps shelf: named POIs from the US extract's amenity/shop/tourism/leisure/healthcare/craft/office
objects (osmium export, GeoJSON sequence) into SQLite with an R*Tree.

Usage: python build_poi.py us-poi.geojsonseq poi.db EXTRACT_TIMESTAMP
"""

import json
import sqlite3
import sys
import time

KEYS = ("amenity", "shop", "tourism", "leisure", "healthcare", "craft", "office", "cuisine")
KEEP = KEYS + ("brand", "opening_hours", "phone", "website", "addr:housenumber", "addr:street", "addr:city",
               "addr:state", "addr:postcode")


def centroid(geom: dict) -> tuple[float, float] | None:
    t, c = geom.get("type"), geom.get("coordinates")
    if t == "Point":
        return c[0], c[1]
    ring = c[0] if t == "Polygon" else c[0][0] if t == "MultiPolygon" else None
    if not ring:
        return None
    return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)


def main(src: str, out: str, extract_ts: str) -> None:
    db = sqlite3.connect(out)
    db.executescript("""
        PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF;
        DROP TABLE IF EXISTS poi; DROP TABLE IF EXISTS poi_rtree; DROP TABLE IF EXISTS meta;
        CREATE TABLE poi (id INTEGER PRIMARY KEY, osm TEXT, name TEXT, lat REAL, lon REAL, cats TEXT, tags TEXT);
        CREATE VIRTUAL TABLE poi_rtree USING rtree(id, min_lat, max_lat, min_lon, max_lon);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
    """)
    t0, n, kept, batch = time.time(), 0, 0, []
    with open(src, encoding="utf-8") as f:
        for line in f:
            line = line.lstrip("\x1e").strip()
            if not line:
                continue
            n += 1
            feat = json.loads(line)
            props = feat.get("properties") or {}
            name = props.get("name")
            pt = centroid(feat.get("geometry") or {})
            if not name or pt is None:
                continue
            cats = "|" + "|".join(f"{k}={v}" for k in KEYS for v in str(props.get(k, "")).split(";") if v) + "|"
            if cats == "||":
                continue
            kept += 1
            osm = feat.get("id") or props.get("@id") or ""
            batch.append((kept, str(osm), name, pt[1], pt[0], cats,
                          json.dumps({k: props[k] for k in KEEP if k in props}, ensure_ascii=False)))
            if len(batch) >= 50_000:
                flush(db, batch)
                print(f"{n:,} read, {kept:,} kept ({time.time() - t0:.0f}s)", flush=True)
    flush(db, batch)
    db.executemany("INSERT INTO meta VALUES (?, ?)", [("extract_timestamp", extract_ts), ("pois", str(kept)),
                                                       ("built_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))])
    db.commit()
    print(f"done: {n:,} read, {kept:,} named POIs ({time.time() - t0:.0f}s)")


def flush(db, batch) -> None:
    db.executemany("INSERT INTO poi VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
    db.executemany("INSERT INTO poi_rtree VALUES (?, ?, ?, ?, ?)", [(b[0], b[3], b[3], b[4], b[4]) for b in batch])
    db.commit()
    batch.clear()


if __name__ == "__main__":
    main(*sys.argv[1:4])
