# Journey Ready Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. Proposed execution: native, in the current session, with no delegated work unless authorised.

**Goal:** Build and commission a HACS custom integration that plans calendar travel, compares work trains with York Park & Ride, and delivers phone and home-only Alexa reminders.

**Architecture:** A Home Assistant coordinator reads obligations and calls isolated provider clients. Pure Python functions construct and rank complete journeys, while persisted state drives reminder timers and correlated phone/Alexa answers. Each source reports coverage and freshness; absent data cannot become an on-time prediction.

**Tech Stack:** Python, Home Assistant supported APIs, aiohttp, pytest, Home Assistant custom-component test fixtures, Ruff, HACS validation and GitHub Actions. The verified owner instance is Home Assistant 2026.9.4, whose source requires Python >=3.14.2. Full integration tests must run on a compatible Linux/Python runtime; Windows Python 3.12 cannot establish HA compatibility.

**Spec:** `docs/superpowers/specs/2026-10-23-journey-ready-design.md` in the repository; the local reviewed source is `outputs/travel-planner-design.md`.

## Global Constraints

- Name `Journey Ready`, domain `journey_ready`, repository `aidanbha79/ha-journey-ready`.
- Target Home Assistant 2026.9.4 initially. Consult source at that tag for APIs introduced after this release.
- Work journeys by car always use York Park & Ride. Never recommend parking in central York.
- Train is an option only for work. Other physical appointments use car.
- Rain throughout the working day selects car plus Park & Ride when feasible. Clear roads favour car.
- Diesel economy defaults to 45 UK imperial mpg. Cost uses 4.54609 litres per UK gallon.
- Notify one hour and fifteen minutes before departure. For rail, departure starts with the walk/access to the station.
- Speak through Alexa only while the configured person is home. Unknown presence suppresses speech.
- Ollama may explain results but must never be required for calculations or notifications.
- Configure through UI flows; no direct edits to Home Assistant `.storage` files.
- Do not publish real calendars, account identifiers, credentials, home coordinates or raw diagnostic payloads to the public repository.
- A release requires automated checks; fully commissioned status additionally requires real provider, phone and Echo checks.

## Review Focus

1. Changed and deleted calendar events must invalidate stale reminders and old question answers. Covered in Tasks 2 and 6.
2. A fresh location timestamp without usable coordinates or with poor accuracy must not silently choose home. Covered in Task 2.
3. A workday decision can be feasible inbound but leave the user unable to retrieve the car after a late appointment. Covered in Tasks 3 and 4.
4. A provider's live-board horizon or missing forecast hours must not be mistaken for complete tomorrow coverage. Covered in Tasks 3 and 5.
5. A delayed phone/Alexa answer can arrive after expiry or from an unrelated question or user. Covered in Task 7.

## File responsibilities and interfaces

All runtime files reside in `custom_components/journey_ready/`.

| File | Responsibility |
|---|---|
| `models.py`, `const.py` | Typed obligations, legs, candidates, evidence, preferences and defaults |
| `calendar.py`, `location.py` | Calendar normalisation, revision handling, origin and car availability |
| `planner.py`, `costs.py` | Journey construction, feasibility, preference ranking and cost |
| `providers/base.py`, `http.py` | Provider protocols, timestamped evidence and bounded transport |
| `providers/tomtom.py`, `rail.py`, `bus.py`, `fuel.py`, `weather.py`, `geocode.py` | Source-specific clients and normalisation |
| `scheduler.py`, `storage.py`, `questions.py` | Persisted reminders, questions and response lifecycle |
| `notifications.py`, `alexa.py` | Phone, persistent notification, Waze and speaker adapters |
| `config_flow.py`, `options.py`, `strings.json`, `translations/en.json` | Typed setup, configuration, credentials and UI text |
| `__init__.py`, `coordinator.py`, `sensor.py`, `button.py`, `services.yaml`, `diagnostics.py` | Home Assistant lifecycle, entities, actions and redacted readiness |
| `manifest.json`, `brand/icon.png` | Integration metadata and branding |

