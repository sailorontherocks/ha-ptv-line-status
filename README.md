# PTV Line Status for Home Assistant

<p align="center">
  <img src="logo.png" alt="PTV Line Status logo" width="220">
</p>

Project/repository: `ha-ptv-line-status`

Home Assistant integration: **PTV Line Status** (`ptv_line_status`)

PTV Line Status provides concise Metro train service information for Home
Assistant. It was originally created to supply service text and an issue
indicator to ESPControl displays, but ESPControl is optional: the same entities
work in ordinary Home Assistant dashboards and automations.

Version 0.2.5 creates three entities for each configured Metro train station,
line, and direction. Multiple entries can be added, such as **North
Williamstown → City**, **Newport → Williamstown**, and **Newport → City**.

## What it provides

- **Service status** is an enum sensor whose state is `normal`, `delayed`,
  `disrupted`, `suspended`, or `unknown`.
- **Service issue** is a problem binary sensor. It is off for `normal` and on
  for `delayed`, `disrupted`, `suspended`, or `unknown`, and during API failures.
- **Service notice** displays a concise message: data unavailable, active
  suspension/disruption/delay (or unknown status), planned disruption, or normal
  service. Active alerts override planned notices. On refresh failure this notice
  remains available to explain the failure, Service issue stays available and on,
  and Service status becomes unavailable. Initial setup must still complete its
  first successful refresh before entities are created.

For ESPControl tiles, use **Service notice** for the concise text and **Service
issue** for a warning or highlight. The status sensor remains useful when you
need the machine-friendly state in an automation or dashboard condition.

All three entities use the same coordinator data and therefore share one realtime
feed request and polling schedule per configured service.

When only future structured alert periods match, status stays `normal`, issue
stays off, and notice says `Planned disruption`. Notice attributes include up to
10 upcoming alert summaries (headlines limited to 200 characters), the full count,
a truncation flag, and the next start/end as Australia/Melbourne ISO timestamps.
Expired and informational alerts are excluded. Times update on the next successful
60-second refresh. A broad multi-day period cannot establish nightly hours such
as "8:30 pm to last service"; free-text timing is not parsed.

The integration polls Transport Victoria's Metro GTFS-Realtime Service Alerts
feed and uses explicit GTFS alert effects to classify service. Informational
alerts (including construction alerts that do not explicitly affect train
operation) are exposed only as a count and do not change the sensor state.

## Installation

### HACS (preferred)

This repository may not appear in HACS's default catalogue, so add it as a custom
repository first:

1. In Home Assistant, open **HACS** → three-dot menu → **Custom repositories**.
2. Add `https://github.com/sailorontherocks/ha-ptv-line-status` with type
   **Integration**.
3. Find **PTV Line Status** in HACS and download it.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration**, then select
   **PTV Line Status**.

Future published releases can be installed through HACS; restart Home Assistant
after each update.

If you already installed this integration manually, back up your existing
`custom_components/ptv_line_status` folder before letting HACS manage that same
folder. Do not remove existing Home Assistant configuration entries.

### Manual installation and development

Copy `custom_components/ptv_line_status` into the `custom_components` directory
of a Home Assistant configuration, then restart Home Assistant. For development,
mount or copy this repository into a Home Assistant development environment and
run the tests with `pytest` from the repository root. External API calls are
mocked by the tests; no development API key is required.

The runtime dependency `gtfs-realtime-bindings==2.2.0` is declared in
`manifest.json` and Home Assistant installs it when loading the integration.

## Obtain an API key

