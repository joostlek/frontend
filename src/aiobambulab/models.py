"""Models for aiobambulab."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Any, Final, Self

from .stages import STAGES, PrintStage


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


class Fan(StrEnum):
    """The fans of a printer that can be set to a speed."""

    PART_COOLING = "part_cooling"
    AUXILIARY = "auxiliary"
    CHAMBER = "chamber"


class ErrorSeverity(StrEnum):
    """How bad a problem is that the printer reports."""

    FATAL = "fatal"
    SERIOUS = "serious"
    COMMON = "common"
    INFO = "info"


_PRODUCT_NAME_PREFIX: Final = "Bambu Lab "

# Product names that differ from the name of the model.
_MODEL_ALIASES: Final = {"X1-Carbon": PrinterModel.X1C}

# These models have no video stream: they send images of their camera.
MODELS_WITH_CAMERA_IMAGES: Final = frozenset(
    {
        PrinterModel.A1,
        PrinterModel.A1_MINI,
        PrinterModel.A2L,
        PrinterModel.P1P,
        PrinterModel.P1S,
    }
)

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

SPEED_PROFILES: Final = {
    1: SpeedProfile.SILENT,
    2: SpeedProfile.STANDARD,
    3: SpeedProfile.SPORT,
    4: SpeedProfile.LUDICROUS,
}

_CHAMBER_LIGHT: Final = "chamber_light"

_ERROR_SEVERITIES: Final = {
    1: ErrorSeverity.FATAL,
    2: ErrorSeverity.SERIOUS,
    3: ErrorSeverity.COMMON,
    4: ErrorSeverity.INFO,
}

# A printer reports the speed of a fan as a level up to this one.
_MAX_FAN_LEVEL: Final = 15

# What a printer reports as the tray it prints from, when that is not a tray
# of an AMS.
_EXTERNAL_SPOOL: Final = 254
# An AMS with one tray has an id from this number on, and is the tray itself.
_FIRST_SINGLE_TRAY_AMS: Final = 128
_TRAYS_PER_AMS: Final = 4

# How a printer tells that it only accepts commands that are signed.
_FUN_SIGNATURE_REQUIRED: Final = 0x20000000
_FLAG3_AUTHORIZATION_CONTROL: Final = 0x10


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


@dataclass(frozen=True, slots=True, kw_only=True)
class PrinterError:
    """A problem the printer reports, which Bambu Lab calls an HMS code.

    The code is the one to look up at Bambu Lab, like `0300_0100_0001_0007`.
    """

    code: str
    severity: ErrorSeverity | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Filament:
    """The filament on a spool.

    The color is `RRGGBBAA`. What remains is a percentage, and only known for
    a spool with a tag of Bambu Lab.
    """

    type: str | None = None
    name: str | None = None
    color: str | None = None
    remaining: int | None = None
    nozzle_temperature_min: int | None = None
    nozzle_temperature_max: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AmsTray:
    """A tray of an AMS. The filament is None when the tray is empty."""

    id: int
    filament: Filament | None = None
    active: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class Ams:
    """An AMS: the unit that feeds filament to the printer.

    The humidity index is the level from 1 to 5 that the printer shows. Newer
    units also report the humidity as a percentage.
    """

    id: int
    humidity_index: int | None = None
    humidity: int | None = None
    temperature: float | None = None
    trays: tuple[AmsTray, ...] = ()


def _fan_speed(value: Any) -> int | None:
    """Return the speed of a fan as a percentage, in steps of ten.

    The level a printer reports wavers between two neighbors for one speed.
    Rounding up to the step the speed is set in keeps it steady.
    """
    level = _as_int(value)
    if level is None or not 0 <= level <= _MAX_FAN_LEVEL:
        return None
    return -(-level * 10 // _MAX_FAN_LEVEL) * 10


def _print_error(report: dict[str, Any]) -> str | None:
    """Return the code of the error of the print job, like `0700_8006`."""
    if not (code := _as_int(report.get("print_error"))) or code < 0:
        return None
    text = f"{code:08X}"
    return f"{text[:4]}_{text[4:]}"


def _errors(report: dict[str, Any]) -> tuple[PrinterError, ...]:
    """Return the problems the printer reports."""
    entries = report.get("hms")
    if not isinstance(entries, list):
        return ()
    errors = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        attr = _as_int(entry.get("attr"))
        code = _as_int(entry.get("code"))
        if not attr or not code or attr < 0 or code < 0:
            continue
        errors.append(
            PrinterError(
                code=(
                    f"{attr >> 16:04X}_{attr & 0xFFFF:04X}"
                    f"_{code >> 16:04X}_{code & 0xFFFF:04X}"
                ),
                severity=_ERROR_SEVERITIES.get(code >> 16),
            )
        )
    return tuple(errors)


def _color(value: Any) -> str | None:
    """Return a color as `RRGGBBAA`, or None if it is not one."""
    color = _as_text(value)
    if color is None or len(color) != 8:  # noqa: PLR2004
        return None
    try:
        int(color, 16)
    except ValueError:
        return None
    return color.upper()


def _filament(tray: Any) -> Filament | None:
    """Return the filament of a tray, or None if the tray is empty."""
    if not isinstance(tray, dict):
        return None
    kind = _as_text(tray.get("tray_type"))
    if kind is None and _as_text(tray.get("tray_info_idx")) is None:
        # An empty tray only has an id.
        return None
    remaining = _as_int(tray.get("remain"))
    return Filament(
        type=kind,
        name=_as_text(tray.get("tray_sub_brands")),
        color=_color(tray.get("tray_color")),
        remaining=(
            remaining if remaining is not None and 0 <= remaining <= 100 else None  # noqa: PLR2004
        ),
        nozzle_temperature_min=_as_int(tray.get("nozzle_temp_min")) or None,
        nozzle_temperature_max=_as_int(tray.get("nozzle_temp_max")) or None,
    )


def _active_tray(report: dict[str, Any]) -> int | None:
    """Return the number of the tray the printer prints from, as it reports it."""
    ams = report.get("ams")
    return _as_int(ams.get("tray_now")) if isinstance(ams, dict) else None


def _is_active(active_tray: int | None, ams_id: int, tray_id: int) -> bool:
    """Return whether a tray is the one the printer prints from."""
    if active_tray is None or active_tray >= _EXTERNAL_SPOOL:
        return False
    if active_tray >= _FIRST_SINGLE_TRAY_AMS:
        return active_tray == ams_id
    return divmod(active_tray, _TRAYS_PER_AMS) == (ams_id, tray_id)


def _in_range(value: int | None, low: int, high: int) -> int | None:
    """Return the value if it is in the range, and None if not."""
    return value if value is not None and low <= value <= high else None


def _ams(report: dict[str, Any]) -> tuple[Ams, ...]:
    """Return the AMS units of the printer."""
    ams = report.get("ams")
    units = ams.get("ams") if isinstance(ams, dict) else None
    if not isinstance(units, list):
        return ()
    active_tray = _active_tray(report)
    result = []
    for unit in units:
        if not isinstance(unit, dict) or (ams_id := _as_int(unit.get("id"))) is None:
            continue
        trays = unit.get("tray")
        result.append(
            Ams(
                id=ams_id,
                humidity_index=_in_range(_as_int(unit.get("humidity")), 1, 5),
                humidity=_in_range(_as_int(unit.get("humidity_raw")), 0, 100),
                temperature=_as_float(unit.get("temp")),
                trays=tuple(
                    AmsTray(
                        id=tray_id,
                        filament=_filament(tray),
                        active=_is_active(active_tray, ams_id, tray_id),
                    )
                    for tray in (trays if isinstance(trays, list) else [])
                    if isinstance(tray, dict)
                    and (tray_id := _as_int(tray.get("id"))) is not None
                ),
            )
        )
    return tuple(result)


def _enabled(value: Any) -> bool | None:
    """Return whether something is enabled, the way a printer reports that."""
    return {"enable": True, "disable": False}.get(value) if value else None


def _camera_setting(report: dict[str, Any], setting: str) -> bool | None:
    """Return whether a setting of the camera is enabled."""
    ipcam = report.get("ipcam")
    return _enabled(ipcam.get(setting)) if isinstance(ipcam, dict) else None


def _available_firmware_version(report: dict[str, Any]) -> str | None:
    """Return the version of the firmware that the printer can update to."""
    upgrade = report.get("upgrade_state")
    if not isinstance(upgrade, dict):
        return None
    if (version := _as_text(upgrade.get("ota_new_version_number"))) is not None:
        return version
    # Some printers list the new versions of all their parts.
    versions = upgrade.get("new_ver_list")
    for part in versions if isinstance(versions, list) else []:
        if isinstance(part, dict) and part.get("name") == "ota":
            return _as_text(part.get("new_ver"))
    return None


def _stage(report: dict[str, Any], print_state: PrintState | None) -> PrintStage | None:
    """Return what the printer is doing right now."""
    stage = _as_int(report.get("stg_cur"))
    # A printer keeps the stage of a print job that failed, and reports
    # printing when it starts up. Neither is what it is doing.
    if print_state is PrintState.FAILED or (
        stage == 0 and report.get("print_type") == "idle"
    ):
        return PrintStage.IDLE
    return None if stage is None else STAGES.get(stage)


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


def _accepts_commands(report: dict[str, Any]) -> bool:
    """Return whether the printer accepts commands that control it."""
    fun = report.get("fun")
    if isinstance(fun, str) and fun:
        try:
            return not int(fun, 16) & _FUN_SIGNATURE_REQUIRED
        except ValueError:
            return True
    # Some firmware reports this elsewhere.
    flag3 = _as_int(report.get("flag3"))
    return flag3 is None or not flag3 & _FLAG3_AUTHORIZATION_CONTROL


def _camera_stream_enabled(report: dict[str, Any]) -> bool | None:
    """Return whether the printer serves its video stream on the network."""
    ipcam = report.get("ipcam")
    if not isinstance(ipcam, dict) or "rtsp_url" not in ipcam:
        return None
    # The printer reports where the stream is, or that it is disabled.
    return str(ipcam["rtsp_url"]).startswith(("rtsp://", "rtsps://"))


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

    Newer firmware only accepts commands when the printer is in developer
    mode. `accepts_commands` tells whether it does. The chamber light is the
    exception: a printer always accepts the command for it.

    `camera_stream_enabled` is None for a printer without a video stream. A
    printer that has one only serves it on the network when that is turned on
    on the printer.

    The speed of a fan is a percentage. `print_error` is the code of what went
    wrong with the print job, and `errors` are the problems the printer has.
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
    accepts_commands: bool = True
    camera_stream_enabled: bool | None = None
    stage: PrintStage | None = None
    speed_percentage: int | None = None
    part_fan_speed: int | None = None
    aux_fan_speed: int | None = None
    chamber_fan_speed: int | None = None
    heatbreak_fan_speed: int | None = None
    nozzle_diameter: float | None = None
    nozzle_type: str | None = None
    print_error: str | None = None
    errors: tuple[PrinterError, ...] = ()
    ams: tuple[Ams, ...] = ()
    external_spool: Filament | None = None
    external_spool_active: bool = False
    sd_card_present: bool | None = None
    timelapse_enabled: bool | None = None
    recording_enabled: bool | None = None
    available_firmware_version: str | None = None

    @classmethod
    def from_report(
        cls, report: dict[str, Any], model: PrinterModel | None = None
    ) -> Self:
        """Create the state from the status a printer reports.

        Printers with two nozzles report the temperatures of the active one.
        """
        speed_level = _as_int(report.get("spd_lvl"))
        print_state = _print_state(report)
        sd_card = report.get("sdcard")
        return cls(
            print_state=print_state,
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
                None if speed_level is None else SPEED_PROFILES.get(speed_level)
            ),
            chamber_light_on=_chamber_light_on(report),
            wifi_signal=_wifi_signal(report),
            accepts_commands=_accepts_commands(report),
            camera_stream_enabled=_camera_stream_enabled(report),
            stage=_stage(report, print_state),
            speed_percentage=_as_int(report.get("spd_mag")),
            part_fan_speed=_fan_speed(report.get("cooling_fan_speed")),
            aux_fan_speed=_fan_speed(report.get("big_fan1_speed")),
            chamber_fan_speed=_fan_speed(report.get("big_fan2_speed")),
            heatbreak_fan_speed=_fan_speed(report.get("heatbreak_fan_speed")),
            nozzle_diameter=_as_float(report.get("nozzle_diameter")) or None,
            nozzle_type=_as_text(report.get("nozzle_type")),
            print_error=_print_error(report),
            errors=_errors(report),
            ams=_ams(report),
            external_spool=_filament(report.get("vt_tray")),
            external_spool_active=_active_tray(report) == _EXTERNAL_SPOOL,
            sd_card_present=sd_card if isinstance(sd_card, bool) else None,
            timelapse_enabled=_camera_setting(report, "timelapse"),
            recording_enabled=_camera_setting(report, "ipcam_record"),
            available_firmware_version=_available_firmware_version(report),
        )