Testing mirrors these boundaries under `tests/`. Store schema examples under `tests/fixtures/`, with a source/date note and synthetic personal fields. Keep package initialisation lightweight enough that pure planner tests do not require bootstrapping Home Assistant.

Shared models are immutable dataclasses. `Obligation` contains `id`, `revision`, `kind`, `destination`, `arrival_by` and `end_at`. `Leg` contains `mode`, endpoints, scheduled/expected times, distance and `Evidence`. `Candidate` contains complete outward/return legs, leave time, arrival time, effective return cost and feasibility reasons. `Preferences` holds the exact editable defaults from the spec. `Recommendation` contains the selected candidate, alternatives, reasons, readiness and obligations' revisions. `Evidence` records source, observation time, coverage window and live/timetable/manual/stale/unknown classification. `RuntimeState` serialises sent reminder keys, pending question and overrides by entry/obligation/date.

## Task 1: Define the tested journey model and return costs

**Files:** models, costs, constants, package initialisation; `tests/test_costs.py`, `tests/test_models.py`; test dependency and lint configuration; minimal manifest/HACS metadata required by tests.

**Consumes:** approved spec. **Produces:** shared models above and `fuel_cost(miles: Decimal, mpg: Decimal, pounds_per_litre: Decimal, gallon: str) -> Decimal`; `effective_fare(ticket: Ticket, date: date) -> Decimal`.

- [ ] Write failing tests: `test_imperial_return_cost` asserts 90 return miles at 45 mpg and GBP 1.50/litre costs GBP 13.63827 before display rounding; `test_zero_mpg_rejected`; `test_pence_converted_once`; `test_existing_pass_has_no_new_ticket_charge`; `test_unknown_price_is_not_zero`.
- [ ] Run `python -m pytest tests/test_costs.py tests/test_models.py -q` and confirm failures originate in the absent behaviour.
- [ ] Implement dataclasses and Decimal cost calculations. Use separate outward/return road distances and preserve unknown cost as unknown. Round only displayed money.
- [ ] Run the same command and Ruff for changed files; require success. Commit the independently working model/cost unit.

## Task 2: Normalise calendars, destinations and origin

**Files:** calendar, location, geocode client; `tests/test_calendar.py`, `tests/test_location.py`, `tests/test_geocode.py`.

**Consumes:** `Obligation`, `Evidence`, `Preferences`. **Produces:** `normalise_events(events: list[CalendarRecord], settings: CalendarSettings, now: datetime) -> list[Obligation]`; `resolve_origin(state: LocationState, settings: OriginSettings, now: datetime) -> OriginResult`; `Geocoder.async_resolve(query: str) -> list[Place]`.

- [ ] Add failing tests for all-day office markers, non-work all-day events, known virtual locations, provider-exposed cancelled/declined status, duplicate calendars, and revision/deletion invalidation. Assert a 09:00 local event remains 09:00 on both sides of Europe/London DST changes.
- [ ] Add `test_location_requires_coordinates`, `test_location_age_11_minutes_is_stale`, `test_accuracy_201_metres_rejected`, and `test_tomorrow_away_origin_is_provisional_home`. Missing location requests confirmation and never fabricates an address.
- [ ] Run the three test modules and verify expected failures.
- [ ] Implement native calendar range retrieval and pure normalisation. Use exact matching rules and explicit exclusion lists. Geocode postcodes/addresses using a verified documented provider endpoint, retain multiple matches, and require UI coordinate confirmation. No unverified scraped geocoding.
- [ ] Pass the same tests and commit. Test denied geocoding access and malformed coordinates without recording raw addresses in logs.

## Task 3: Establish provider contracts and road/transit clients

**Files:** providers base, HTTP, TomTom, rail, bus; `docs/providers.md`; `tests/test_http.py`, `tests/test_road_provider.py`, `tests/test_rail_provider.py`, `tests/test_bus_provider.py`; redacted schema fixtures.

**Consumes:** shared models and a Home Assistant aiohttp session. **Produces:** `RoadProvider.async_route(origin: Place, destination: Place, departure: datetime) -> RoadRoute`; `RailProvider.async_services(origin_crs: str, destination_crs: str, start: datetime, end: datetime) -> list[TransitService]`; `BusProvider.async_services(site: ParkRideSite, start: datetime, end: datetime) -> list[TransitService]`.

