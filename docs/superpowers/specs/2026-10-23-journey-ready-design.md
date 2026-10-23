# Journey Ready: design

Date: 23 October 2026
Status: design accepted for implementation planning. No custom integration has been built or deployed.

## Purpose

Build a Home Assistant custom integration, distributed through a HACS-compatible repository, that reads selected calendars, recognises office days and appointments, compares appropriate journeys, and sends departure reminders. Configuration belongs in the Home Assistant UI. The initial use case is travel to an office in York, Waze navigation, and a diesel car averaging 45 UK imperial mpg.

## Confirmed requirements

- Configure home postcode, office destination, required office arrival time, local rail station, calendars and office-event matching rules.
- Check today and tomorrow. Appointments with a usable physical location use car travel. Train is an option only for work.
- Work journeys by car always use York Park & Ride. Never recommend parking in central York.
- Rain throughout the working day selects car plus Park & Ride when feasible. Clear roads favour car. Train is an alternative when road delays make driving less suitable.
- Ask the previous day whether the car is needed after work. Yes restricts the work journey to car plus Park & Ride. It does not permit central York parking.
- Compare return diesel and Park & Ride costs against return rail costs.
- Notify one hour and fifteen minutes before departure. For train travel, departure means leaving the origin to walk to the station.
- Recheck conditions and reschedule reminders as departure time changes.
- Driving notifications include a Waze link to the actual driving destination, including the selected Park & Ride site for work.
- Announce the morning plan and fifteen-minute reminder through Alexa only while the configured person is home.
- If the evening phone question is unanswered, ask through Alexa only while home.
- When away, use a sufficiently fresh phone location for immediate journey planning. Tomorrow's plan is provisional and uses the configured home origin; re-evaluate using actual location on the travel day.
- Ollama may explain results but must never be required for calculations or notifications.

## Architecture

Use one Python custom integration with a config flow and options flow, an asynchronous coordinator, separate provider clients, a pure journey-selection module, persisted reminder state and notification adapters. Avoid a separate daemon or mandatory language model.

Calendar ingestion produces travel obligations with stable identity, revision, destination, required arrival time and work/appointment type. Provider clients produce timestamped journey candidates. Selection produces a recommendation with explicit reasons, estimated cost, evidence freshness and uncertainty. Notification code consumes this recommendation and does not calculate routes itself.

Use Home Assistant's supported APIs for calendars, forecasts, location entities, notifications, storage and timers. Network requests use the shared asynchronous HTTP session with bounded timeouts, backoff and provider rate limits. Blocking parsing must not block the event loop. Config unload removes timers and event listeners. No direct edits to Home Assistant `.storage` files.

## Configuration

Required commissioning inputs are home postcode or confirmed map point, office destination and entrance, office arrival/end times, selected calendars, office title/location matching, origin station, destination station, and phone target. These values have not been supplied and must not be invented.

Further UI options:

- Person/location tracker; manual car-availability override; weather source and destination forecast provider.
- Enabled Park & Ride sites, inbound/outbound stops, office walking endpoint, site operating hours and walking/parking/boarding buffers.
- Provider credentials for routing, rail and fuel, stored as credentials and excluded from diagnostics.
- Diesel economy with explicit UK/US gallon selector; default 45 UK mpg. Preferred fuel station or search radius; manual fuel-price fallback.
- Park & Ride fare/pass and rail fare/pass/railcard inputs. Existing passes must not be charged as newly bought tickets each day.
- Morning check 06:00, evening check 19:00, Alexa fallback after 15 minutes, and unanswered-question default of car required. All are proposed editable defaults.
- Safety margin 10 minutes, parking allowance 5 minutes and station boarding allowance 5 minutes. Walking times come from routes or explicit overrides; do not count an allowance twice.
- Road hold-up threshold 10 minutes above the provider's no-traffic estimate. Selection and ETA change notification threshold 5 minutes.
- Rain window defaults to configured work start/end; classify persistent rain when at least 75% of available hourly intervals predict precipitation with probability at least 60%. Require coverage for at least 80% of the window, otherwise report weather unknown. These are editable proposed interpretations of 'raining all day'.
- Alexa announcement backend, selected speaker(s), question backend, skill ID, question helper and allowed response event type. Quiet hours apply to speech; phone reminders continue.

The setup flow validates destinations and lets the user confirm coordinates. A postcode centroid is an estimate, so entrances and Park & Ride vehicle entrances can be refined. Required providers are tested during commissioning. Features with missing credentials remain visibly unavailable rather than appearing operational.

## Calendar and origins

