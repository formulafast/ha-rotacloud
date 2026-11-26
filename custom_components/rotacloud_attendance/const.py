VERSION = "0.7.0"
DOMAIN = "rotacloud_attendance"
CONF_TERMINAL = "terminal_id"
CONF_POLL = "poll_seconds"
CONF_LATE = "late_minutes"
CONF_LEAVING = "leaving_minutes"
CONF_CLOCKING = "enable_clocking"
CONF_ACTIVATE_TERMINAL = "activate_terminal"
DEFAULT_POLL = 86400
DEFAULT_LATE = 0
DEFAULT_LEAVING = 15
REFRESH_EVENT = "rotacloud_attendance_refresh"

TIMING_KINDS = ("clock_in_early", "clock_in_late", "clock_out_early", "clock_out_late")
def timing_options(options):
    return {kind: {"minutes": options.get(kind + "_minutes", 0),
                   "color": options.get(kind + "_color", [239, 68, 68] if kind.endswith("late") else [234, 179, 8])}
            for kind in TIMING_KINDS}