- [ ] Record source documentation, authentication, quota and response schemas before implementing each endpoint. Road provider is TomTom. Rail live status uses licensed National Rail Darwin JSON; future timetables and direct rail/bus journey details use TransportAPI only where the chosen account's products and coverage are verified. Document credentials separately and estimate request volume against the actual allowance. Do not invent an endpoint or treat its free quota as sufficient for continuous polling.
- [ ] Add failing fixture tests asserting traffic duration includes delay once; future routes carry forecast classification; cancelled trains cannot be candidates; direct trains must call at the destination; live-board windows cannot establish tomorrow schedules; SIRI vehicle positions alone cannot become bus arrival predictions; return bus/site closure can invalidate a journey.
- [ ] Add HTTP tests for 401, 403, 429 with Retry-After, timeout, invalid JSON, missing fields and partial source failure. Verify one source failure does not erase successful sources.
- [ ] Run `python -m pytest tests/test_http.py tests/test_road_provider.py tests/test_rail_provider.py tests/test_bus_provider.py -q`; confirm relevant failures, then implement the clients and typed error classes. Use bounded requests, caching, a per-provider budget and no logged credential URLs.
- [ ] Pass the modules and commit. Sources whose account docs or coverage are inaccessible must return an explicit unsupported/readiness status, with a precise commissioning step, and cannot be represented as completed live functionality.

## Task 4: Build and rank complete work and appointment journeys

**Files:** planner and routing model additions; `tests/test_planner.py`.

**Consumes:** Tasks 1-3; weather classification from Task 5 can initially be supplied as a typed input. **Produces:** `build_candidates(obligation: Obligation, origin: OriginResult, services: ProviderSnapshot, preferences: Preferences) -> list[Candidate]`; `recommend(candidates: list[Candidate], context: DecisionContext) -> Recommendation`.

- [ ] Add failing tests for clear roads choosing car, persistent rain choosing feasible Park & Ride, required car excluding rail, road delay over 10 minutes enabling train comparison, ordinary appointments excluding rail, and never selecting central York parking for work.
- [ ] Assert a 09:00 arrival includes walking, parking, waiting, boarding and the 10-minute safety margin exactly once. Reject impossible connections, incompatible car availability, closed sites and a missed last return bus. Prefer shorter door-to-door duration then known effective cost when road preference no longer applies; unknown cost does not mean free.
- [ ] Run `python -m pytest tests/test_planner.py -q` and verify failures, implement backward selection from service times and the deterministic precedence rules, then rerun to pass.
- [ ] Add tests that mode stays stable near departure unless infeasible or manually changed, and that a sequential appointment starts from the previous confirmed destination. Commit.

## Task 5: Fuel, fares and destination weather

**Files:** fuel and weather providers, fare options; `tests/test_fuel_provider.py`, `tests/test_weather.py`, fixture/schema documentation.

**Consumes:** `Evidence`, cost interfaces and candidate endpoints. **Produces:** `FuelProvider.async_price(origin: Place, selection: FuelSelection) -> FuelQuote`; `classify_rain(hours: list[ForecastHour], window: TimeWindow, settings: RainSettings) -> RainResult`; `WeatherProvider.async_forecast(place: Place, window: TimeWindow) -> list[ForecastHour]`.

- [ ] Obtain Fuel Finder's actual OAuth/client and data specification from its official developer access. Record timestamps, units and pagination in provider docs. Add failing tests for token renewal, selecting diesel only, stale prices, station radius, preferred station, manual fallback, and prices expressed in pence per litre.
- [ ] Add weather tests for at least 75% wet intervals at probability >=60%, less than 80% forecast coverage yielding unknown, and destination forecast differing from home. Validate hourly forecast fields against the configured provider; do not assume a home weather entity forecasts York.
- [ ] Run `python -m pytest tests/test_fuel_provider.py tests/test_weather.py -q`, implement verified provider contracts and configurable manual fare/pass inputs, and rerun to pass.
- [ ] Check that GBP 4 Park & Ride return is an editable initial published value with source date, and rail pricing never comes from Darwin. Commit. If official API access is not supplied, live fuel stays unavailable and the explicitly labelled manual price remains usable.

