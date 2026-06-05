"""
Scenario registry — single import point for all benchmark scenarios.
"""

from ptu_benchmark.scenarios.base import BaseScenario
from ptu_benchmark.scenarios.scenario_a import ScenarioA
from ptu_benchmark.scenarios.scenario_b import ScenarioB
from ptu_benchmark.scenarios.scenario_c import ScenarioC
from ptu_benchmark.scenarios.scenario_d import ScenarioD
from ptu_benchmark.scenarios.scenario_e import ScenarioE

# Ordered registry of all available scenarios
SCENARIOS: dict[str, type[BaseScenario]] = {
    "A": ScenarioA,
    "B": ScenarioB,
    "C": ScenarioC,
    "D": ScenarioD,
    "E": ScenarioE,
}

__all__ = [
    "BaseScenario",
    "ScenarioA",
    "ScenarioB",
    "ScenarioC",
    "ScenarioD",
    "ScenarioE",
    "SCENARIOS",
]