Read date ranges in the configured Home Assistant timezone. Handle all-day office markers using the configured office arrival time. Skip all-day non-work markers, cancelled events and recognised online-only appointments. Declined status can only be respected if the calendar provider exposes it. Exclusion keywords and manual skip controls cover providers that omit attendee status.

Match office events using explicit configured rules before considering AI assistance. Ambiguous or missing locations need user confirmation. Never invent an address. Deduplicate selected calendars by provider identity where available, with a cautious time/destination fallback. Changes or deletions invalidate pending reminders and question identifiers.

Away-origin estimates require location no older than 10 minutes and reported accuracy within 200 metres by default. Request a refresh if supported, with a bounded wait. If it fails, label the origin unconfirmed and offer a manual origin rather than silently using home. Explicitly establish car availability when away. Forecast later consecutive appointments from the preceding confirmed destination; use actual location when their departure approaches. Warn about overlaps and impossible connections.

## Journey construction and choice

Build car work candidates for each enabled Park & Ride: origin to site by road, parking, walk to stop, bus wait/ride, and final walk to the office. Validate the return bus and site closing time against work end and after-work car collection. If no site can support the day, report the conflict. Never substitute central York parking.

Build rail work candidates: walk/access to origin station, boarding buffer, eligible train services and any supported connections, then walk to the office. Verify the return service where needed. Initial rail support is limited to direct station pairs unless a verified journey-planning provider supports connections; reject unsupported configurations explicitly.

Choose only candidates capable of meeting the arrival requirement. Honour explicit car requirements first, then persistent-rain preference, then clear-roads preference. If roads exceed the configured hold-up threshold and car is not required, compare viable options by expected door-to-door duration, then effective return cost. Show both costs even when preference rules choose the dearer option. Preserve a selected mode close to departure unless infeasible or the user changes it, avoiding repeated mode changes. Missing live data is not equivalent to clear roads or an on-time train.

For ordinary appointments, plan driving to the event destination, including configured parking/walking allowances. Infeasible plans must say the appointment cannot be reached by the deadline.

## Providers and cost

- Road routing: TomTom Routing API, using traffic-aware and appropriate departure-time estimates. Future departures require recalculation; a current ETA is not a promise about tomorrow. Use Waze only as the navigation hand-off, without claiming its route must match the ETA provider.
- Rail: National Rail Darwin running information with licensed credentials. It is not a ticket-pricing API or a complete multi-leg journey planner. Use a verified journey service or cached timetable within its supported horizon. Tomorrow's train planning cannot rely solely on a short live-board window.
- Bus: York timetables plus a verified stop-level live prediction source. BODS vehicle positions alone do not establish an arrival prediction. Site/stop identifiers, feed coverage, service calendar, return timetable and closure information must be validated before claiming live support. Scraping is an explicit per-source fallback only where permitted, with cached responses and tested parsers. Unsupported live coverage is labelled timetable estimate.
- Fuel: government Fuel Finder API, authenticated using its documented method; local diesel with station name and price timestamp. Use configured forecourt selection or a robust local representative price, not an unexplained minimum. Manual fallback is visibly labelled.
- Fares: configurable values and pass treatment until machine-readable licensed live fare access is verified. York's published standard Park & Ride return was listed as GBP 4 at research time; it is an initial editable value, not a permanent price guarantee. Rail fares are never inferred from Darwin.
- Weather: hourly destination and relevant origin forecasts through supported sources. Missing forecast coverage cannot establish all-day rain or clear weather.

Return fuel cost in GBP = return road miles / UK mpg * 4.54609 * diesel GBP/litre. Compare actual return routes, not automatically twice the outbound distance. Add effective bus fare. Display fuel and ticket costs separately and label this as running fuel/ticket cost, excluding depreciation unless a user adds a per-mile allowance.

Before release, each provider must have documented access, schema fixtures, rate limits and a successful authenticated commissioning check. A feature lacking these checks remains explicitly unavailable. Provider uncertainty must never be hidden behind an AI response.

## Reminders and state

Persist a per-obligation record of selected journey, calculated departure, sent reminders, pending question, answer expiry and evidence timestamps using Home Assistant storage APIs. Store timestamps in UTC and display local time. Restore and reconcile against the calendar after restart, timezone changes or provider recovery.

During active monitoring refresh every 5 minutes, increasing to every 2 minutes within 90 minutes of departure when provider limits permit. Cache fuel and fares separately on slower schedules. Outside active monitoring refresh calendars at the scheduled checks and supported change events. Avoid scanning every provider all day.

Send at departure minus 60 minutes and minus 15 minutes. If a new departure crosses an unsent reminder threshold, send once immediately. Significant worsening sends an urgent update; the same condition does not repeat on every poll. If departure has passed, say how late the plan is. Start/arrival detection and user acknowledgement suppress reminders after the journey begins or finishes. In train mode, movement to the station is a journey stage, not proof the whole commute has finished.

