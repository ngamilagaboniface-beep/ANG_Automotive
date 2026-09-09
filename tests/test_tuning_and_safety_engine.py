"""
Test Suite for AI Datalog Parser, Safety Bounds, and Calibration Optimization Engine.
Tests non-overridable safety triggers, table boundary checks, flex fuel math, and burble timing.
"""

import pytest
import numpy as np
from ang_telematics.flashing.rom_manager import ECURomPackage, CalibrationMap3D, ECUType
from ang_telematics.tuning_engine.safety_monitor import EngineSafetyMonitor, SafetyStatus
from ang_telematics.tuning_engine.datalog_analyzer import DatalogParser, DatalogAnalyzer, DatalogSession
from ang_telematics.tuning_engine.ai_calibrator import AICalibrator

def test_non_overridable_safety_triggers_multi_cylinder_knock():
    # Multi-cylinder knock retard > 3.0 deg -> Must trigger CRITICAL_REVERSION_REQUIRED
    frame = {
        "rpm": 5500.0,
        "pedal_pct": 100.0,
        "knock_retard": [3.5, 0.0, 3.2, 0.0, 0.0, 0.0], # 2 cylinders > 3.0 deg
        "coolant_c": 92.0,
        "oil_c": 95.0,
        "egt_c": 750.0,
        "boost_actual_hpa": 2200.0,
        "boost_target_hpa": 2200.0,
        "lambda_actual": 0.82
    }
    res = EngineSafetyMonitor.evaluate_telemetry_frame(frame)
    assert res["reversion_required"] is True
    assert res["status"] == SafetyStatus.CRITICAL_REVERSION_REQUIRED.value
    assert res["derate_factor"] <= 0.50

def test_non_overridable_safety_triggers_single_cylinder_knock():
    # Single cylinder knock > 5.0 deg -> Must trigger CRITICAL_REVERSION_REQUIRED
    frame = {
        "rpm": 5200.0,
        "pedal_pct": 100.0,
        "knock_retard": [0.0, 5.5, 0.0, 0.0, 0.0, 0.0],
        "coolant_c": 90.0,
        "oil_c": 95.0,
        "egt_c": 700.0,
        "boost_actual_hpa": 2100.0,
        "boost_target_hpa": 2100.0,
        "lambda_actual": 0.82
    }
    res = EngineSafetyMonitor.evaluate_telemetry_frame(frame)
    assert res["reversion_required"] is True
    assert res["status"] == SafetyStatus.CRITICAL_REVERSION_REQUIRED.value

def test_non_overridable_safety_thermal_derating():
    # Coolant > 112 deg C
    frame_coolant = {"coolant_c": 115.0, "oil_c": 100.0, "egt_c": 700.0}
    res_c = EngineSafetyMonitor.evaluate_telemetry_frame(frame_coolant)
    assert res_c["derating_active"] is True
    assert res_c["derate_factor"] <= 0.70

    # Oil > 130 deg C
    frame_oil = {"coolant_c": 95.0, "oil_c": 133.0, "egt_c": 700.0}
    res_o = EngineSafetyMonitor.evaluate_telemetry_frame(frame_oil)
    assert res_o["derating_active"] is True
    assert res_o["derate_factor"] <= 0.75

    # EGT > 950 deg C
    frame_egt = {"coolant_c": 95.0, "oil_c": 100.0, "egt_c": 970.0}
    res_e = EngineSafetyMonitor.evaluate_telemetry_frame(frame_egt)
    assert res_e["derating_active"] is True
    assert res_e["derate_factor"] <= 0.65

def test_non_overridable_safety_boost_and_lean_wot():
    # Boost overshoot > +350 hPa (0.35 bar)
    frame_boost = {"boost_actual_hpa": 2500.0, "boost_target_hpa": 2100.0} # +400 hPa overshoot
    res_b = EngineSafetyMonitor.evaluate_telemetry_frame(frame_boost)
    assert res_b["derating_active"] is True

    # WOT Lean mixture: Lambda 0.92 under 100% pedal
    frame_lean = {"pedal_pct": 100.0, "rpm": 4500.0, "lambda_actual": 0.92, "hpfp_bar": 200.0}
    res_l = EngineSafetyMonitor.evaluate_telemetry_frame(frame_lean)
    assert res_l["reversion_required"] is True
    assert "CRITICAL LEAN TRIPWIRE" in res_l["violations"][0]