## Task 6: Persist and reconcile reminders

**Files:** scheduler, storage; `tests/test_scheduler.py`, `tests/test_storage.py`.

**Consumes:** `Recommendation`, `RuntimeState`, injected UTC clock. **Produces:** `reconcile(state: RuntimeState, recommendations: list[Recommendation], now: datetime) -> ScheduleDelta`; `JourneyStore.async_load() -> RuntimeState`; `JourneyStore.async_save(state: RuntimeState) -> None`.

- [ ] Write failures asserting leave-at-10:00 produces 09:00 and 09:45 reminders, changed departure cancels the old timer, a crossed threshold sends one immediate reminder, restart preserves sent keys, and removed/revised obligations invalidate old work.
- [ ] Assert starting to walk to a station suppresses the walk reminder but does not mark the whole work journey completed. Test new appointments inside the one-hour window, late departure, DST, significant worsening, and duplicate update suppression.
- [ ] Run `python -m pytest tests/test_scheduler.py tests/test_storage.py -q`; implement pure reconciliation and Home Assistant Store serialisation/versioning, then pass the tests.
- [ ] Bind deltas to cancellable Home Assistant timers, perform startup reconciliation before sending, and register cleanup on unload. Test unloading removes all callbacks. Commit.

## Task 7: Phone notifications, Waze and Alexa questions

**Files:** notifications, Alexa and questions; `tests/test_notifications.py`, `tests/test_questions.py`, `tests/test_alexa.py`; public Alexa commissioning guide.

**Consumes:** recommendations, schedule events and current presence. **Produces:** `NotificationAdapter.async_send(plan: Recommendation, stage: str) -> None`; `QuestionManager.async_ask(work_date: date) -> PendingQuestion`; `QuestionManager.accept(response: Response, now: datetime) -> AnswerResult`; `AlexaAdapter.async_announce(text: str) -> DeliveryResult`; `AlexaAdapter.async_ask(question: PendingQuestion) -> DeliveryResult`.

- [ ] Write failing tests for valid encoded Waze coordinates, work driving link ending at Park & Ride, rail text indicating walk-to-station, stable persistent-notification IDs and phone replacement tags. Use separate per-question action IDs and match the expected user's registered device.
- [ ] Write failing tests for phone answer cancelling Alexa fallback, expired/foreign responses rejected, duplicate phone/voice answers resolved once, unknown presence suppressing speech, leaving home during the fallback delay, and timeout using the stated car-required default without pretending an answer was received.
- [ ] Run `python -m pytest tests/test_notifications.py tests/test_questions.py tests/test_alexa.py -q`; implement Companion events and the verified upstream Alexa Actions helper/event contract. Support native Alexa notify entities for announcements independently. Generic spoken history must not stand in for a correlated answer.
- [ ] Pass the tests and commit. Document Amazon login, private skill and external HTTPS prerequisites. Keep the planner ready for phone use while exposing unavailable voice questions clearly.

## Task 8: Home Assistant setup, coordinator and controls

**Files:** config/options flows, strings/translations, init, coordinator, sensor, button, services, diagnostics; `tests/test_config_flow.py`, `tests/test_coordinator.py`, `tests/test_lifecycle.py`, `tests/test_diagnostics.py`.

**Consumes:** Tasks 1-7. **Produces:** config-entry setup/unload, typed runtime data, UI flows, public entities and actions described in the spec.

