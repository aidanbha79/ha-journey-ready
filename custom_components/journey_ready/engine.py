"""Coordinate providers into complete, explicitly qualified journeys."""

import re
from dataclasses import replace
from datetime import datetime, time, timedelta
from decimal import Decimal

from .costs import effective_fare, fuel_cost
from .models import Candidate, DecisionContext, Evidence, Place, Recommendation, TransitService
from .planner import park_ride_candidate, rail_candidate, recommend
from .providers.base import CoverageError, ProviderError
from .providers.weather import classify_rain
from .vehicle import started_commute


def place_from(data):
    return Place(data.get("name", "Destination"), float(data["latitude"]), float(data["longitude"]))


def at(clock, day):
    return datetime.combine(day.date(), time.fromisoformat(clock), day.tzinfo)


def timetable(times, day, minutes, source):
    result = []
    for raw in str(times).split(","):
        if not raw.strip():
            continue
        departure = at(raw.strip(), day)
        result.append(
            TransitService(
                f"{source}:{departure.isoformat()}",
                departure,
                departure + timedelta(minutes=minutes),
                Evidence(source, day, "manual", day + timedelta(days=2)),
            )
        )
    return result


class Engine:
    def __init__(self, settings, road, *, rail=None, bus=None, weather=None):
        self.settings, self.road = settings, road
        self.rail, self.bus, self.weather = rail, bus, weather
        self.resolved = {}

    async def plan(self, obligations, origin, now, state):
        plans = []
        previous = None
        home = (
            place_from(self.settings["home_location"])
            if self.settings.get("home_location")
            else origin
        )
        for trip in sorted(obligations, key=lambda item: item.arrival_by):
            warnings, candidates = [], []
            if self.settings.get("_fuel_source"):
                warnings.append(self.settings["_fuel_source"])
            start = home if trip.arrival_by.date() > now.date() else origin
            if trip.arrival_by.date() > now.date():
                warnings.append("Tomorrow's home origin and travel times are provisional")
            if (
                previous
                and previous[0].end_at.date() == trip.arrival_by.date()
                and previous[0].end_at > now
            ):
                start = previous[1]
            destination = await self._destination(trip)
            if not destination:
                plans.append(
                    Recommendation(
                        trip,
                        None,
                        warnings=("Confirm the appointment address in Journey Ready options",),
                    )
                )
                continue
            if start is None:
                plans.append(
                    Recommendation(
                        trip,
                        None,
                        warnings=("Refresh your phone location or set a confirmed origin",),
                    )
                )
                continue
            rain = None
            if trip.kind == "work" and self.weather:
                try:
                    hours = await self.weather.forecast(destination)
                    rain = classify_rain(
                        hours,
                        trip.arrival_by,
                        trip.end_at,
                        probability=self.settings.get("rain_probability", 60),
                        fraction=self.settings.get("rain_fraction", 75),
                        coverage=self.settings.get("rain_coverage", 80),
                    )
                except (ProviderError, ValueError, TypeError):
                    warnings.append("Destination weather unavailable")
                if rain is None:
                    warnings.append("Weather coverage is insufficient to assess persistent rain")
            try:
                if trip.kind == "work":
                    candidates += await self._park_ride(trip, start, now, warnings)
                    if self.settings.get("rail_enabled"):
                        candidates += await self._rail(trip, start, destination, now, warnings)
                else:
                    if (
                        previous
                        and previous[0].end_at.date() == trip.arrival_by.date()
                        and previous[0].kind == "work"
                        and not (previous[0].end_at <= now and origin == home)
                    ):
                        candidates += await self._onward_car(
                            trip, previous, destination, now, warnings, origin=origin
                        )
                    else:
                        candidates.append(await self._car(trip, start, destination, now))
            except (ProviderError, ValueError, TypeError, KeyError):
                warnings.append(
                    "Journey data unavailable; check provider access and route settings"
                )
            if previous and previous[0].end_at.date() == trip.arrival_by.date():
                candidates = [
                    replace(c, feasible=False) if c.leave_at < previous[0].end_at else c
                    for c in candidates
                ]
            question = state.questions.get(trip.arrival_by.date().isoformat(), {})
            car_required = question.get("answer")
            if car_required is None:
                car_required = self.settings.get("car_required_default", True)
                if trip.kind == "work":
                    warnings.append("No car-after-work answer; using your configured default")
            override = state.overrides.get(trip.id, "auto")
            if override in ("car", "park_ride", "train"):
                candidates = [c for c in candidates if c.mode == override]
            previous_selection = state.overrides.get("_selected", {}).get(trip.id, {})
            lock = False
            if previous_selection.get("leave_at"):
                lock = now >= datetime.fromisoformat(previous_selection["leave_at"]) - timedelta(
                    minutes=15
                )
            context = DecisionContext(
                trip.kind,
                bool(car_required),
                rain,
                self.settings.get("road_delay_minutes", 10),
                self.settings.get("car_available", True),
                previous_selection.get("mode"),
                lock,
            )
            result = recommend(trip, candidates, context)
            if any(c.arrive_at > trip.arrival_by for c in candidates):
                warnings.append(
                    "Some routes miss the arrival deadline; check achievable arrival times"
                )
            if not candidates and trip.kind == "work" and not self.settings.get("park_ride_sites"):
                warnings.append("Configure at least one Park & Ride site")
            plans.append(replace(result, warnings=tuple(dict.fromkeys(warnings))))
            previous = (trip, destination, started_commute(state, trip) or result.selected)
        return plans

    async def _destination(self, trip):
        if trip.kind == "work":
            return place_from(self.settings["office_location"])
        saved = self.settings.get("destinations", {}).get(trip.destination)
        if saved:
            return place_from(saved)
        if trip.destination in self.resolved:
            return self.resolved[trip.destination]
        if not re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", trip.destination, re.IGNORECASE):
            return None
        try:
            matches = await self.road.geocode(trip.destination)
        except ProviderError:
            return None
        if len(matches) == 1:
            self.resolved[trip.destination] = matches[0]
            return matches[0]
        return None

    def _cost(self, metres, fare):
        price = self.settings.get("effective_diesel", self.settings.get("diesel_price"))
        price = price if price and float(price) > 0 else None
        fuel = fuel_cost(
            Decimal(str(metres)) / Decimal("1609.344"),
            self.settings.get("mpg", 45),
            price,
            self.settings.get("gallon", "UK"),
        )
        return fuel + fare if fuel is not None and fare is not None else None

    async def _car(self, trip, origin, destination, now, *, earliest=None):
        safety = self.settings.get("safety_minutes", 10)
        parking = self.settings.get("appointment_parking", 5)
        walk = self.settings.get("appointment_walk", 0)
        ready = max(now, earliest or now)
        guess = max(ready, trip.arrival_by - timedelta(hours=1))
        road = await self.road.route(origin, destination, guess, now=now)
        leave = trip.arrival_by - timedelta(seconds=road.seconds, minutes=safety + parking + walk)
        road = await self.road.route(origin, destination, max(leave, ready), now=now)
        leave = trip.arrival_by - timedelta(seconds=road.seconds, minutes=safety + parking + walk)
        back = await self.road.route(destination, origin, max(trip.end_at, now), now=now)
        return Candidate(
            "car",
            leave,
            max(leave, ready) + timedelta(seconds=road.seconds, minutes=parking + walk),
            self._cost(road.metres + back.metres, Decimal(0)),
            road.delay_seconds,
            drive_destination=destination,
            detail=destination.name,
            evidence=(road.evidence, back.evidence),
        )

    async def _onward_car(self, trip, previous, destination, now, warnings, *, origin=None):
        work, _, selected = previous
        if not selected or selected.mode != "park_ride":
            warnings.append(
                "Car is not confirmed at the office; confirm collection before this appointment"
            )
            return []
        site = next(
            (
                s
                for s in self.settings.get("park_ride_sites", [])
                if place_from(s) == selected.drive_destination
            ),
            None,
        )
        if not site or not site.get("timetable_confirmed") or not site.get("return_departures"):
            warnings.append("Confirm Park & Ride return departures to plan car collection")
            return []
        warnings.append(
            "Car collection uses your confirmed return bus timetable; return delays unconfirmed"
        )
        point = place_from(site)
        ready = max(work.end_at, now)
        walk = site.get("return_walk", site["office_walk"])
        if work.end_at <= now and origin and origin != previous[1]:
            access = await self.road.route(origin, previous[1], now, now=now, mode="pedestrian")
            walk += (access.seconds + 59) // 60
            warnings.append(
                "Return collection includes walking from your current location via the office"
            )
        boarding = self.settings.get("boarding_minutes", 5)
        parking = self.settings.get("parking_minutes", 5)
        result = []
        for service in timetable(
            site["return_departures"],
            work.end_at,
            site["bus_minutes"],
            "Configured return bus timetable",
        ):
            office_leave = service.departure - timedelta(minutes=walk + boarding)
            collected = service.arrival + timedelta(minutes=parking)
            if (
                office_leave < ready
                or service.departure > at(site["last_return"], work.end_at)
                or collected > at(site["closes"], work.end_at)
            ):
                continue
            car = await self._car(trip, point, destination, now, earliest=collected)
            # Leave the office in time for the return bus, then drive once the car is collected.
            result.append(
                replace(
                    car,
                    leave_at=office_leave,
                    detail=f"Collect car at {site['name']}, bus {service.departure:%H:%M}, car ready {collected:%H:%M}; then {destination.name}",
                    evidence=(service.evidence,) + car.evidence,
                )
            )
        return result

    async def _park_ride(self, trip, origin, now, warnings):
        result = []
        for site in self.settings.get("park_ride_sites", []):
            try:
                if trip.arrival_by.weekday() not in site.get("days", list(range(7))):
                    continue
                destination = place_from(site)
                services = None
                if self.bus and site.get("stop_id") and trip.arrival_by.date() == now.date():
                    try:
                        services = await self.bus.departures(site["stop_id"], site["line"], now)
                        services = [
                            replace(s, arrival=s.departure + timedelta(minutes=site["bus_minutes"]))
                            for s in services
                        ]
                        warnings.append(
                            f"{site['name']}: bus ride duration uses your confirmed timetable"
                        )
                    except ProviderError:
                        warnings.append(f"{site['name']}: live departures unavailable")
                if services is None or site.get("timetable_confirmed"):
                    if not site.get("timetable_confirmed"):
                        warnings.append(f"{site['name']}: confirm its service timetable first")
                        continue
                    configured = timetable(
                        site.get("departures", ""),
                        trip.arrival_by,
                        site["bus_minutes"],
                        "Configured bus timetable",
                    )
                    warnings.append(
                        f"{site['name']}: timetable estimates; live bus delays unconfirmed"
                    )
                    # A stop board proves coverage only for the departures it reports.
                    # Retain cancellation/delay records so the matching manual service cannot return.
                    covered = {s.scheduled_departure or s.departure for s in services or []}
                    services = (services or []) + [
                        s for s in configured if s.departure not in covered
                    ]
                collection = trip.end_at + timedelta(
                    minutes=site.get("return_walk", site["office_walk"])
                )
                return_ok = collection <= at(
                    site["last_return"], trip.end_at
                ) and collection + timedelta(
                    minutes=site["bus_minutes"] + self.settings.get("parking_minutes", 5)
                ) <= at(site["closes"], trip.end_at)
                if site.get("return_departures") and site.get("timetable_confirmed"):
                    return_ok = any(
                        service.departure
                        >= collection + timedelta(minutes=self.settings.get("boarding_minutes", 5))
                        and service.departure <= at(site["last_return"], trip.end_at)
                        and service.arrival
                        + timedelta(minutes=self.settings.get("parking_minutes", 5))
                        <= at(site["closes"], trip.end_at)
                        for service in timetable(
                            site["return_departures"],
                            trip.end_at,
                            site["bus_minutes"],
                            "Configured return bus timetable",
                        )
                    )
                else:
                    warnings.append(
                        f"{site['name']}: return limit is an estimate; confirm return departures for car collection"
                    )
                for bus in services:
                    if bus.departure < now or bus.arrival >= trip.arrival_by:
                        continue
                    guess = bus.departure - timedelta(minutes=45)
                    road = await self.road.route(origin, destination, max(guess, now), now=now)
                    leave = bus.departure - timedelta(
                        seconds=road.seconds, minutes=self.settings.get("parking_minutes", 5)
                    )
                    road = await self.road.route(origin, destination, max(leave, now), now=now)
                    back = await self.road.route(destination, origin, max(collection, now), now=now)
                    fare = effective_fare(
                        self.settings.get("park_ride_fare", 4),
                        self.settings.get("park_ride_pass", False),
                    )
                    candidate = park_ride_candidate(
                        trip,
                        destination,
                        road,
                        bus,
                        office_walk=site["office_walk"],
                        parking=self.settings.get("parking_minutes", 5),
                        safety=self.settings.get("safety_minutes", 10),
                        cost=self._cost(road.metres + back.metres, fare),
                        return_available=return_ok,
                    )
                    if candidate.leave_at >= now:
                        result.append(candidate)
            except (ProviderError, KeyError, ValueError, TypeError):
                warnings.append(
                    f"{site.get('name', 'Park & Ride')}: route or timetable unavailable"
                )
        return result

    async def _rail(self, trip, origin, destination, now, warnings):
        cfg = self.settings
        if not cfg.get("origin_station") or not cfg.get("destination_station"):
            warnings.append("Confirm both station locations and CRS codes")
            return []
        start_station, end_station = (
            place_from(cfg["origin_station"]),
            place_from(cfg["destination_station"]),
        )
        services = None
        if self.rail:
            try:
                services = await self.rail.services(
                    cfg["origin_crs"],
                    cfg["destination_crs"],
                    max(now, trip.arrival_by - timedelta(hours=2)),
                    trip.arrival_by,
                    now,
                )
            except CoverageError:
                warnings.append("Rail live board does not cover this journey time")
            except ProviderError:
                warnings.append("Live train information unavailable")
        if services is None:
            if not cfg.get("rail_timetable_confirmed"):
                warnings.append(
                    "Rail timetable is not confirmed; cannot recommend an unverified train"
                )
                return []
            services = timetable(
                cfg.get("rail_departures", ""),
                trip.arrival_by,
                cfg["rail_minutes"],
                "Configured rail timetable",
            )
            warnings.append("Rail uses a configured direct-service timetable; delays unconfirmed")
        walk_origin = await self.road.route(origin, start_station, now, now=now, mode="pedestrian")
        walk_office = await self.road.route(
            end_station, destination, now, now=now, mode="pedestrian"
        )
        if walk_origin.seconds > cfg.get("max_station_walk", 45) * 60:
            warnings.append("Current origin is too far to walk to the configured station")
            return []
        station_minutes = (walk_origin.seconds + 59) // 60
        office_minutes = (walk_office.seconds + 59) // 60
        return_ok = bool(cfg.get("rail_last_return")) and trip.end_at + timedelta(
            minutes=office_minutes + cfg.get("boarding_minutes", 5)
        ) <= at(cfg.get("rail_last_return", "00:00"), trip.end_at)
        fare = effective_fare(cfg.get("rail_fare") or None, cfg.get("rail_pass", False))
        return [
            rail_candidate(
                trip,
                service,
                station_walk=station_minutes,
                office_walk=office_minutes,
                boarding=cfg.get("boarding_minutes", 5),
                safety=cfg.get("safety_minutes", 10),
                cost=fare,
                return_available=return_ok,
            )
            for service in services
            if service.departure
            - timedelta(minutes=station_minutes + cfg.get("boarding_minutes", 5))
            >= now
        ]
