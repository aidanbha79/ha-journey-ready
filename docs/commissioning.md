# Commissioning

Automated tests and a proven real commute are separate. Keep actual locations and credentials in Home Assistant.

## Configure

1. Set postcode/office and confirm entrance pins.
2. Choose the phone-linked person, phone action and authoritative calendars without duplicate copies.
3. Set arrival/end times, office marker, summary/question times, buffers and unanswered default.
4. Confirm car availability and allowed Park & Ride sites.
5. Verify each entrance, bus route/stop, timetable, ride/walking time, service day, last return and gate closure.
6. For trains, verify the direct station pair/pins, walking and last return. Use JSON-service credentials. Manual schedules remain provisional.
7. Set ticket/pass costs, diesel fallback and gallon definition.

## Verify sources

Compare road time/traffic with a known journey. Check train calls/cancellations and bus direction/line against real departures. Confirm destination forecast coverage.

For Fuel Finder, register consumer credentials, enter them in provider settings, select the account's token format and enable lookup. First scan may take minutes. Compare local price and units against current forecourt information.

Verify fares and each account's request allowance.

## Verify notifications

Use the test button. Test phone Yes/No and ensure only the intended work date changes. Another user's answer must be rejected.

Open Waze and check the driving entrance. Work driving must end at Park & Ride.

Check Companion background location. Stale/inaccurate/unknown tracking must not silently become home. Confirm ambiguous destinations in options.

Follow [Alexa setup](alexa-setup.md). Test a real announcement and spoken Yes/No with matching question event IDs. Home permits speech; away/unknown suppresses it. Quiet hours defer morning voice without repeating the phone summary. Phone answers prevent fallback. Silence uses the configured default.

## Dry run

Use labelled test appointments and controlled timings for hour/fifteen-minute reminders. Change/delete an event, lose/restore route data and restart the integration. Confirm no stale/duplicate prompts and that the car can be collected within return/site limits.

Record enabled features as passed, failed or unavailable. Fully set up means every enabled live path has passed.
