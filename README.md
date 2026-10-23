# Journey Ready

Calendar-based travel planning for Home Assistant, with traffic, trains, York Park & Ride, weather and departure reminders.

**Status: design and implementation planning. There is no installable integration or release yet.**

Journey Ready will check selected calendars for office days and appointments, calculate when to leave, and send reminders through the Home Assistant Companion App. Driving directions will open in Waze. Optional Alexa announcements and Yes/No questions will run only when the configured person is home.

For work journeys, driving always uses Park & Ride. The planner will compare complete return journeys, account for train and bus disruption, and apply configurable preferences for rain, road delays, cost and needing the car after work. Other appointments will use driving routes.

## Design and build plan

- [Design](docs/superpowers/specs/2026-10-23-journey-ready-design.md)
- [Implementation plan](docs/superpowers/plans/2026-10-23-journey-ready.md)
- [Alexa setup](docs/alexa-setup.md)

The planned integration name is **Journey Ready**, with domain `journey_ready`. Initial compatibility will be checked against Home Assistant 2026.9.4.

## External services

Traffic, rail, bus and fuel data require suitable provider access. Some accounts have paid products or request limits. Live predictions and timetable estimates will be distinguished in the UI. Ticket prices and existing passes can be configured where a verified live fare source is unavailable.

Alexa announcements and spoken answers have separate prerequisites. Amazon account authentication and skill authorisation must be completed by the account owner. Ollama will be optional.

## Installation

Installation instructions and HACS metadata will accompany the first tested release. Adding this documentation-only repository to HACS will not install a working integration.
