"""Upcoming journey sensors with stable registry identifiers."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        JourneySensor(entry.runtime_data, key)
        for key in (
            "destination",
            "mode",
            "leave_by",
            "expected_arrival",
            "return_cost",
            "readiness",
        )
    )


class JourneySensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_name = key.replace("_", " ").capitalize()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title,
            manufacturer="Journey Ready",
            model="Calendar travel planner",
            sw_version=VERSION,
        )
        if key in ("leave_by", "expected_arrival"):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif key == "return_cost":
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_native_unit_of_measurement = "GBP"
            self._attr_suggested_display_precision = 2

    @property
    def native_value(self):
        plan = self.coordinator.next_plan
        candidate = plan.selected if plan else None
        if self.key == "readiness":
            if not self.coordinator.calendar_ok:
                return "calendar_unavailable"
            if self.coordinator.status:
                return "attention"
            if not plan:
                return "idle"
            return (
                "needs_configuration"
                if not candidate
                else "estimates"
                if plan.warnings
                else "ready"
            )
        if not plan:
            return None
        if self.key == "destination":
            return plan.obligation.destination or plan.obligation.title
        if not candidate:
            return None
        return {
            "mode": candidate.mode,
            "leave_by": candidate.leave_at,
            "expected_arrival": candidate.arrive_at,
            "return_cost": float(candidate.cost) if candidate.cost is not None else None,
        }.get(self.key)

    @property
    def extra_state_attributes(self):
        plan = self.coordinator.next_plan
        data = {"issues": list(self.coordinator.status)}
        if plan:
            data.update(
                {
                    "obligation_id": plan.obligation.id,
                    "reasons": list(plan.reasons),
                    "warnings": list(plan.warnings),
                }
            )
            if plan.selected:
                data["sources"] = [
                    {"source": e.source, "kind": e.kind, "observed_at": e.observed_at.isoformat()}
                    for e in plan.selected.evidence
                ]
                data["alternatives"] = [
                    {
                        "mode": c.mode,
                        "leave_at": c.leave_at.isoformat(),
                        "cost": float(c.cost) if c.cost is not None else None,
                        "feasible": c.feasible and c.return_available,
                    }
                    for c in plan.alternatives
                ]
        return data
