"""Native management-only attendance sensors. No writes or PIN input."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import timing_options

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known = set()
    async_add_entities([CountSensor(coordinator,entry.entry_id,s) for s in ("here","break","leaving","due","late","gone","present","on_leave","available")])
    @callback
    def add_staff():
        new = set(coordinator.data or {}) - known
        if new:
            known.update(new)
            async_add_entities([StaffSensor(coordinator,entry.entry_id,coordinator.data[uid]) for uid in sorted(new)])
    add_staff()
    entry.async_on_unload(coordinator.async_add_listener(add_staff))

class CountSensor(CoordinatorEntity, SensorEntity):
    _attr_icon = "mdi:account-group"
    _unrecorded_attributes = frozenset({"display_options", "rows"})
    def __init__(self, coordinator, entry_id, status):
        super().__init__(coordinator)
        self.status = status
        self._attr_unique_id = f"{entry_id}_count_{status}"
        self._attr_name = f"RotaCloud {status.title()}"
    @property
    def extra_state_attributes(self):
        result = {"rotacloud_kind":"count","rotacloud_status":self.status,"last_api_refresh":self.coordinator.last_api_refresh}
        if self.status == "present":
            result["display_options"] = timing_options(self.coordinator.entry.options)
            result["config_entry_id"] = self.coordinator.entry.entry_id
            result["day_start"] = self.coordinator.day
            result["planning_available"] = self.coordinator.planning_available
        if self.status in ("on_leave", "available"):
            result["rows"] = self.coordinator.planning_rows(self.status)
            result["planning_available"] = self.coordinator.planning_available
        return result
    @property
    def native_value(self):
        if self.status in ("on_leave", "available"):
            return len(self.coordinator.planning_rows(self.status)) if self.coordinator.planning_available else None
        states = {"here","break","leaving"} if self.status=="present" else {self.status}
        return sum(s.status in states and not s.previous_day for s in (self.coordinator.data or {}).values())

class StaffSensor(CoordinatorEntity, SensorEntity):
    _attr_icon = "mdi:account-clock"
    _unrecorded_attributes = frozenset({"scheduled_start","scheduled_end","clock_in","clock_out",
                                      "active_break_start","completed_break_seconds","clock_in_delta_seconds",
                                      "clock_out_delta_seconds","shifts","shift_duration_seconds","staff_name",
                                      "previous_day","total_break_seconds_today","break_warning"})
    def __init__(self, coordinator, entry_id, staff):
        super().__init__(coordinator)
        self.uid = staff.user_id
        self._attr_unique_id = f"{entry_id}_staff_{self.uid}"
        self._attr_name = f"RotaCloud {staff.name}"
    @property
    def native_value(self):
        staff = (self.coordinator.data or {}).get(self.uid)
        return staff.status if staff else "off_duty"
    @property
    def extra_state_attributes(self):
        staff = (self.coordinator.data or {}).get(self.uid)
        if not staff:
            return {"rotacloud_kind":"staff"}
        a,s = staff.attendance, staff.scheduled
        return {"rotacloud_kind":"staff","staff_name":staff.name,"scheduled_start":s.start if s else None,"scheduled_end":s.end if s else None,
                "clock_in":a.clock_in if a else None,"clock_out":a.clock_out if a else None,
                "active_break_start":staff.active_break_start,"completed_break_seconds":staff.completed_break_seconds,
                "clock_in_delta_seconds":staff.clock_in_delta_seconds,"clock_out_delta_seconds":staff.clock_out_delta_seconds,
                "shift_duration_seconds":a.shift_seconds(a.clock_out) if a and a.clock_out is not None else None,
                "previous_day":staff.previous_day,"total_break_seconds_today":staff.total_break_seconds_today,
                "break_warning":staff.break_warning,
                "shifts":[{"id":x.id,"start":x.start,"end":x.end} for x in staff.shifts]}
