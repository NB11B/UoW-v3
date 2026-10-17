"""Reference Domain Package Definitions for Industrial, Cybersecurity, and Logistics."""
from __future__ import annotations

from typing import Dict, Optional
from .models import ActionDefinition, DomainPackage, EntityDefinition, SafetyGuard


def build_industrial_domain_package() -> DomainPackage:
    pkg = DomainPackage(
        domain_id="domain.industrial.v1",
        version="1.0.0",
        name="Industrial",
        description="High-integrity industrial telemetry, process control, and emergency isolation.",
    )
    # Register authoritative entities
    pkg.entities["PUMP_101"] = EntityDefinition("PUMP_101", "pump", ["RUNNING", "IDLE", "ISOLATED", "OVERPRESSURE"])
    pkg.entities["PUMP_102"] = EntityDefinition("PUMP_102", "pump", ["RUNNING", "IDLE", "ISOLATED"])
    pkg.entities["VALVE_201"] = EntityDefinition("VALVE_201", "valve", ["OPEN", "CLOSED", "VENTING"])
    pkg.entities["VALVE_202"] = EntityDefinition("VALVE_202", "valve", ["OPEN", "CLOSED"])
    pkg.entities["TANK_01"] = EntityDefinition("TANK_01", "tank", ["NOMINAL", "DRAINING", "FULL"])
    pkg.entities["SECTOR_A"] = EntityDefinition("SECTOR_A", "sector", ["ACTIVE", "SHUTDOWN"])

    # Register aliases
    pkg.aliases["P-101"] = "PUMP_101"
    pkg.aliases["P-102"] = "PUMP_102"
    pkg.aliases["V-201"] = "VALVE_201"
    pkg.aliases["V-202"] = "VALVE_202"

    # Register operations
    pkg.actions["isolate_pump"] = ActionDefinition(
        action_name="isolate_pump",
        required_parameters=["pump_id", "isolation_valve_id"],
        applicable_entity_types=["pump"],
    )
    pkg.actions["vent_pressure"] = ActionDefinition(
        action_name="vent_pressure",
        required_parameters=["valve_id", "target_pressure"],
        applicable_entity_types=["valve"],
        safety_guards=[
            SafetyGuard(
                guard_id="guard.pressure.max_limit",
                parameter="target_pressure",
                condition="max_value:180.0",
                threshold=180.0,
            ),
            SafetyGuard(
                guard_id="guard.pressure.min_limit",
                parameter="target_pressure",
                condition="min_value:0.0",
                threshold=0.0,
            ),
        ],
    )
    pkg.actions["emergency_shutdown"] = ActionDefinition(
        action_name="emergency_shutdown",
        required_parameters=["sector_id", "reason"],
        applicable_entity_types=["sector"],
    )
    return pkg


def build_cybersecurity_domain_package() -> DomainPackage:
    pkg = DomainPackage(
        domain_id="domain.cybersecurity.v1",
        version="1.0.0",
        name="Cybersecurity",
        description="OT/ICS and host security incident response and perimeter containment.",
    )
    pkg.entities["HOST_10"] = EntityDefinition("HOST_10", "host", ["CLEAN", "SUSPECTED", "ISOLATED"])
    pkg.entities["HOST_20"] = EntityDefinition("HOST_20", "host", ["CLEAN", "ISOLATED"])
    pkg.entities["FIREWALL_01"] = EntityDefinition("FIREWALL_01", "firewall", ["ACTIVE", "DEGRADED"])
    pkg.entities["GATEWAY_01"] = EntityDefinition("GATEWAY_01", "gateway", ["ONLINE", "OFFLINE"])

    pkg.aliases["h-10"] = "HOST_10"
    pkg.aliases["fw-01"] = "FIREWALL_01"

    pkg.actions["quarantine_host"] = ActionDefinition(
        action_name="quarantine_host",
        required_parameters=["host_id", "isolation_level"],
        applicable_entity_types=["host"],
    )
    pkg.actions["block_traffic"] = ActionDefinition(
        action_name="block_traffic",
        required_parameters=["target_id", "port"],
        applicable_entity_types=["firewall", "gateway"],
    )
    return pkg


def build_logistics_domain_package() -> DomainPackage:
    pkg = DomainPackage(
        domain_id="domain.logistics.v1",
        version="1.0.0",
        name="Logistics",
        description="Multi-modal freight scheduling, asset tracking, and contingency routing.",
    )
    pkg.entities["DEPOT_A"] = EntityDefinition("DEPOT_A", "depot", ["OPEN", "CONGESTED"])
    pkg.entities["DEPOT_B"] = EntityDefinition("DEPOT_B", "depot", ["OPEN", "CLOSED"])
    pkg.entities["TRUCK_01"] = EntityDefinition("TRUCK_01", "vehicle", ["EN_ROUTE", "IDLE"])
    pkg.entities["SHIPMENT_1001"] = EntityDefinition("SHIPMENT_1001", "shipment", ["TRANSIT", "DELAYED", "HELD"])
    pkg.entities["SHIPMENT_1002"] = EntityDefinition("SHIPMENT_1002", "shipment", ["TRANSIT"])

    pkg.aliases["SHP-1001"] = "SHIPMENT_1001"
    pkg.aliases["SHP-1002"] = "SHIPMENT_1002"

    pkg.actions["reroute_shipment"] = ActionDefinition(
        action_name="reroute_shipment",
        required_parameters=["shipment_id", "destination_depot_id"],
        applicable_entity_types=["shipment"],
    )
    pkg.actions["hold_shipment"] = ActionDefinition(
        action_name="hold_shipment",
        required_parameters=["shipment_id", "reason"],
        applicable_entity_types=["shipment"],
    )
    return pkg


REFERENCE_DOMAIN_CATALOG: Dict[str, DomainPackage] = {
    "domain.industrial.v1": build_industrial_domain_package(),
    "domain.cybersecurity.v1": build_cybersecurity_domain_package(),
    "domain.logistics.v1": build_logistics_domain_package(),
}


def get_reference_domain_package(domain_id: str) -> Optional[DomainPackage]:
    return REFERENCE_DOMAIN_CATALOG.get(domain_id)
