#!/bin/bash
# Maps shelf build (US): POI extract from the Geofabrik US extract, then Valhalla routing tiles (car/foot/bike).
# Throttled to coexist with the planet tile build: nice/idle I/O, build container memory-capped.
set -euo pipefail
SRC=/mnt/hub/data/maps/us-latest.osm.pbf
W=${MAPS_WORK:-$HOME/maps-work}
mkdir -p "$W"
cd "$W"
mem_sampler() {  # host RAM and container RAM every 10 s, for the build-cost report
  while true; do
    echo "$(date +%T) host_used_mb=$(free -m | awk '/Mem:/{print $3}') swap_used_mb=$(free -m | awk '/Swap:/{print $3}') $(docker stats --no-stream --format '{{.Name}}={{.MemUsage}}' maps-build 2>/dev/null | tr ' ' '_')" >> "$W/mem.log"
    sleep 10
  done
}
mem_sampler & SAMPLER=$!
trap 'kill $SAMPLER' EXIT
step() { echo "=== $(date '+%F %T') $*"; }

step copy extract to NVMe
[ -s us-latest.osm.pbf ] && [ "$(stat -c %s us-latest.osm.pbf)" = "$(stat -c %s $SRC)" ] || cp "$SRC" us-latest.osm.pbf

step POI filter
[ -s us-poi.geojsonseq ] || { /usr/bin/time -v osmium tags-filter -O -o us-poi.osm.pbf us-latest.osm.pbf \
  nwr/amenity nwr/shop nwr/tourism nwr/leisure nwr/healthcare nwr/craft nwr/office 2> poi-filter.time &&
  osmium export -O -f geojsonseq -u type_id --geometry-types=point,polygon -o us-poi.geojsonseq us-poi.osm.pbf; }
grep -E "Maximum resident|Elapsed" poi-filter.time || true

# OSRM (car, MLD) was tried first per the brief and OOM-killed twice in osrm-extract's parsing pass: 18 GB cap on the
# routable-ways extract, 15 GB cap on the car-only extract. Valhalla builds tiles from disk-backed temporaries instead.
VALHALLA_IMAGE=ghcr.io/valhalla/valhalla:latest
mkdir -p "$W/valhalla"
VRUN="docker run --rm --name maps-build --memory=15g --memory-swap=15g --user $(id -u):$(id -g) -v $W:/work $VALHALLA_IMAGE"
step valhalla config
[ -s valhalla/valhalla.json ] || $VRUN sh -c "valhalla_build_config --mjolnir-tile-dir /work/valhalla/tiles \
  --mjolnir-tile-extract /work/valhalla/tiles.tar --mjolnir-concurrency 6 --mjolnir-admin /work/valhalla/none.sqlite \
  --mjolnir-timezone /work/valhalla/none.sqlite > /work/valhalla/valhalla.json"
step valhalla_build_tiles
[ -e valhalla/tiles.done ] || { /usr/bin/time -v -o valhalla-tiles.time $VRUN \
  valhalla_build_tiles -c /work/valhalla/valhalla.json /work/us-latest.osm.pbf && touch valhalla/tiles.done; }
step valhalla_build_extract
[ -s valhalla/tiles.tar ] || /usr/bin/time -v -o valhalla-extract.time $VRUN \
  valhalla_build_extract -c /work/valhalla/valhalla.json -v
step POI index
[ -s "$HOME/maps-data/poi.db" ] || python3 "$(dirname "$0")/build_poi.py" us-poi.geojsonseq "$HOME/maps-data/poi.db" \
  "$(osmium fileinfo -g header.option.timestamp us-latest.osm.pbf)"
step MAPS_PREP_DONE
