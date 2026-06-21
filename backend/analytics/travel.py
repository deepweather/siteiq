from models.analytics import ZoneTravelMetrics
from state.source import SiteStateSource
from config import LOADED_HOURLY_RATE, WORKDAY_START, WORKDAY_END


def compute_travel_metrics(source: SiteStateSource) -> list[ZoneTravelMetrics]:
    results = []
    workday_seconds = WORKDAY_END - WORKDAY_START
    elapsed = max(source.sim_time - WORKDAY_START, 1.0)
    day_fraction = min(elapsed / workday_seconds, 1.0)

    for zone in source.site.zones:
        workers = source.workers_in_zone(zone.id)
        if not workers:
            continue

        total_toilet_rt = 0.0
        total_toilet_trips = 0
        total_material_rt = 0.0
        total_material_trips = 0
        total_time_working = 0.0
        total_time_walking = 0.0
        total_time_facilities = 0.0

        for w in workers:
            internals = source.worker_internals_for(w.id)
            if internals is None:
                continue
            # Duck-typed: WorkerInternals dataclass attribute access (post
            # step 3). Fallback to dict access for any test FakeSource still
            # emitting raw dicts.
            if hasattr(internals, "time_working"):
                total_time_working += internals.time_working
                total_time_walking += internals.time_walking
                total_time_facilities += internals.time_at_facilities
                total_toilet_trips += internals.toilet_trips_today
                total_toilet_rt += internals.toilet_total_round_trip
                total_material_trips += internals.material_trips_today
                total_material_rt += internals.material_total_round_trip
            else:
                total_time_working += internals["time_working"]
                total_time_walking += internals["time_walking"]
                total_time_facilities += internals["time_at_facilities"]
                total_toilet_trips += internals["toilet_trips_today"]
                total_toilet_rt += internals["toilet_total_round_trip"]
                total_material_trips += internals["material_trips_today"]
                total_material_rt += internals["material_total_round_trip"]

        n = len(workers)
        avg_toilet_rt_sec = (total_toilet_rt / total_toilet_trips) if total_toilet_trips > 0 else 0
        avg_toilet_rt_min = avg_toilet_rt_sec / 60.0

        trips_per_day = (total_toilet_trips / day_fraction) if day_fraction > 0.1 else total_toilet_trips
        avg_trips_per_worker = trips_per_day / n if n > 0 else 0

        daily_toilet_walk_min = avg_trips_per_worker * avg_toilet_rt_min * n
        daily_toilet_walk_cost = daily_toilet_walk_min / 60.0 * LOADED_HOURLY_RATE

        avg_material_rt_sec = (total_material_rt / total_material_trips) if total_material_trips > 0 else 0
        avg_material_rt_min = avg_material_rt_sec / 60.0
        mat_trips_per_day = (total_material_trips / day_fraction) if day_fraction > 0.1 else total_material_trips
        avg_mat_trips_per_worker = mat_trips_per_day / n if n > 0 else 0
        daily_material_walk_cost = (avg_mat_trips_per_worker * avg_material_rt_min * n) / 60.0 * LOADED_HOURLY_RATE

        total_active = total_time_working + total_time_walking + total_time_facilities
        productivity = total_time_working / total_active if total_active > 0 else 0.5

        results.append(ZoneTravelMetrics(
            zone_id=zone.id,
            num_workers=n,
            avg_toilet_round_trip_min=round(avg_toilet_rt_min, 1),
            avg_toilet_trips_per_day=round(avg_trips_per_worker, 1),
            daily_toilet_walk_minutes=round(daily_toilet_walk_min, 1),
            daily_toilet_walk_cost=round(daily_toilet_walk_cost, 2),
            avg_material_round_trip_min=round(avg_material_rt_min, 1),
            daily_material_walk_cost=round(daily_material_walk_cost, 2),
            productivity_rate=round(productivity, 3),
        ))

    return results
