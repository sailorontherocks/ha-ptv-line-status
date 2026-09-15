# Planned-disruption design

## Original investigation (before 0.2.3)

The API client returns the complete decoded FeedMessage. Alert.active_period,
all description_text translations, and informed_entity.trip (including trip_id,
start_date and start_time) survive decoding. evaluate_feed retains the complete
entity for active matching alerts. evaluate_service_alerts reduces those entities
to AlertDetail summaries: descriptions, periods and trip selectors are omitted.
Inactive matching alerts are counted and discarded from these summaries.

period_is_active already compares epoch seconds using start <= now < end.
alert_is_active accepts any matching period, including open-ended intervals;
an omitted active_period has no time restriction. A timezone conversion cannot
fix a broad multi-day interval that contains the morning. matching_selectors
currently uses only top-level route_id, stop_id and direction_id, ignoring trip
constraints (and not resolving selectors with only a nested trip route).

The available local alerts.pb snapshot is dated 2026-09-02 10:40:10 AEST and
does not contain entity 24ef2694-69ab-5955-bd6b-6d3b15953c69. Its current timing
has not been verified. The new fixtures are synthetic, not captured PTV evidence.

## Implemented presentation in 0.2.3

1. Reuse the existing epoch comparisons for operational effects. Use
   ZoneInfo("Australia/Melbourne") to present period boundaries as ISO timestamps
   with offsets, including daylight saving. Never assume a fixed UTC offset.
2. Preserve the diagnostic evaluate_feed return contract. In the shared evaluator,
   collect matching operational-effect alerts that are inactive now but have a
   future structured period (start > now). This includes gaps between nightly
   periods; exclude expired-only alerts and informational alerts.
3. Add planned_alerts to ServiceAlertResult, with an empty tuple default for
   compatibility. The service-notice sensor attributes expose planned_alert_count and a
   bounded planned_alerts list: ID, effect, short header, next start/end in
   Melbourne time. Proposed limits: 10 summaries, 200 characters per header;
   report the full count and whether the summaries were truncated. Do not expose
   full descriptions or entire protobuf entities as recorder attributes.
4. Planned alerts never contribute to overall severity. With no other active
   operational alerts, service_status remains normal and service_issue is off.
   If another alert is active, its effect still determines severity. Keep the
   existing coordinator and 60-second polling; boundary changes appear on the
   next successful poll. Failed refreshes still make entities unavailable.
5. Keep no-period/open-ended semantics. Missing timing is not evidence of a
   future-only alert. Do not derive intervals from prose or from trip start_time:
   a trip start identifies a service instance, not its disruption end time.

The presentation feature uses the structured periods as supplied. The service
notice reports data unavailability first, then active status (including unknown),
then planned disruption, then normal service. It remains available after refresh
failures; the operational entities retain normal coordinator availability rules.
The reported PTV alert's nightly timing remains unverified. No English time
parser or per-alert override is implemented.

## Evidence needed before a fallback

Inspect the current complete decoded entity, preserving field presence:

- Feed header timestamp and fetch time; entity id and is_deleted.
- Every active_period.start/end as raw epoch values and Melbourne timestamps;
  distinguish missing fields from zero. Check for individual nightly windows
  versus a single announcement window spanning multiple dates.
- All header_text, description_text and url translations; cause and effect.
- Every informed_entity, including agency_id, route_id, route_type, stop_id,
  direction_id, and its complete trip descriptor: trip_id, route_id,
  direction_id, start_date, start_time and schedule_relationship where present.
- Any producer extensions or additional timing fields supplied in the raw feed.

If periods are broad, missing, or merely describe when to display the alert,
they cannot establish "8:30 pm to last service". A structured affected-service
schedule or resolved affected trips with service dates and terminal stop times
would be needed to establish nightly end times. Trip-only selectors require
separate static schedule resolution before a service-level timing inference.
Stop before implementing any fallback until this evidence is available.

Reference: https://gtfs.org/documentation/realtime/reference/

## Regression fixtures

Tests cover an explicit 20:30–01:00 window, inclusive start/exclusive end,
gaps between nights, Melbourne daylight-saving offsets, broad multi-day and
missing intervals with identical prose, and protobuf field retention. These
tests characterize structured timing behaviour. Additional notice tests cover
priority, planned-only status, bounded attributes, failures and recovery.