Phone messages include destination, mode/site or train, leave-by time, expected arrival, cost, main reason and uncertainty. Driving includes an Open Waze action with encoded confirmed destination coordinates. Preserve an internal persistent notification as the current plan. Phone notification replacement and reminder deduplication use stable identifiers.

## Alexa

Support announcements independently of questions. Native Alexa Devices Speak/Announce notify entities can provide announcements. Alexa Media Player can provide announcements and launch a compatible actionable-notifications skill.

Recommended question path for this installation: configure the already downloaded Alexa Media Player, then use a separate Alexa Actionable Notifications skill following the upstream setup. Amazon authentication, account linking/developer-console setup and Echo discovery require the account owner. Do not embed Amazon passwords in the travel integration. A fresh login or app-based MFA may be required.

Use the documented Alexa Actions input-text payload and response event contract through a dedicated adapter; verify the installed skill's actual contract before enabling it. Correlate each answer to integration entry, user, work date and pending question. First valid answer wins. Reject expired or unrelated responses. Do not interpret arbitrary Alexa command-history text as a response.

Immediately before every spoken question or announcement, require the configured person to be `home`, the speaker to be available, and quiet hours to allow speech. Unknown presence suppresses speech. If the person leaves during the fallback delay, cancel speech. Phone answer cancels the pending Alexa question. If the person returns during the valid evening window, permit one deferred question, avoiding repeated prompts.

The new integration exposes all selectors and a connection-test screen, but does not silently install external skills or complete Amazon login. Home Assistant Cloud being loaded does not itself prove the custom skill can reach the instance.

## Entities and controls

Expose next destination, recommended mode, leave-by timestamp, expected-arrival timestamp, estimated return cost and readiness status. Details include reasons, alternative summaries and provider freshness without secrets or raw calendar descriptions. Add refresh-now and test-notification controls, per-day car-required override, skip-journey action and temporary mode override. Missing providers produce repair/readiness information, not fabricated sensor values.

## Verification and commissioning

Automated tests must cover calendar date boundaries and daylight saving changes, route buffers, rain precedence, road-delay preference, diesel units, pass costs, missing/stale providers, impossible journeys, and forbidden central York parking. Test reminder rescheduling, restarts, duplicate answers, cancellation, away presence and location freshness with an injected clock.

Test adapters against recorded redacted real schema fixtures and provider error responses. Validate config/options flow, integration setup/unload and HACS packaging against the selected Home Assistant release. Do not claim mocks establish live service compatibility.

Live commissioning must confirm: authoritative calendars, confirmed destinations/stations/stops, actual route timings, provider credentials, fare accuracy, iPhone Yes and No actions, Waze launch to the selected site, Alexa announcement, Alexa Yes and No response, timeout, presence suppression, and one representative dry-run commute. Test notifications must identify themselves as tests. Only mark fully set up once all enabled features have passed these checks.

## Delivery and remaining owner inputs

Deliver source, meaningful tests, installation instructions, HACS metadata and a release archive. A real repository URL and release are needed before HACS can install the new integration from a custom repository. Existing configuration APIs do not by themselves provide general custom-component filesystem deployment.

Owner commissioning steps include Amazon sign-in, skill authorisation, API account/credential setup, destination/station/time values and authoritative calendar selections. These are setup inputs, not reasons to invent defaults. The build can proceed after design and implementation-plan review; activation waits for valid inputs and live checks.

## Sources

- Alexa Devices: https://www.home-assistant.io/integrations/alexa_devices/
- Alexa Media Player configuration: https://github.com/alandtse/alexa_media_player/wiki/Configuration
- Alexa Actions prerequisites: https://github.com/keatontaylor/alexa-actions/wiki/Prerequisites
- Alexa Actions skill setup: https://github.com/keatontaylor/alexa-actions/wiki/Alexa-Talking-to-Home-Assistant-(The-Skill)
- Companion phone actions: https://companion.home-assistant.io/docs/notifications/actionable-notifications/
- Companion location: https://companion.home-assistant.io/docs/core/location/
- Waze navigation links: https://developers.google.com/waze/deeplinks/
- York fares: https://www.itravelyork.info/park-ride/fares-passes-3
- York timetables: https://www.itravelyork.info/park-ride/timetables-1
- National Rail data: https://www.nationalrail.co.uk/developers/
- Fuel Finder: https://www.gov.uk/guidance/access-the-latest-fuel-prices-and-forecourt-data-via-api-or-email
- TomTom routing: https://docs.tomtom.com/routing-api/documentation/tomtom-maps/v1/calculate-route
