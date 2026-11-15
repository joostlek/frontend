"""Models for aiobambulab."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Any, Final, Self


class PrinterModel(StrEnum):
    """The printer models this library knows."""

    A1 = "A1"
    A1_MINI = "A1 mini"
    A2L = "A2L"
    H2C = "H2C"
    H2D = "H2D"
    H2D_PRO = "H2D Pro"
    H2S = "H2S"
    H3C = "H3C"
    P1P = "P1P"
    P1S = "P1S"
    P2S = "P2S"
    X1C = "X1 Carbon"
    X1E = "X1E"
    X2D = "X2D"


class PrintState(StrEnum):
    """What the printer is doing with its print job."""

    IDLE = "idle"
    INITIALIZING = "initializing"
    SLICING = "slicing"
    PREPARING = "preparing"
    PRINTING = "printing"
    PAUSED = "paused"
    FINISHED = "finished"
    FAILED = "failed"


class SpeedProfile(StrEnum):
    """The speed profile of the printer."""

    SILENT = "silent"
    STANDARD = "standard"
    SPORT = "sport"
    LUDICROUS = "ludicrous"


_PRODUCT_NAME_PREFIX: Final = "Bambu Lab "

# Product names that differ from the name of the model.
_MODEL_ALIASES: Final = {"X1-Carbon": PrinterModel.X1C}

# These models report a chamber temperature, but have no sensor to measure it.
_MODELS_WITHOUT_CHAMBER_SENSOR: Final = frozenset(
    {
        PrinterModel.A1,
        PrinterModel.A1_MINI,
        PrinterModel.A2L,
        PrinterModel.P1P,
        PrinterModel.P1S,
    }
)

# The states of a print job, as a printer reports them.
_PRINT_STATES: Final = {
    "IDLE": PrintState.IDLE,
    "INIT": PrintState.INITIALIZING,
    "SLICING": PrintState.SLICING,
    "PREPARE": PrintState.PREPARING,
    "RUNNING": PrintState.PRINTING,
    "PAUSE": PrintState.PAUSED,
    "FINISH": PrintState.FINISHED,
    "FAILED": PrintState.FAILED,
}

_SPEED_PROFILES: Final = {
    1: SpeedProfile.SILENT,
    2: SpeedProfile.STANDARD,
    3: SpeedProfile.SPORT,
    4: SpeedProfile.LUDICROUS,
}

_CHAMBER_LIGHT: Final = "chamber_light"


def _as_float(value: Any) -> float | None:
    """Return the value as a float, or None if it is not a finite number."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_int(value: Any) -> int | None:
    """Return the value as an integer, or None if it is not a number."""
    number = _as_float(value)
    return None if number is None else int(number)


def _as_degrees(value: Any) -> int | None:
    """Return a temperature in whole degrees, like the printer shows it.

    Some printers report temperatures in steps of 1/32 degree. That is more
    than their sensors can tell, and it changes with every report.
    """
    number = _as_float(value)
    return None if number is None else round(number)


