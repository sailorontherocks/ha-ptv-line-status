# Transport Victoria service status for Home Assistant

Version 0.2 creates two Home Assistant entities for each configured Metro train
station, line, and direction. Multiple entries can be added, such as
**North Williamstown → City**, **Newport → Williamstown**, and **Newport → City**.

- **Service status** is an enum sensor whose state is `normal`, `delayed`,
  `disrupted`, `suspended`, or `unknown`.
- **Service issue** is a problem binary sensor. It is off for `normal` and on
  for `delayed`, `disrupted`, `suspended`, or `unknown`.

Both entities use the same coordinator data and therefore share one realtime
feed request and polling schedule per configured service.

The integration polls Transport Victoria's Metro GTFS-Realtime Service Alerts
feed and uses explicit GTFS alert effects to classify service. Informational
alerts (including construction alerts that do not explicitly affect train
operation) are exposed only as a count and do not change the sensor state.

## Installation and development

Copy `custom_components/ptv` into the `custom_components` directory of a Home
Assistant configuration, then restart Home Assistant. For development, mount or
copy this repository into a Home Assistant development environment and run the
tests with `pytest` from the repository root. External API calls are mocked by
the tests; no development API key is required.

The runtime dependency `gtfs-realtime-bindings==2.2.0` is declared in
`manifest.json` and Home Assistant installs it when loading the integration.

## Configuration

In Home Assistant, go to **Settings → Devices & services → Add integration**,
select **Transport Victoria**, enter a Transport Victoria Open Data API key,
then choose a Metro station and direction. A line-selection step appears when a
station is served by multiple lines. Direction labels come from published GTFS
trip destinations rather than the numeric GTFS `direction_id`.

The API key is validated against the Service Alerts endpoint. The static Metro
GTFS Schedule is downloaded during configuration and cached in memory for reuse
by further config flows. The large schedule and its raw tables are not stored in
the config entry. Only resolved IDs and human-readable names are saved. The key
is not logged or exposed in sensor attributes. YAML is not supported.

Existing v0.1 North Williamstown entries are migrated automatically to the new
mapping fields while retaining their API key, entry identity, and unique ID.

## Polling and updates

The feed is fetched every 60 seconds while the integration has listeners. This
is a practical balance for a realtime alert feed and amounts to at most about
1,440 requests per day for this config entry. Transport Victoria's exact quota
is not encoded here; the interval can be revisited if published feed guidance
or rate-limit headers establish a better value.

Authentication failures trigger Home Assistant's authentication-failure path.
Network, HTTP, and malformed protobuf failures mark coordinator data unavailable
and retain Home Assistant's normal retry behavior.

## Known limitations

- Metro trains only; buses, trams, regional trains, and replacement buses are
  excluded.
- Static GTFS is cached only for the current Home Assistant process. The first
  new configuration after a restart downloads the current weekly schedule.
- There is no departure-time data, nearby-stop support, dashboard, automation,
  or HACS packaging.
- Classification is deliberately conservative and based on explicit GTFS-RT
  effects, not keywords in alert titles or descriptions.
- Operational alert attributes contain compact summaries rather than complete
  GTFS-Realtime payloads.
