import asyncio
import sys
import os

# Ensure the backend directory is on the path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import ANALYTICS_UPDATE_INTERVAL
from simulation.engine import SimulationEngine, run_simulation_loop
from analytics.aggregator import compute_waste_summary
from optimization.facility_placement import optimize_toilet_placement
from optimization.material_staging import optimize_material_staging
from optimization.equipment_schedule import optimize_equipment
from api.routes import router as api_router, init_routes
from api.websocket import router as ws_router, init_ws

engine: SimulationEngine | None = None
latest_analytics = None
cached_recommendations: list = []
recs_dirty = True


def get_latest_analytics():
    return latest_analytics


def get_recommendations():
    global cached_recommendations, recs_dirty
    if recs_dirty or not cached_recommendations:
        recs = []
        recs.extend(optimize_toilet_placement(engine))
        recs.extend(optimize_material_staging(engine))
        recs.extend(optimize_equipment(engine))

        applied_ids = {r.id for r in cached_recommendations if r.applied}
        for r in recs:
            if r.id in applied_ids:
                r.applied = True

        cached_recommendations = recs
        recs_dirty = False
    return cached_recommendations


async def run_analytics_loop(eng: SimulationEngine):
    global latest_analytics, recs_dirty
    while eng.running:
        try:
            latest_analytics = compute_waste_summary(eng)
            recs_dirty = True
        except Exception as e:
            print(f"Analytics error: {e}")
        await asyncio.sleep(ANALYTICS_UPDATE_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    engine = SimulationEngine()
    init_routes(engine, get_recommendations)
    init_ws(engine, get_latest_analytics)
    sim_task = asyncio.create_task(run_simulation_loop(engine))
    analytics_task = asyncio.create_task(run_analytics_loop(engine))
    yield
    engine.running = False
    sim_task.cancel()
    analytics_task.cancel()


app = FastAPI(title="SiteIQ Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)
