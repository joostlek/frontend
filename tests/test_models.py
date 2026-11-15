"""Tests for the models of aiobambulab."""

from __future__ import annotations

from typing import Any

import pytest

from aiobambulab import (
    PrinterInfo,
    PrinterModel,
    PrinterState,
    PrintState,
    SpeedProfile,
)

from .conftest import SERIAL, load_fixture


def _report(name: str) -> dict[str, Any]:
    report: dict[str, Any] = load_fixture(name)["print"]
    return report


def _info(name: str) -> PrinterInfo:
    return PrinterInfo.from_modules(SERIAL, load_fixture(name)["info"]["module"])


def test_state_of_an_idle_printer() -> None:
    """A printer with a chamber sensor reports everything."""
    assert PrinterState.from_report(
        _report("x1c_status.json"), PrinterModel.X1C
    ) == PrinterState(
        print_state=PrintState.IDLE,
        job_name=None,
        progress=0,
        remaining_minutes=0,
        current_layer=0,
        total_layers=0,
        nozzle_temperature=25,
        nozzle_target_temperature=0,
        bed_temperature=24,
        bed_target_temperature=0,
        chamber_temperature=26,
        speed_profile=SpeedProfile.STANDARD,
        chamber_light_on=True,
        wifi_signal=-45,
    )


def test_state_of_a_printer_without_chamber_sensor() -> None:
    """A P1S reports a chamber temperature that it does not measure."""
    assert PrinterState.from_report(
        _report("p1s_status.json"), PrinterModel.P1S
    ) == PrinterState(
        print_state=PrintState.PRINTING,
        job_name="Benchy",
        progress=42,
        remaining_minutes=73,
        current_layer=96,
        total_layers=240,
        # The printer reports 219.90625 and 59.6875.
        nozzle_temperature=220,
        nozzle_target_temperature=220,
        bed_temperature=60,
        bed_target_temperature=60,
        chamber_temperature=None,
        speed_profile=SpeedProfile.SPORT,
        chamber_light_on=False,
        wifi_signal=-58,
    )


def test_state_of_a_printer_that_reports_the_chamber_as_a_device() -> None:
    """Newer firmware packs the chamber temperature and its target together."""
    state = PrinterState.from_report(_report("h2d_status.json"), PrinterModel.H2D)

    assert state.print_state is PrintState.PAUSED
    assert state.chamber_temperature == 35
    assert state.nozzle_temperature == 245
    assert state.chamber_light_on is True


def test_state_without_a_known_model_keeps_the_chamber_temperature() -> None:
    """Only a known model is known to have no chamber sensor."""
    state = PrinterState.from_report(_report("p1s_status.json"))

    assert state.chamber_temperature == 5


def test_state_of_an_empty_report() -> None:
    """Nothing is known when the printer reports nothing."""
    assert PrinterState.from_report({}) == PrinterState()


@pytest.mark.parametrize(
    "report",
    [
        {"gcode_state": "DANCING"},
        {"gcode_state": "OFFLINE"},
        {"gcode_state": None},
        {"subtask_name": 5},
        {"subtask_name": "   "},
        {"mc_percent": "many"},
        {"mc_percent": True},
        {"mc_percent": float("nan")},
        {"mc_percent": "nan"},
        {"mc_remaining_time": float("inf")},
        {"nozzle_temper": float("-inf")},
        {"mc_remaining_time": None},
        {"nozzle_temper": [1]},
        {"spd_lvl": 9},
        {"spd_lvl": "fast"},
        {"wifi_signal": "strong"},
        {"wifi_signal": None},
        {"lights_report": "on"},
        {"lights_report": ["on", {"node": "work_light", "mode": "on"}]},
        {"device": None},
        {"device": {"ctc": None}},
        {"device": {"ctc": {"info": {}}}},
        {"device": {"ctc": {"info": {"temp": "warm"}}}},
    ],
)
def test_state_ignores_values_it_does_not_understand(report: dict[str, Any]) -> None:
    """A value of an unexpected type or meaning is not known."""
    assert PrinterState.from_report(report) == PrinterState()


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        ({"mc_percent": "37"}, PrinterState(progress=37)),
        ({"mc_percent": 37.9}, PrinterState(progress=37)),
        ({"wifi_signal": -61}, PrinterState(wifi_signal=-61)),
        ({"bed_temper": "60.6"}, PrinterState(bed_temperature=61)),
        ({"bed_temper": 59.4}, PrinterState(bed_temperature=59)),
        ({"gcode_state": "finish"}, PrinterState(print_state=PrintState.FINISHED)),
        (
            {"lights_report": [{"node": "chamber_light", "mode": "flashing"}]},
            PrinterState(chamber_light_on=True),
        ),
    ],
)
def test_state_accepts_values_in_other_notations(
    report: dict[str, Any], expected: PrinterState
) -> None:
    """Printers do not agree on numbers as text, or on capitals."""
    assert PrinterState.from_report(report) == expected


