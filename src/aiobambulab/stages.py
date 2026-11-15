"""The stages of a print job.

A print job is more than printing: the printer heats up, levels its bed,
changes filament, and can pause for a reason. The printer reports what it is
doing as a number.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class PrintStage(StrEnum):
    """What the printer is doing right now."""

    IDLE = "idle"
    PRINTING = "printing"
    AUTO_BED_LEVELING = "auto_bed_leveling"
    HEATBED_PREHEATING = "heatbed_preheating"
    SWEEPING_XY_MECH_MODE = "sweeping_xy_mech_mode"
    CHANGING_FILAMENT = "changing_filament"
    M400_PAUSE = "m400_pause"
    PAUSED_FILAMENT_RUNOUT = "paused_filament_runout"
    HEATING_HOTEND = "heating_hotend"
    CALIBRATING_EXTRUSION = "calibrating_extrusion"
    SCANNING_BED_SURFACE = "scanning_bed_surface"
    INSPECTING_FIRST_LAYER = "inspecting_first_layer"
    IDENTIFYING_BUILD_PLATE_TYPE = "identifying_build_plate_type"
    CALIBRATING_MICRO_LIDAR = "calibrating_micro_lidar"
    HOMING_TOOLHEAD = "homing_toolhead"
    CLEANING_NOZZLE_TIP = "cleaning_nozzle_tip"
    CHECKING_EXTRUDER_TEMPERATURE = "checking_extruder_temperature"
    PAUSED_USER = "paused_user"
    PAUSED_FRONT_COVER_FALLING = "paused_front_cover_falling"
    CALIBRATING_EXTRUSION_FLOW = "calibrating_extrusion_flow"
    PAUSED_NOZZLE_TEMPERATURE_MALFUNCTION = "paused_nozzle_temperature_malfunction"
    PAUSED_HEAT_BED_TEMPERATURE_MALFUNCTION = "paused_heat_bed_temperature_malfunction"
    FILAMENT_UNLOADING = "filament_unloading"
    PAUSED_SKIPPED_STEP = "paused_skipped_step"
    FILAMENT_LOADING = "filament_loading"
    CALIBRATING_MOTOR_NOISE = "calibrating_motor_noise"
    PAUSED_AMS_LOST = "paused_ams_lost"
    PAUSED_LOW_FAN_SPEED_HEAT_BREAK = "paused_low_fan_speed_heat_break"
    PAUSED_CHAMBER_TEMPERATURE_CONTROL_ERROR = (
        "paused_chamber_temperature_control_error"
    )
    COOLING_CHAMBER = "cooling_chamber"
    PAUSED_USER_GCODE = "paused_user_gcode"
    MOTOR_NOISE_SHOWOFF = "motor_noise_showoff"
    PAUSED_NOZZLE_FILAMENT_COVERED_DETECTED = "paused_nozzle_filament_covered_detected"
    PAUSED_CUTTER_ERROR = "paused_cutter_error"
    PAUSED_FIRST_LAYER_ERROR = "paused_first_layer_error"
    PAUSED_NOZZLE_CLOG = "paused_nozzle_clog"
    CHECK_ABSOLUTE_ACCURACY_BEFORE_CALIBRATION = (
        "check_absolute_accuracy_before_calibration"
    )
    ABSOLUTE_ACCURACY_CALIBRATION = "absolute_accuracy_calibration"
    CHECK_ABSOLUTE_ACCURACY_AFTER_CALIBRATION = (
        "check_absolute_accuracy_after_calibration"
    )
    CALIBRATE_NOZZLE_OFFSET = "calibrate_nozzle_offset"
    BED_LEVEL_HIGH_TEMPERATURE = "bed_level_high_temperature"
    CHECK_QUICK_RELEASE = "check_quick_release"
    CHECK_DOOR_AND_COVER = "check_door_and_cover"
    LASER_CALIBRATION = "laser_calibration"
    CHECK_PLATFORM = "check_platform"
    CHECK_BIRDEYE_CAMERA_POSITION = "check_birdeye_camera_position"
    CALIBRATE_BIRDEYE_CAMERA = "calibrate_birdeye_camera"
    BED_LEVEL_PHASE_1 = "bed_level_phase_1"
    BED_LEVEL_PHASE_2 = "bed_level_phase_2"
    HEATING_CHAMBER = "heating_chamber"
    HEATBED_COOLING = "heatbed_cooling"
    PRINT_CALIBRATION_LINES = "print_calibration_lines"
    CHECK_MATERIAL = "check_material"
    CALIBRATING_LIVE_VIEW_CAMERA = "calibrating_live_view_camera"
    WAITING_FOR_HEATBED_TEMPERATURE = "waiting_for_heatbed_temperature"
    CHECK_MATERIAL_POSITION = "check_material_position"
    CALIBRATING_CUTTER_MODEL_OFFSET = "calibrating_cutter_model_offset"
    MEASURING_SURFACE = "measuring_surface"
    THERMAL_PRECONDITIONING = "thermal_preconditioning"
    HOMING_BLADE_HOLDER = "homing_blade_holder"
    CALIBRATING_CAMERA_OFFSET = "calibrating_camera_offset"
    CALIBRATING_BLADE_HOLDER_POSITION = "calibrating_blade_holder_position"
    HOTEND_PICK_PLACE_TEST = "hotend_pick_place_test"
    WAITING_CHAMBER_TEMPERATURE_EQUALIZE = "waiting_chamber_temperature_equalize"
    PREPARING_HOTEND = "preparing_hotend"
    CALIBRATING_DETECTION_NOZZLE_CLUMPING = "calibrating_detection_nozzle_clumping"
    PURIFYING_CHAMBER_AIR = "purifying_chamber_air"
    MEASURING_ROTARY_ATTACHMENT = "measuring_rotary_attachment"
    MOVING_TOOLHEAD_ABOVE_PURGE_CHUTE = "moving_toolhead_above_purge_chute"
    COOLING_NOZZLE = "cooling_nozzle"
    MOVING_TOOLHEAD_TO_CENTER_OF_HEATBED = "moving_toolhead_to_center_of_heatbed"
    ACTIVE_ARC_FITTING = "active_arc_fitting"
    HOTEND_TYPE_DETECTION = "hotend_type_detection"
    BUILD_PLATE_ALIGNMENT_DETECTION = "build_plate_alignment_detection"
    HEATBED_SURFACE_FOREIGN_OBJECT_DETECTION = (
        "heatbed_surface_foreign_object_detection"
    )
    HEATBED_UNDERSIDE_FOREIGN_OBJECT_DETECTION = (
        "heatbed_underside_foreign_object_detection"
    )
    PRE_EXTRUSION_BEFORE_PRINTING = "pre_extrusion_before_printing"
    PREPARING_AMS = "preparing_ams"
    HEATBED_STABILIZING = "heatbed_stabilizing"


# The number a printer reports for each stage. Some printers use -1 for idle,
# others 255.
STAGES: Final = {
    -1: PrintStage.IDLE,
    0: PrintStage.PRINTING,
    1: PrintStage.AUTO_BED_LEVELING,
    2: PrintStage.HEATBED_PREHEATING,
    3: PrintStage.SWEEPING_XY_MECH_MODE,
    4: PrintStage.CHANGING_FILAMENT,
    5: PrintStage.M400_PAUSE,
    6: PrintStage.PAUSED_FILAMENT_RUNOUT,
    7: PrintStage.HEATING_HOTEND,
    8: PrintStage.CALIBRATING_EXTRUSION,
    9: PrintStage.SCANNING_BED_SURFACE,
    10: PrintStage.INSPECTING_FIRST_LAYER,
    11: PrintStage.IDENTIFYING_BUILD_PLATE_TYPE,
    12: PrintStage.CALIBRATING_MICRO_LIDAR,
    13: PrintStage.HOMING_TOOLHEAD,
    14: PrintStage.CLEANING_NOZZLE_TIP,
    15: PrintStage.CHECKING_EXTRUDER_TEMPERATURE,
    16: PrintStage.PAUSED_USER,
    17: PrintStage.PAUSED_FRONT_COVER_FALLING,
    18: PrintStage.CALIBRATING_MICRO_LIDAR,
    19: PrintStage.CALIBRATING_EXTRUSION_FLOW,
    20: PrintStage.PAUSED_NOZZLE_TEMPERATURE_MALFUNCTION,
    21: PrintStage.PAUSED_HEAT_BED_TEMPERATURE_MALFUNCTION,
    22: PrintStage.FILAMENT_UNLOADING,
    23: PrintStage.PAUSED_SKIPPED_STEP,
    24: PrintStage.FILAMENT_LOADING,
    25: PrintStage.CALIBRATING_MOTOR_NOISE,
    26: PrintStage.PAUSED_AMS_LOST,
    27: PrintStage.PAUSED_LOW_FAN_SPEED_HEAT_BREAK,
    28: PrintStage.PAUSED_CHAMBER_TEMPERATURE_CONTROL_ERROR,
    29: PrintStage.COOLING_CHAMBER,
    30: PrintStage.PAUSED_USER_GCODE,
    31: PrintStage.MOTOR_NOISE_SHOWOFF,
    32: PrintStage.PAUSED_NOZZLE_FILAMENT_COVERED_DETECTED,
    33: PrintStage.PAUSED_CUTTER_ERROR,
    34: PrintStage.PAUSED_FIRST_LAYER_ERROR,
    35: PrintStage.PAUSED_NOZZLE_CLOG,
    36: PrintStage.CHECK_ABSOLUTE_ACCURACY_BEFORE_CALIBRATION,
    37: PrintStage.ABSOLUTE_ACCURACY_CALIBRATION,
    38: PrintStage.CHECK_ABSOLUTE_ACCURACY_AFTER_CALIBRATION,
    39: PrintStage.CALIBRATE_NOZZLE_OFFSET,
    40: PrintStage.BED_LEVEL_HIGH_TEMPERATURE,
    41: PrintStage.CHECK_QUICK_RELEASE,
    42: PrintStage.CHECK_DOOR_AND_COVER,
    43: PrintStage.LASER_CALIBRATION,
    44: PrintStage.CHECK_PLATFORM,
    45: PrintStage.CHECK_BIRDEYE_CAMERA_POSITION,
    46: PrintStage.CALIBRATE_BIRDEYE_CAMERA,
    47: PrintStage.BED_LEVEL_PHASE_1,
    48: PrintStage.BED_LEVEL_PHASE_2,
    49: PrintStage.HEATING_CHAMBER,
    50: PrintStage.HEATBED_COOLING,
    51: PrintStage.PRINT_CALIBRATION_LINES,
    52: PrintStage.CHECK_MATERIAL,
    53: PrintStage.CALIBRATING_LIVE_VIEW_CAMERA,
    54: PrintStage.WAITING_FOR_HEATBED_TEMPERATURE,
    55: PrintStage.CHECK_MATERIAL_POSITION,
    56: PrintStage.CALIBRATING_CUTTER_MODEL_OFFSET,
    57: PrintStage.MEASURING_SURFACE,
    58: PrintStage.THERMAL_PRECONDITIONING,
    59: PrintStage.HOMING_BLADE_HOLDER,
    60: PrintStage.CALIBRATING_CAMERA_OFFSET,
    61: PrintStage.CALIBRATING_BLADE_HOLDER_POSITION,
    62: PrintStage.HOTEND_PICK_PLACE_TEST,
    63: PrintStage.WAITING_CHAMBER_TEMPERATURE_EQUALIZE,
    64: PrintStage.PREPARING_HOTEND,
    65: PrintStage.CALIBRATING_DETECTION_NOZZLE_CLUMPING,
    66: PrintStage.PURIFYING_CHAMBER_AIR,
    67: PrintStage.MEASURING_ROTARY_ATTACHMENT,
    68: PrintStage.MOVING_TOOLHEAD_ABOVE_PURGE_CHUTE,
    69: PrintStage.COOLING_NOZZLE,
    70: PrintStage.MOVING_TOOLHEAD_TO_CENTER_OF_HEATBED,
    71: PrintStage.ACTIVE_ARC_FITTING,
    72: PrintStage.HOTEND_TYPE_DETECTION,
    73: PrintStage.BUILD_PLATE_ALIGNMENT_DETECTION,
    74: PrintStage.HEATBED_SURFACE_FOREIGN_OBJECT_DETECTION,
    75: PrintStage.HEATBED_UNDERSIDE_FOREIGN_OBJECT_DETECTION,
    76: PrintStage.PRE_EXTRUSION_BEFORE_PRINTING,
    77: PrintStage.PREPARING_AMS,
    82: PrintStage.HEATBED_STABILIZING,
    255: PrintStage.IDLE,
}
