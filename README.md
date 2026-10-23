# Journey Ready

Calendar travel planning for Home Assistant, with traffic, work trains, York Park & Ride, weather, fuel costs and departure reminders.

**Initial implementation. Real provider accounts, routes and Echo responses still need commissioning.**

## Features

- Check today and tomorrow's calendars for office days and appointments.
- Compare work trains with driving to allowed Park & Ride sites. Work driving never ends at a central York car park.
- Prefer driving on clear roads or with persistent rain. Use the car for other appointments.
- Include walking, parking, boarding, safety margins and collecting the car after work.
- Compare estimated return fuel/ticket costs and existing passes.
- Send a morning summary, hour/fifteen-minute reminders, material changes, and route loss/recovery.
- Ask whether the car is needed after work using phone Yes/No and optional home-only Alexa fallback.
- Open Waze at the driving destination, including the chosen Park & Ride entrance.
- Use fresh phone coordinates when away. Tomorrow's origin remains provisional.

Alexa respects presence and quiet hours. Calculations work without Ollama.

## Install and set up

Requires Home Assistant 2026.9.4+, selected calendars, a Companion App phone/person and a TomTom routing/geocoding key.

A published HACS release needs the asset journey_ready.zip. Until a release is published, use a reviewed archive or copy custom_components/journey_ready into your Home Assistant configuration's custom_components directory.

After publication:

1. Add https://github.com/aidanbha79/ha-journey-ready to HACS as a custom repository, category **Integration**.
2. Download it and restart Home Assistant.
3. Open **Settings > Devices & services > Add integration > Journey Ready**.
4. Enter postcode, office, key, person, calendars and phone action. Confirm both entrance pins.
5. Open **Configure**, then complete the [commissioning checklist](docs/commissioning.md).

| Options screen | Settings |
|---|---|
| Times and preferences | Arrival/end times, calendar matching, buffers, delay threshold, unanswered default, car availability and quiet hours |
| Provider credentials | Routing, National Rail, TransportAPI and Fuel Finder credentials and budgets |
| Park & Ride | Sites, entrance pins, route/stop, confirmed timetable, walking, last return bus and gate closure |
| Train stations | Direct CRS pair, entrance pins, optional confirmed timetable and last return |
| Fuel, tickets and weather | Economy, diesel source, forecourt radius, fares/passes and rain thresholds |
| Alexa | Announcement target, speaker and installed Alexa Actions question script |
| Appointment destinations | Confirm or replace ambiguous calendar locations |
| Connections | Calendars, person, phone and location freshness |

A full calendar postcode can be resolved automatically when lookup returns one match. Ambiguous locations need a map pin. Cancelled, provider-exposed declined, online-only and non-work all-day events are skipped. An all-day office marker uses configured arrival time.

## Sources and limitations

| Source | Used for |
|---|---|
| TomTom | Traffic-aware road routes, walking and geocoding |
| National Rail JSON LDBWS | Short-horizon live direct trains and actual calling points |
| TransportAPI | Bus boarding-stop predictions, subject to account and stop coverage |
| Open-Meteo | Hourly rain probability at the destination |
| Fuel Finder | Optional authenticated local standard-diesel median/preferred station |
| Configured values | Fares, passes, return limits, bus ride duration and fallback schedules |

Live bus departure does not predict the entire ride. A rail live board cannot provide tomorrow's timetable. Manual estimates are labelled. Missing live data never proves there are no delays.

Fuel Finder follows first-hand consumer documentation because the official portal was inaccessible through the documentation service. Its schema and credentials require a live check. Unsupported/incomplete responses are rejected. Lookup is disabled until enabled in options. Auto price-unit handling follows documented mixed units; explicit pounds/pence overrides exist.

Local median is an indicative area price, not the cheapest pump quotation. Fuel cost uses return miles, 45 UK mpg by default and price per litre, excluding depreciation. Ticket prices are configured, not live quotes.

Check account products and quotas. TransportAPI's small free allowance may not support frequent monitoring. Usage budgets survive reloads. See [provider contracts](docs/providers.md) and [Alexa setup](docs/alexa-setup.md).

## Entities and controls

Sensors expose destination, mode, leave-by, arrival, return cost and readiness, with reasons, warnings, alternatives and source timestamps. Refresh/test buttons are available.

Actions in the journey_ready domain: refresh, test_notification, set_car_required, override_mode, skip_journey, mark_started.

Journey actions accept the obligation ID from sensor attributes, or use the next journey. Leaving home near departure suppresses departure prompts; walking to a station does not mark the final destination reached.

## Development

Linux, Python 3.14.2+:

    python -m pip install -r requirements_test.txt
    python -m pytest -q --timeout=60
    python -m ruff check .
    python -m ruff format --check .
    python tools/build_release.py

Windows portable/selector tests:

    python -m pytest -p no:homeassistant --ignore=tests/ha -q

CI also runs HACS validation and Hassfest. Release workflow creates a draft from an existing version tag after tests pass. Keep credentials and real journey data out of public issues.

[Design](docs/superpowers/specs/2026-10-23-journey-ready-design.md) · [Plan](docs/superpowers/plans/2026-10-23-journey-ready.md)

MIT licensed.
