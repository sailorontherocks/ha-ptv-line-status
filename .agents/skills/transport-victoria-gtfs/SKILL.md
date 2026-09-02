---
name: transport-victoria-gtfs
description: Resolve Transport Victoria station stop IDs, train route IDs, and human travel directions from the current Metro static GTFS schedule. Use for Victorian GTFS identifier investigation and diagnostic evidence; do not use a GTFS-Realtime feed as the source of these mappings.
---

# Transport Victoria static GTFS mapping

Use Transport Victoria's published GTFS Schedule and select operational branch
`2` (Metropolitan Train). The statewide public schedule is normally available at
`https://data.ptv.vic.gov.au/downloads/gtfs.zip` without an API key. Confirm the
current official resource before relying on it because publication details and
identifiers can change.

## Resolve identifiers

Treat the mapping as a join across the static GTFS tables:

- Resolve a station with `stops.txt`. Report the `location_type=1` parent station
  ID separately from its child platform IDs. `stop_times.txt` normally references
  platforms, while another consumer may require the parent station ID.
- Resolve a line with `routes.txt`. Prefer an exact normalized
  `route_short_name` match, then inspect `route_long_name`. Keep the ordinary rail
  route distinct from a replacement-bus route even when their long names match.
- Join `routes.txt -> trips.txt -> stop_times.txt` to resolve direction. Never
  assign human meaning to `direction_id=0` or `1` from the number alone: GTFS only
  defines them as opposite directions.
- Translate a human direction such as "towards City" by choosing a concrete
  destination or anchor stop, then establish whether that anchor occurs before or
  after the requested station in published stop sequences. Check all relevant
  trips, summarize headsigns and counts by direction, and print at least one
  representative trip in each direction so the conclusion is auditable.

Exclude entrances, pathways, bike-and-ride nodes, and rail-replacement bus stops
from rail-platform matching unless the user explicitly asks about them. Account
for short workings whose trips may not reach the chosen anchor; they are evidence
to report, not a reason to guess.

## Repository diagnostic

In the `ptv-ha` repository, use `scripts/diagnose_gtfs_mapping.py`. It accepts the
statewide ZIP, the nested Metro `google_transit.zip`, or an extracted Metro
directory:

```bash
python3 scripts/diagnose_gtfs_mapping.py --gtfs /path/to/gtfs.zip
```

Without `--gtfs`, it downloads the official schedule into a temporary directory.
Do not commit downloaded feeds, caches, API keys, tokens, or travel data. Run the
script against current data and include its resolved values plus supporting stop,
route, trip, headsign, and stop-order evidence in the response.

Do not build or modify the Home Assistant integration unless the user separately
requests implementation.
