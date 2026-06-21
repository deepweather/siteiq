"""Shared pytest fixtures."""
import sys
import os

# Make backend imports work like the live app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from simulation.engine import SimulationEngine


@pytest.fixture
def engine() -> SimulationEngine:
    """A fresh SimulationEngine using the default westhafen project."""
    return SimulationEngine()


@pytest.fixture
def frankfurt_engine() -> SimulationEngine:
    """europa-quarter has 6 zones (incl. zone-f) and 3 toilets."""
    return SimulationEngine(project_id="europa-quarter")


@pytest.fixture
def munich_engine() -> SimulationEngine:
    """isar-bridge runs to day 210 with start_day=135."""
    return SimulationEngine(project_id="isar-bridge")
