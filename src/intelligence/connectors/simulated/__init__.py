"""Explicit synthetic connectors used only for deterministic contract validation."""

from intelligence.connectors.simulated.business_registry import (
    SIMULATED_BUSINESS_REGISTRY_CONNECTOR_ID,
    SIMULATED_BUSINESS_REGISTRY_SOURCE_ID,
    SimulatedBusinessRegistryConnector,
)
from intelligence.connectors.simulated.scenarios import BusinessRegistryScenario

__all__ = [
    "SIMULATED_BUSINESS_REGISTRY_CONNECTOR_ID",
    "SIMULATED_BUSINESS_REGISTRY_SOURCE_ID",
    "BusinessRegistryScenario",
    "SimulatedBusinessRegistryConnector",
]
