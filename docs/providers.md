# Provider contracts

The shared asynchronous HTTP client bounds request time/response size, caches data, hides credential-bearing URLs and honours Retry-After. Persisted request budgets are user limits, not claims about provider allowances.

## Road

[TomTom Routing](https://docs.tomtom.com/routing-api/documentation/tomtom-maps/v1/calculate-route) and [geocoding](https://docs.tomtom.com/geocoding-api/documentation/tomtom-maps/v1/geocode).

Travel time already includes delay. Recalculate using estimated departure; future results are forecasts. Waze may choose a different route. Setup confirms entrance pins; calendar auto-lookup requires a full UK postcode and one match.

## Rail and bus

[National Rail access](https://www.nationalrail.co.uk/developers/), [JSON docs](https://realtime.nationalrail.co.uk/LDBWS/docs/documentation.html), [schema](https://realtime.nationalrail.co.uk/LDBWS/static/ldbws.json), [TransportAPI](https://developer.transportapi.com/).

Rail uses the 20220120 JSON GetDepBoardWithDetails operation and licensed Basic Auth credentials. Do not assume SOAP tokens are interchangeable. Destination calling points must exist; stale boards, cancellations and unknown delay clocks are rejected. Direct trains only. Tomorrow requires a confirmed fallback schedule outside the live-board horizon.

Bus uses TransportAPI v3 stop departures with ATCO boarding-stop and route filtering. GPS is never converted to an arrival prediction. Ride duration, walks, service days, last return and closure are configured. A board overrides only the scheduled departures it reports. Explicit cancellations and unusable predictions block matching manual departures. An empty board does not establish coverage of later services, which remain labelled timetable estimates.

Confirmed return departure times are required to plan collecting a parked car before an onward appointment. Collection must finish before gate closure and use a bus no later than the configured last return. Without return times, work return availability is only an estimate based on the configured limits and ride duration.

## Weather

[Open-Meteo](https://open-meteo.com/en/docs) hourly destination precipitation probability, in UTC.

Initial persistent-rain settings: 60% probability, 75% wet hours, 80% coverage. These are editable preferences. Missing coverage yields unknown.

## Fuel

[Official access](https://www.gov.uk/guidance/access-the-latest-fuel-prices-and-forecourt-data-via-api-or-email), [UK-Fuel-Finder first-hand contract](https://github.com/philmale/UK-Fuel-Finder/blob/main/uff_api.md), [FuelHunter implementation notes](https://fuelhunter.co.uk/developers).

The official portal was inaccessible through the documentation service. Authenticate and verify the supported consumer schema before relying on the adapter.

Tokens stay in memory. Form/JSON token formats are selectable. Sequential pages continue to 404; an early empty page is retried then rejected. A bounded scan runs in the background and never replaces a quote with incomplete data.

Select standard diesel, exclude closed/distant stations, and choose a preferred forecourt or local median. Auto units follow the documented mixed-unit convention; overrides exist. Implausible values are discarded.

Price-change time and feed-check time differ. A held price is not automatically stale. Quotes refresh after three hours and expire after six. Failed scans retry no more often than every 30 minutes. Fresh fuel sensors and labelled manual prices remain fallbacks.

Fixtures are synthetic. No real feed, credentials or exact home coordinates are committed.

## Fares

Verify the initially researched GBP 4 return against [York fares](https://www.itravelyork.info/park-ride/fares-passes-3). Fares and passes are configured; live train ticket pricing is not implemented. Unknown cost is not free.