- [ ] On compatible Linux/Python, write failing Home Assistant fixture tests for required inputs and coordinate confirmation, invalid credentials, unsupported station pair, config entry uniqueness, option changes, provider reauthentication and missing optional Alexa/Ollama.
- [ ] Add tests for the 06:00/19:00 checks, today/tomorrow ranges, event updates, 5-minute/2-minute bounded monitoring, slow fuel refresh and provider budget exhaustion. Unavailable sources preserve readiness explanations and do not produce plausible-looking fake values.
- [ ] Run `python -m pytest tests/test_config_flow.py tests/test_coordinator.py tests/test_lifecycle.py tests/test_diagnostics.py -q`; implement native selectors and setup with credentials in config entries, mutable settings in options, and registration cleanup. Do not block core setup merely because an optional provider is down.
- [ ] Expose destination, mode, leave-by, arrival, return cost and readiness; refresh/test buttons and skip/car/mode controls scoped to an obligation/date. Diagnostics must redact credentials, external Home Assistant URLs, exact locations, calendar descriptions and phone identifiers. Assert those fields do not appear in serialised output.
- [ ] Pass all tests on Home Assistant 2026.9.4 with Python >=3.14.2 and commit. Windows pure-function results are supplementary and never labelled full HA validation.

## Task 9: Packaging, CI and release preparation

**Files:** `.github/workflows/validate.yml`, `.github/workflows/release.yml`, README, HACS metadata, manifest/brand, changelog, commissioning docs and `tests/test_packaging.py`.

**Consumes:** working integration and tests. **Produces:** validated repository and installable versioned archive without secrets.

- [ ] Add packaging tests for one custom-component directory, manifest domain/version/owner/documentation/issue URLs, translations, actual icon image and archive layout. Run the test before adding missing metadata/assets and verify failure.
- [ ] Implement metadata and a simple code-rendered brand icon. Add CI for Ruff, full tests on compatible Linux, HACS validation and Hassfest. Pin third-party workflow actions to reviewed immutable commits, use read-only permissions for validation, and grant contents-write only to the tag release job.
- [ ] Run `python -m pytest -q`, `python -m ruff check .`, `python -m ruff format --check .`, package tests and CI validators. Review the actual diff against the spec and ensure docs distinguish implemented, unavailable and uncommissioned features.
- [ ] Push the tested implementation to a feature branch and open a PR against the documentation baseline. Attach the PR to this chat. Avoid claiming a test passed until its output exists.
- [ ] After checks and authorised integration, create a versioned release with changelog and archive. Verify a HACS custom-repository install from that published artifact, then mark packaging complete. No release from the current docs-only repository.

## Task 10: Owner commissioning and live acceptance

**Files:** commissioning checklist and a redacted local acceptance record. No public record of real destinations or credentials.

**Consumes:** published artifact and owner-supplied setup inputs. **Produces:** an honestly reported operational status for each enabled feature.

- [ ] Ask for missing postcode, confirmed office entrance, arrival/end time, rail stations, calendar matching, enabled Park & Ride sites, provider credentials and ticket/pass settings through the appropriate setup screens. Read existing entity selections but do not infer a private address from unrelated configuration.
- [ ] Connect Alexa Media Player in Home Assistant using owner-driven Amazon login/MFA; verify a real Echo announcement. Configure/authorise the private Alexa Actions skill and confirm correlated Yes and No events. Test away and unknown presence suppression.
- [ ] Verify the phone's Yes/No buttons, Waze launch to the intended site, current-location freshness, real traffic, actual train/bus coverage, destination forecast, local diesel quote and fare settings. Confirm return access after work.
- [ ] Run one clearly labelled dry-run workday with controlled reminder timing. Then restore configured real reminder offsets and verify the resulting schedule.
- [ ] Record pass/fail/unavailable per feature. Fully set up requires every enabled path to pass; disclose any remaining account, quota, feed, credential or skill blocker specifically. Fix and rerun only affected checks.

## Execution checkpoints

The written spec is accepted by the owner's instruction to proceed with the repository and build. This written implementation plan is prepared for review before code, as required by the active planning workflow. Recommend native execution because all tasks share models and lifecycle state, and the owner has not requested delegated agents.

Complete Tasks 1-8 as successive tested units, then packaging and live commissioning. Provider/account access may delay particular live adapters but does not prevent independent model, scheduling, notification and UI work. A disabled/unverified adapter is a visible limitation, not completion of its feature.

No product code, runtime dependencies or Home Assistant configuration changes are part of publishing this plan.