def _as_text(value: Any) -> str | None:
    """Return the value as text, or None if it is empty or not text."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _model_from_hardware(
    hardware_version: str, project_name: str
) -> PrinterModel | None:
    """Return the model of a printer that does not report its product name."""
    if hardware_version == "AP02":
        return PrinterModel.X1E
    if project_name == "N1":
        return PrinterModel.A1_MINI
    return {
        ("AP04", "C11"): PrinterModel.P1P,
        ("AP04", "C12"): PrinterModel.P1S,
        ("AP05", "N2S"): PrinterModel.A1,
        ("AP05", ""): PrinterModel.X1C,
    }.get((hardware_version, project_name))


@dataclass(frozen=True, slots=True, kw_only=True)
class PrinterInfo:
    """What a printer is: its model and its versions."""

    serial: str
    model: PrinterModel | None = None
    model_name: str | None = None
    firmware_version: str | None = None
    hardware_version: str | None = None

    @classmethod
    def from_modules(cls, serial: str, modules: Any) -> Self:
        """Create the info from the modules a printer reports for its version."""
        if not isinstance(modules, list):
            modules = []
        modules = [module for module in modules if isinstance(module, dict)]
        ota: dict[str, Any] = next(
            (mod for mod in modules if mod.get("name") == "ota"), {}
        )
        # The mainboard is the module with an "AP" hardware version.
        board: dict[str, Any] = next(
            (mod for mod in modules if str(mod.get("hw_ver", "")).startswith("AP")),
            {},
        )
        hardware_version = _as_text(board.get("hw_ver"))

        model: PrinterModel | None = None
        model_name = _as_text(ota.get("product_name"))
        if model_name is not None:
            model_name = model_name.removeprefix(_PRODUCT_NAME_PREFIX)
            try:
                model = PrinterModel(model_name)
            except ValueError:
                model = _MODEL_ALIASES.get(model_name)
        elif hardware_version is not None:
            # Older firmware does not report a product name.
            model = _model_from_hardware(
                hardware_version, str(board.get("project_name", ""))
            )
        if model is not None:
            model_name = model.value

        return cls(
            serial=serial,
            model=model,
            model_name=model_name,
            firmware_version=_as_text(ota.get("sw_ver")),
            hardware_version=hardware_version,
        )


def _chamber_temperature(
    report: dict[str, Any], model: PrinterModel | None
) -> int | None:
    """Return the temperature of the chamber, if the printer measures it."""
    if model in _MODELS_WITHOUT_CHAMBER_SENSOR:
        return None
    if (temperature := _as_degrees(report.get("chamber_temper"))) is not None:
        return temperature
    # Newer firmware reports the chamber as a device. The low 16 bits hold
    # the current temperature, the high 16 bits hold the target.
    try:
        packed = report["device"]["ctc"]["info"]["temp"]
    except (KeyError, TypeError):
        return None
    if (value := _as_int(packed)) is None:
        return None
    return value & 0xFFFF


def _chamber_light_on(report: dict[str, Any]) -> bool | None:
    """Return whether the light in the chamber is on."""
    lights = report.get("lights_report")
    if not isinstance(lights, list):
        return None
    for light in lights:
        if isinstance(light, dict) and light.get("node") == _CHAMBER_LIGHT:
            return bool(light.get("mode") != "off")
    return None


def _print_state(report: dict[str, Any]) -> PrintState | None:
    """Return the state of the print job."""
    return _PRINT_STATES.get(str(report.get("gcode_state")).upper())


def _wifi_signal(report: dict[str, Any]) -> int | None:
    """Return the Wi-Fi signal strength in dBm."""
    signal = report.get("wifi_signal")
    if isinstance(signal, str):
        signal = signal.removesuffix("dBm")
    return _as_int(signal)


@dataclass(frozen=True, slots=True, kw_only=True)
class PrinterState:
    """What a printer is doing right now.

    A value is None when the printer does not report it. Temperatures are in
    whole degrees Celsius.
    """

    print_state: PrintState | None = None
    job_name: str | None = None
    progress: int | None = None
    remaining_minutes: int | None = None
    current_layer: int | None = None
    total_layers: int | None = None
    nozzle_temperature: int | None = None
    nozzle_target_temperature: int | None = None
    bed_temperature: int | None = None
    bed_target_temperature: int | None = None
    chamber_temperature: int | None = None
    speed_profile: SpeedProfile | None = None
    chamber_light_on: bool | None = None
    wifi_signal: int | None = None

    @classmethod
    def from_report(
        cls, report: dict[str, Any], model: PrinterModel | None = None
    ) -> Self:
        """Create the state from the status a printer reports.

        Printers with two nozzles report the temperatures of the active one.
        """
        speed_level = _as_int(report.get("spd_lvl"))
        return cls(
            print_state=_print_state(report),
            job_name=_as_text(report.get("subtask_name")),
            progress=_as_int(report.get("mc_percent")),
            remaining_minutes=_as_int(report.get("mc_remaining_time")),
            current_layer=_as_int(report.get("layer_num")),
            total_layers=_as_int(report.get("total_layer_num")),
            nozzle_temperature=_as_degrees(report.get("nozzle_temper")),
            nozzle_target_temperature=_as_degrees(report.get("nozzle_target_temper")),
            bed_temperature=_as_degrees(report.get("bed_temper")),
            bed_target_temperature=_as_degrees(report.get("bed_target_temper")),
            chamber_temperature=_chamber_temperature(report, model),
            speed_profile=(
                None if speed_level is None else _SPEED_PROFILES.get(speed_level)
            ),
            chamber_light_on=_chamber_light_on(report),
            wifi_signal=_wifi_signal(report),
        )