def test_datalog_csv_parser_and_analyzer():
    csv_sample = """RPM,Pedal,Boost Target,Actual Boost,Lambda,Lambda Target,Timing,Knock Retard,WGDC,Coolant Temp,Oil Temp,EGT,HPFP,Ethanol
2000,10,1013,1013,1.00,1.00,28.0,0.0,0,90,92,500,200,10
3000,100,2100,2080,0.85,0.84,14.0,0.0,55,91,93,650,195,10
4500,100,2250,2240,0.82,0.82,12.5,0.0,65,92,95,780,190,10
6000,100,2200,2190,0.81,0.81,13.0,0.0,72,93,98,840,185,10
"""
    session = DatalogParser.parse_csv(csv_sample)
    assert session.sample_count == 4

    report = DatalogAnalyzer.analyze(session)
    assert "summary" in report
    assert report["summary"]["peak_rpm"] == 6000.0
    assert report["summary"]["peak_boost_hpa"] == 2240.0
    assert report["summary"]["max_knock_retard"] == 0.0
    assert report["safety_assessment"]["reversion_required"] is False

def test_ai_calibration_synthesis():
    base_rom = ECURomPackage(ecu_type=ECUType.BOSCH_MEVD17)

    # Synthesize Stage 2 tune for 98 RON fuel
    tuned_rom = AICalibrator.generate_optimized_calibration(
        base_rom=base_rom,
        stage="STAGE_2",
        octane_ron=98.0,
        ethanol_pct=10.0,
        enable_burble=True,
        burble_duration=1.8,
        burble_aggression="MEDIUM",
        disable_vmax=True
    )

    assert tuned_rom.vmax_disabled is True
    assert tuned_rom.burble_enabled is True
    assert tuned_rom.burble_duration_sec == 1.8
    assert tuned_rom.burble_retard_angle == -14.0

    # Ensure timing table is advanced safely
    base_t = base_rom.tables["ignition_timing"].get_value(5, 5)
    tuned_t = tuned_rom.tables["ignition_timing"].get_value(5, 5)
    assert tuned_t > base_t
    assert tuned_t <= 42.0  # Safe upper bound

    # Ensure boost target is increased safely
    base_b = base_rom.tables["target_boost"].get_value(5, 10)
    tuned_b = tuned_rom.tables["target_boost"].get_value(5, 10)
    assert tuned_b > base_b
    assert tuned_b <= 2550.0  # Hardware ceiling

def test_flex_fuel_blend_scaling():
    rom = ECURomPackage(ecu_type=ECUType.BOSCH_MG1)
    base_timing = rom.tables["ignition_timing"].get_value(5, 5)

    # Scale to E85
    rom.apply_flex_fuel_scaling(85.0)
    e85_timing = rom.tables["ignition_timing"].get_value(5, 5)

    # E85 provides +3.8 to +4.5 deg timing advance
    assert e85_timing > base_timing
    assert abs(e85_timing - (base_timing + 3.825)) < 0.1

    # Verify binary serialization and roundtrip integrity
    rom_bin = rom.generate_binary_flash_image()
    unpacked_rom = ECURomPackage.parse_binary_flash_image(rom_bin)
    assert abs(unpacked_rom.flex_fuel_ethanol_pct - 85.0) < 0.01
    assert abs(unpacked_rom.tables["ignition_timing"].get_value(5, 5) - e85_timing) < 0.001

def test_3d_table_bilinear_interpolation():
    x = [1000.0, 2000.0]
    y = [50.0, 100.0]
    # Matrix: row0 (y=50): [10, 20], row1 (y=100): [30, 40]
    matrix = [[10.0, 20.0], [30.0, 40.0]]
    table = CalibrationMap3D("TestMap", x, y, matrix)

    # Exact corners
    assert table.interpolate(1000.0, 50.0) == 10.0
    assert table.interpolate(2000.0, 50.0) == 20.0
    assert table.interpolate(1000.0, 100.0) == 30.0
    assert table.interpolate(2000.0, 100.0) == 40.0

    # Center point (x=1500, y=75) -> should be average = 25.0
    assert table.interpolate(1500.0, 75.0) == 25.0