PTV Line Status consumes Transport Victoria **GTFS-Realtime** data. Create an
account or sign in at the [Transport Victoria Open Data
Portal](https://opendata.transport.vic.gov.au/). After signing in, open **My
Account → Profile → API tokens**. Locate the **API Key** under **Subscription
Keys** (portal labels may vary). Do not use the separate **Create API Token**
option under **Data Platform API Tokens**, or the older PTV Timetable API
developer-ID/key pair. Enter the Open Data Portal API key only in the PTV Line
Status configuration flow in Home Assistant. Never put the key in GitHub, YAML
examples, ESPControl configuration, or screenshots.

The portal's [Help and Support](https://opendata.transport.vic.gov.au/Help-And-Support)
page links to its current registration, login, and API-key guides. Account
registration includes confirmation and multi-factor authentication steps.

## Configuration

After installing, enter the Open Data Portal API key, then choose a Metro station
and direction. A line-selection step appears when a station is served by multiple
lines. Direction labels come from published GTFS trip destinations rather than
the numeric GTFS `direction_id`.

The API key is validated against the Service Alerts endpoint. The static Metro
GTFS Schedule is downloaded during configuration and cached in memory for reuse
by further config flows. The large schedule and its raw tables are not stored in
the config entry. Only resolved IDs and human-readable names are saved. The key
is not logged or exposed in sensor attributes. YAML is not supported.

Existing v0.1 North Williamstown entries are migrated automatically to the new
mapping fields while retaining their API key, entry identity, and unique ID.

### Upgrading from the former `ptv` domain

The integration was renamed to the `ptv_line_status` domain. Home Assistant does
not provide a supported way for a custom integration to transfer config entries
between domains. Remove entries belonging to the former **Transport Victoria**
integration, remove the old `custom_components/ptv` directory, install
`custom_components/ptv_line_status`, restart Home Assistant, and add the desired
services again through **PTV Line Status**. Do not edit Home Assistant `.storage`
files.

The entity unique-ID algorithms have not otherwise changed. Re-adding an entry
creates a new Home Assistant config-entry ID, so entity-registry IDs and history
from the former domain cannot be guaranteed to attach automatically.

## Polling and updates

The feed is fetched every 60 seconds while the integration has listeners. This
is a practical balance for a realtime alert feed and amounts to at most about
1,440 requests per day for this config entry. Transport Victoria's exact quota
is not encoded here; the interval can be revisited if published feed guidance
or rate-limit headers establish a better value.

All runtime failures, including HTTP 401/403 authentication rejection, retain
the configured API key and retry automatically. Consecutive failures wait 60,
120, 240, 480, then 900 seconds; further failures stay at 900 seconds. A valid
`Retry-After` value (seconds or HTTP-date) extends the wait if longer. Success
resets the backoff and resumes normal 60-second polling. Manual entity refreshes
respect the same deadline, and requests within an entry are serialized. Timer
rounding can delay a retry by approximately one second. Unloading the entry
cancels its scheduled polling.

If the first fetch during startup fails, Home Assistant marks the existing entry
as not ready and retries setup automatically with its stored key. Home Assistant
controls setup retry scheduling, so the actual fetch can happen later than the
runtime deadline. The integration retains the deadline across setup attempts in
the same process, including `Retry-After`; earlier setup attempts do not contact
the API. A full Home Assistant restart resets the in-memory backoff. Entities
remain unavailable until the first successful setup fetch.

To change a key manually, go to **Settings → Devices & services → PTV Line Status**,
open the configured entry's three-dot menu, and select **Reconfigure**. The new
key is validated before it replaces the stored value; failed validation leaves
the key and journey mapping unchanged. Initial setup validation and the existing
reauthentication form are still supported.

For an entry already stuck requesting reauthentication from an older version,
install these updated integration files and restart Home Assistant, or reload
the entry after the updated code is loaded. Setup retries use the existing key;
there is no need to remove/recreate the entry or re-enter the key. A successful
fetch dismisses any remaining reauthentication flow for that entry through Home
Assistant's flow API. If the server keeps rejecting the key, automatic retries
continue; use **Reconfigure** if you have a replacement key.

## Troubleshooting

To enable diagnostic logging, add this to your Home Assistant configuration:

```yaml
logger:
  logs:
    custom_components.ptv_line_status: debug
```

Debug logs must never contain the API key. Runtime failure logs include a fixed
message, feed name, failure category and HTTP status when available. Config-flow
debug logs report HTTP status only. The API client still classifies authentication
and gateway failures separately and sanitises its bounded error details, but the
coordinator does not log response bodies or arbitrary exception text. Request
headers and raw transport exceptions are never logged.

HTTP 401 and explicit invalid-key HTTP 403 responses display **API authentication
error** while continuing retries. Gateway/WAF 403 responses (including error code
1010), HTTP 5xx and connection/timeout failures display **API unavailable**.
HTTP 429 displays **API rate limited**. Empty responses, unexpected content types
and invalid protobuf display **API returned invalid data**. None of these runtime
errors automatically starts reauthentication or replaces your key.
During failure, stale service status and planned-alert details are not presented
as current. Service notice and Service issue expose safe diagnostic attributes:
`last_successful_update`, `next_retry_time`, `consecutive_failure_count`,
`last_failure_category`, `last_http_status`, and `feed_name`. The failure fields
reset on recovery. Active/planned alert priorities resume after a successful fetch.
Home Assistant's coordinator logs unavailability and recovery without repeating
the same error on every poll. Config-flow screens show concise translated errors,
not server response text; validation HTTP status is available at debug level.

## Known limitations

- Metro trains only; buses, trams, regional trains, and replacement buses are
  excluded.
- Static GTFS is cached only for the current Home Assistant process. The first
  new configuration after a restart downloads the current weekly schedule.
- There is no departure-time data, nearby-stop support, dashboard, or automation
  configuration generated by the integration.
- Classification is deliberately conservative and based on explicit GTFS-RT
  effects, not keywords in alert titles or descriptions.
- Operational alert attributes contain compact summaries rather than complete
  GTFS-Realtime payloads.

## PTV data attribution and disclaimer

Source: Licensed from Public Transport Victoria under a Creative Commons
Attribution 4.0 International Licence.

This project is not affiliated with, endorsed by, or sponsored by Public
Transport Victoria or Home Assistant.

The project logo is not an official Public Transport Victoria or Home Assistant
logo. Its provenance should be confirmed before public release; replace it with
an original, non-official visual if it incorporates either organisation's
branding or trademarked material.

## Development

This integration was created and continues to be developed with AI assistance.

Changes are checked with automated tests before release. Bugs and limitations may remain; issue reports are welcome.

## Licence

This project is licensed under the MIT License. See LICENSE.
