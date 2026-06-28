import datetime as _dt

SITE_WIDTH = 240
SITE_HEIGHT = 160

WORKER_SPEED = 1.2
LOADED_HOURLY_RATE = 50
TOILET_INTERVAL = 7200          # ~2 hours — ~5 visits in an 11h day
BREAK_INTERVAL = 14400
MATERIAL_RUN_INTERVAL = 7200    # ~2 hours between material pickups
TOILET_DWELL = 240
BREAK_DWELL = 1500
MATERIAL_DWELL = 180
WORK_SESSION_MIN = 1800
WORK_SESSION_MAX = 3600
JITTER_FACTOR = 0.2

# Equipment idle cost rates (rental-equivalent €/hour of idle time)
CRANE_HOURLY_RATE = 180
PUMP_HOURLY_RATE = 120
EXCAVATOR_HOURLY_RATE = 90

# ── System-of-record cost rates ──────────────────────────────────────
# Default rate card the cost engine folds the event ledger against. Per-org
# editable rate cards are a documented future extension; these constants are
# the ground-truth defaults until then.

# Loaded labour cost per hour, by trade. Trades not listed fall back to
# LOADED_HOURLY_RATE. Values are illustrative DACH loaded rates (€/h).
LABOR_HOURLY_RATE_BY_TRADE: dict[str, float] = {
    "laborer": 45,
    "carpenter": 55,
    "electrician": 62,
    "plumber": 60,
    "ironworker": 58,
    "mason": 54,
    "operator": 65,
    "finisher": 52,
}

# Full equipment hourly rate (rental + operator-equivalent) by subtype.
# Used by the cost engine; the idle-cost analytics above use the crane/
# pump/excavator constants directly.
EQUIPMENT_HOURLY_RATE_BY_SUBTYPE: dict[str, float] = {
    "tower_crane": CRANE_HOURLY_RATE,
    "concrete_pump": PUMP_HOURLY_RATE,
    "excavator": EXCAVATOR_HOURLY_RATE,
    "sheet_pile": 40,
    "dewatering_pump": 35,
}

# Material unit cost (€ per delivered unit) by subtype. Units are subtype-
# specific (tonnes of rebar, m of conduit, sheets of drywall, m³ concrete).
MATERIAL_UNIT_COST_BY_SUBTYPE: dict[str, float] = {
    "rebar": 950.0,       # €/tonne
    "conduit": 6.5,       # €/m
    "drywall": 12.0,      # €/sheet
    "concrete": 130.0,    # €/m³
    "pipe": 18.0,         # €/m
    "aggregate": 28.0,    # €/tonne
}
DEFAULT_MATERIAL_UNIT_COST = 50.0

SIM_TICK_INTERVAL = 0.1
SIM_SECONDS_PER_TICK = 30
ANALYTICS_UPDATE_INTERVAL = 1.0
WS_PUSH_INTERVAL = 0.1

# How often the system-of-record drain loop flushes each live engine's
# buffered operational events into the ledger (seconds).
EVENT_DRAIN_INTERVAL = 5.0

# Anchor that maps the simulation clock (sim_day, sim_time) to calendar
# `occurred_at` timestamps in the ledger. Sim day N, time T (seconds) ->
# RECORD_EPOCH_DATE + (N-1) days + T seconds. Keeps backfilled history and
# live emission on one continuous, deterministic timeline. Real camera
# sources will use wall-clock time instead.
RECORD_EPOCH_DATE = _dt.date(2026, 1, 6)

WORKDAY_START = 6 * 3600
WORKDAY_END = 17 * 3600
WORKING_DAYS_PER_MONTH = 22

MAX_TRAIL_LENGTH = 150

# ── Navmesh (worker pathfinding) ─────────────────────────────────────
# Workers no longer walk in straight lines. `simulation/navmesh.NavMesh`
# overlays a weighted grid on every level and uses A* + string-pull so
# paths route around equipment, hug roads, and avoid foundation pits.
# The values below define the cost grid; tune the weights to shift the
# balance between "shortest" and "stay on roads".

# Cell size in metres. 2 m gives ~9.6k cells on a 240x160 site —
# fast enough for cold A* (< 5 ms), trivial when cached.
NAVMESH_CELL_SIZE_M = 2.0

# Per-cell traversal costs. Lower = cheaper = preferred. Roads are the
# baseline cost so the A* heuristic stays admissible.
#   road (1.0) < open ground (1.5) < zone interior (2.0)
# Workers prefer roads, then walk across empty ground, and only cross
# other workers' zones when the detour would be very long. Their own
# zone they cross when leaving it — analytics still measures the
# zone-time correctly via `internals.time_walking`.
NAVMESH_COST_ROAD = 1.0
NAVMESH_COST_OPEN = 1.5
NAVMESH_COST_ZONE = 2.0
# Treated as +infinity by A*. Any value >= this is impassable.
NAVMESH_COST_BLOCKED = 1e9

# Renderer-baked road geometry, kept here so the simulation and the
# canvas drawer share one source of truth. South strip = the access
# road along the bottom edge; west strip = the spur up the left side.
ROAD_SOUTH_STRIP_M = 12.0
ROAD_WEST_STRIP_M = 8.0

# Footprint radii in metres for the navmesh's "no walking through a
# crane" rule. Picked to match the visual extents in the renderer +
# real-world equipment swept areas. Subtypes not in the table fall
# through to 0 m (no footprint), which is the right default for tiny
# props (sheet piles on their own are placed in rows, and a row's
# combined footprint forms a wall naturally).
EQUIPMENT_FOOTPRINT_RADIUS_M: dict[str, float] = {
    "tower_crane": 15.0,
    "concrete_pump": 6.0,
    "excavator": 8.0,
    "sheet_pile": 2.0,
    "dewatering_pump": 3.0,
}
