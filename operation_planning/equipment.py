"""Small, provenance-first first-stage air-conditioner catalogue.

The cooling and rated input values below are public manufacturer/label points.
Purchase, installation, maintenance and SHR are deliberately left as user
inputs when a source does not publish them for the exact combination.  The
catalogue is not a claim of a complete part-load performance map.
"""
from __future__ import annotations
from dataclasses import asdict
from typing import Any, Dict, List
from .schemas import EquipmentProfile

EQUIPMENT: Dict[str, EquipmentProfile] = {
    "midea_msagbu12_mox201": EquipmentProfile(
        "midea_msagbu12_mox201", "美的", "MSAGBU-12HRFN8 / MOX201-12HFN8",
        "MSAGBU-12HRFN8室内机 + MOX201-12HFN8室外机", 3.52, 1.034, 3.40, None,
        {"indoor_c": [17, 30], "outdoor_c": [-15, 50], "capacity_range_kw": [1.37, 4.31], "rated_condition": "manufacturer rated point"},
        None, None, None, 10,
        "https://www.midea.com/it/hvac/monosplit/xtreme/climatizzatore-xtreme-msagbu-12hrfn8-mox201-12hfn8",
        "public_manufacturer_page",
        ["SHR and price are not published for this exact comparison; user quote required", "rated input is not a full hourly power curve", "country-market specification may differ from a China quote"],
    ),
    "midea_gaia12": EquipmentProfile(
        "midea_gaia12", "美的", "GAIA-12HRFN8",
        "GAIA-12HRFN8 split combination", 3.52, 0.920, 3.83, None,
        {"indoor_c": [17, 30], "outdoor_c": [-15, 50], "capacity_range_kw": [1.32, 4.37], "rated_condition": "manufacturer rated point"},
        None, None, None, 10,
        "https://www.midea.com/ge-en/air-conditioners/inverter-conditioner/conditioner-gaia-12hrfn8.gaia-12hrfn8",
        "public_manufacturer_page",
        ["SHR and price are not published for this exact comparison; user quote required", "rated input is not a full hourly power curve", "market-specific specification"],
    ),
    "daikin_ftxf35_rxf35": EquipmentProfile(
        "daikin_ftxf35_rxf35", "大金", "FTXF35E5V1B / RXF35F5V1B",
        "FTXF35E5V1B室内机 + RXF35F5V1B室外机", 3.50, 1.129, 3.10, None,
        {"indoor_c": [18, 32], "outdoor_c": [10, 46], "capacity_range_kw": [1.32, 3.50], "rated_condition": "EU energy label, 35°C declared cooling point"},
        None, None, None, 10,
        "https://energylabel.daikin.eu/eu/en_US/lot10/jcr%3Acontent/root/services.json/lot10/datasheet/html?locale=en_US&product=FTXF35E5V1B+%2F+RXF35F5V1B",
        "public_energy_label",
        ["rated input derived as 3.50/3.10 at the 35°C declared point", "SHR and purchase quote are absent", "EU declared point is not a China field measurement"],
    ),
}


def catalogue() -> List[Dict[str, Any]]:
    return [asdict(x) for x in EQUIPMENT.values()]


def get_equipment(equipment_id: str) -> EquipmentProfile:
    if equipment_id not in EQUIPMENT:
        raise ValueError(f"未支持的设备型号：{equipment_id}")
    return EQUIPMENT[equipment_id]