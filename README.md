# Transport Victoria service status for Home Assistant

This first vertical slice creates one Home Assistant sensor for **North
Williamstown → City** on the Williamstown Line. Its state is one of `normal`,
`delayed`, `disrupted`, `suspended`, or `unknown`.

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
select **Transport Victoria**, and enter a Transport Victoria Open Data API key.
The key is validated against the Service Alerts endpoint and stored only in the
config entry. It is not logged or exposed in sensor state attributes. YAML
configuration is not supported.

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

- Only North Williamstown (`vic:rail:NWN`) towards the City (`direction_id: 1`)
  on the Williamstown Line (`aus:vic:vic-02-WIL:`) is supported.
- There is no dynamic station or direction selection, departure-time data,
  nearby-stop support, dashboard, automation, or HACS packaging.
- Classification is deliberately conservative and based on explicit GTFS-RT
  effects, not keywords in alert titles or descriptions.
- Operational alert attributes contain compact summaries rather than complete
  GTFS-Realtime payloads.