def test_info_of_a_printer_that_reports_its_product_name() -> None:
    """Newer firmware reports the name of the product."""
    assert _info("p1s_version.json") == PrinterInfo(
        serial=SERIAL,
        model=PrinterModel.P1S,
        model_name="P1S",
        firmware_version="01.08.02.00",
        hardware_version="AP04",
    )


def test_info_of_a_printer_without_a_mainboard_module() -> None:
    """Not every printer reports a mainboard."""
    assert _info("h2d_version.json") == PrinterInfo(
        serial=SERIAL,
        model=PrinterModel.H2D,
        model_name="H2D",
        firmware_version="01.01.01.00",
        hardware_version=None,
    )


def test_info_of_a_printer_with_older_firmware() -> None:
    """Older firmware only reports its hardware, which tells the model."""
    assert _info("x1c_version.json") == PrinterInfo(
        serial=SERIAL,
        model=PrinterModel.X1C,
        model_name="X1 Carbon",
        firmware_version="01.07.00.00",
        hardware_version="AP05",
    )


@pytest.mark.parametrize(
    ("hardware_version", "project_name", "model"),
    [
        ("AP02", "", PrinterModel.X1E),
        ("AP04", "C11", PrinterModel.P1P),
        ("AP04", "C12", PrinterModel.P1S),
        ("AP04", "N1", PrinterModel.A1_MINI),
        ("AP05", "N1", PrinterModel.A1_MINI),
        ("AP05", "N2S", PrinterModel.A1),
        ("AP05", "", PrinterModel.X1C),
        ("AP09", "", None),
    ],
)
def test_info_tells_the_model_from_the_hardware(
    hardware_version: str, project_name: str, model: PrinterModel | None
) -> None:
    """The mainboard and the project name tell which printer it is."""
    info = PrinterInfo.from_modules(
        SERIAL,
        [
            {"name": "ota", "sw_ver": "01.04.00.00", "hw_ver": "OTA"},
            {
                "name": "esp32",
                "project_name": project_name,
                "sw_ver": "01.07.23.47",
                "hw_ver": hardware_version,
            },
        ],
    )

    assert info.model is model
    assert info.model_name == (model.value if model else None)
    assert info.hardware_version == hardware_version


@pytest.mark.parametrize(
    ("product_name", "model", "model_name"),
    [
        ("Bambu Lab A1 mini", PrinterModel.A1_MINI, "A1 mini"),
        ("Bambu Lab H2D Pro", PrinterModel.H2D_PRO, "H2D Pro"),
        ("Bambu Lab X1-Carbon", PrinterModel.X1C, "X1 Carbon"),
        ("Bambu Lab Z9", None, "Z9"),
        ("Something else", None, "Something else"),
    ],
)
def test_info_tells_the_model_from_the_product_name(
    product_name: str, model: PrinterModel | None, model_name: str
) -> None:
    """A printer this library does not know yet keeps the name it reports."""
    info = PrinterInfo.from_modules(
        SERIAL, [{"name": "ota", "sw_ver": "01.00.00.00", "product_name": product_name}]
    )

    assert info.model is model
    assert info.model_name == model_name


@pytest.mark.parametrize("modules", [None, "ota", [], ["ota", 5], [{"name": "mc"}]])
def test_info_without_usable_modules(modules: Any) -> None:
    """Nothing is known about a printer that reports no usable modules."""
    assert PrinterInfo.from_modules(SERIAL, modules) == PrinterInfo(serial=SERIAL)


@pytest.mark.parametrize(
    ("reported", "state"),
    [
        ("IDLE", PrintState.IDLE),
        ("INIT", PrintState.INITIALIZING),
        ("SLICING", PrintState.SLICING),
        ("PREPARE", PrintState.PREPARING),
        ("RUNNING", PrintState.PRINTING),
        ("PAUSE", PrintState.PAUSED),
        ("FINISH", PrintState.FINISHED),
        ("FAILED", PrintState.FAILED),
    ],
)
def test_print_states(reported: str, state: PrintState) -> None:
    """Every state of a print job has a name that says what it is."""
    assert PrinterState.from_report({"gcode_state": reported}).print_state is state


@pytest.mark.parametrize(
    ("report", "accepts_commands"),
    [
        ({}, True),
        # Developer mode is on, and off.
        ({"fun": "3EC18FFF9CFF"}, True),
        ({"fun": "3EC1AFFF9CFF"}, False),
        # What "fun" tells counts, when the printer reports it.
        ({"fun": "3EC18FFF9CFF", "flag3": 671}, True),
        ({"fun": "", "flag3": 671}, False),
        ({"fun": "", "flag3": 15}, True),
        ({"flag3": 31}, False),
        ({"fun": "no number", "flag3": 31}, True),
        ({"fun": 5, "flag3": "no number"}, True),
    ],
)
def test_accepts_commands(report: dict[str, Any], accepts_commands: bool) -> None:  # noqa: FBT001
    """Newer firmware tells when it only accepts commands in developer mode."""
    assert PrinterState.from_report(report).accepts_commands is accepts_commands
