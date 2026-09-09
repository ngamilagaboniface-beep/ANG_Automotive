"""
Real-Time Automotive Safety Bounds, Tripwires, and Overrides Engine.
Enforces non-overridable hardware protection thresholds for engine preservation.
"""

from __future__ import annotations
import enum
from typing import Dict, Any, List, Optional, Tuple

class SafetyStatus(enum.Enum):
    SAFE = "SAFE"
    WARNING = "WARNING"
    DERATED = "DERATED"
    CRITICAL_REVERSION_REQUIRED = "CRITICAL_REVERSION_REQUIRED"

class SafetyViolationType(enum.Enum):
    NONE = "NONE"
    KNOCK_MULTI_CYLINDER = "KNOCK_MULTI_CYLINDER"       # Knock retard > 3.0 deg across >= 2 cylinders
    KNOCK_SINGLE_CYLINDER = "KNOCK_SINGLE_CYLINDER"     # Knock retard > 5.0 deg on any cylinder
    COOLANT_OVERTEMP = "COOLANT_OVERTEMP"               # Coolant > 112 deg C
    OIL_OVERTEMP = "OIL_OVERTEMP"                       # Oil > 130 deg C
    EGT_OVERTEMP = "EGT_OVERTEMP"                       # EGT > 950 deg C
    BOOST_OVERSHOOT = "BOOST_OVERSHOOT"                 # Actual > Target + 0.35 bar (350 hPa)
    BOOST_ABSOLUTE_LIMIT = "BOOST_ABSOLUTE_LIMIT"       # Exceeded max hardware limit (2.6 bar)
    LEAN_MIXTURE_WOT = "LEAN_MIXTURE_WOT"               # Lambda > 0.88 under WOT (>80% pedal/load)
    FUEL_PRESSURE_DROP = "FUEL_PRESSURE_DROP"           # HPFP < 140 bar under WOT

class EngineSafetyMonitor:
    """
    Hardcoded, non-overridable safety monitor.
    Monitors high-frequency live telemetry streams and calculates derating / map rollback flags.
    """
    # Non-overridable safety thresholds
    THRESH_KNOCK_MULTI_CYL_DEG = 3.0
    THRESH_KNOCK_SINGLE_CYL_DEG = 5.0
    THRESH_COOLANT_MAX_C = 112.0
    THRESH_OIL_MAX_C = 130.0
    THRESH_EGT_MAX_C = 950.0
    THRESH_BOOST_DELTA_MAX_HPA = 350.0  # 0.35 bar
    THRESH_BOOST_ABS_MAX_HPA = 2600.0   # 2.6 bar absolute
    THRESH_LEAN_LAMBDA_WOT = 0.88
    THRESH_HPFP_MIN_BAR_WOT = 140.0

    @classmethod
    def evaluate_telemetry_frame(cls, frame: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates a single telemetry snapshot against all safety tripwires.
        """
        violations: List[str] = []
        status = SafetyStatus.SAFE
        derate_factor = 1.0 # 1.0 = 100% power, 0.7 = 30% cut, 0.0 = total limp

        # 1. Knock Retard Check
        knock_retards = frame.get("knock_retard", [0.0]*6)
        cylinders_over_3deg = sum(1 for k in knock_retards if k > cls.THRESH_KNOCK_MULTI_CYL_DEG)
        max_single_knock = max(knock_retards) if knock_retards else 0.0

        if cylinders_over_3deg >= 2:
            violations.append(f"CRITICAL: Knock retard > {cls.THRESH_KNOCK_MULTI_CYL_DEG}° on {cylinders_over_3deg} cylinders ({knock_retards})")
            status = SafetyStatus.CRITICAL_REVERSION_REQUIRED
            derate_factor = min(derate_factor, 0.5)

        if max_single_knock > cls.THRESH_KNOCK_SINGLE_CYL_DEG:
            violations.append(f"CRITICAL: Single cylinder knock retard {max_single_knock:.1f}° exceeds {cls.THRESH_KNOCK_SINGLE_CYL_DEG}° limit")
            status = SafetyStatus.CRITICAL_REVERSION_REQUIRED
            derate_factor = min(derate_factor, 0.5)

        # 2. Temperature Checks
        coolant_c = frame.get("coolant_c", 90.0)
        oil_c = frame.get("oil_c", 95.0)
        egt_c = frame.get("egt_c", 650.0)

        if coolant_c > cls.THRESH_COOLANT_MAX_C:
            violations.append(f"THERMAL DERATE: Coolant temperature {coolant_c:.1f}°C exceeds threshold {cls.THRESH_COOLANT_MAX_C}°C")
            if status != SafetyStatus.CRITICAL_REVERSION_REQUIRED:
                status = SafetyStatus.DERATED
            derate_factor = min(derate_factor, 0.70)

        if oil_c > cls.THRESH_OIL_MAX_C:
            violations.append(f"THERMAL DERATE: Oil temperature {oil_c:.1f}°C exceeds threshold {cls.THRESH_OIL_MAX_C}°C")
            if status != SafetyStatus.CRITICAL_REVERSION_REQUIRED:
                status = SafetyStatus.DERATED
            derate_factor = min(derate_factor, 0.75)

        if egt_c > cls.THRESH_EGT_MAX_C:
            violations.append(f"THERMAL DERATE: Exhaust Gas Temperature {egt_c:.1f}°C exceeds threshold {cls.THRESH_EGT_MAX_C}°C")
            if status != SafetyStatus.CRITICAL_REVERSION_REQUIRED:
                status = SafetyStatus.DERATED
            derate_factor = min(derate_factor, 0.65)

        # 3. Boost Checks
        boost_tgt = frame.get("boost_target_hpa", 1013.0)
        boost_act = frame.get("boost_actual_hpa", 1013.0)
        boost_delta = boost_act - boost_tgt

        if boost_delta > cls.THRESH_BOOST_DELTA_MAX_HPA:
            violations.append(f"BOOST CUT: Boost overshoot {boost_delta:.1f} hPa exceeds +{cls.THRESH_BOOST_DELTA_MAX_HPA} hPa limit")
            if status != SafetyStatus.CRITICAL_REVERSION_REQUIRED:
                status = SafetyStatus.DERATED
            derate_factor = min(derate_factor, 0.60)

        if boost_act > cls.THRESH_BOOST_ABS_MAX_HPA:
            violations.append(f"BOOST CUT: Absolute boost {boost_act:.1f} hPa exceeds max limit {cls.THRESH_BOOST_ABS_MAX_HPA} hPa")
            if status != SafetyStatus.CRITICAL_REVERSION_REQUIRED:
                status = SafetyStatus.DERATED
            derate_factor = min(derate_factor, 0.50)

        # 4. Air-Fuel Ratio / Fueling Check under WOT
        pedal_pct = frame.get("pedal_pct", 0.0)
        rpm = frame.get("rpm", 0.0)
        lambda_act = frame.get("lambda_actual", 1.0)
        hpfp_bar = frame.get("hpfp_bar", 200.0)

        is_wot = (pedal_pct > 80.0) or (boost_act > 1400.0 and rpm > 3000.0)

        if is_wot:
            if lambda_act > cls.THRESH_LEAN_LAMBDA_WOT:
                violations.append(f"CRITICAL LEAN TRIPWIRE: Lambda {lambda_act:.3f} under WOT exceeds lean limit {cls.THRESH_LEAN_LAMBDA_WOT}")
                status = SafetyStatus.CRITICAL_REVERSION_REQUIRED
                derate_factor = min(derate_factor, 0.40)

            if hpfp_bar < cls.THRESH_HPFP_MIN_BAR_WOT:
                violations.append(f"FUEL PRESSURE DROP: HPFP rail pressure {hpfp_bar:.1f} bar below {cls.THRESH_HPFP_MIN_BAR_WOT} bar under WOT")
                if status != SafetyStatus.CRITICAL_REVERSION_REQUIRED:
                    status = SafetyStatus.DERATED
                derate_factor = min(derate_factor, 0.70)

        return {
            "status": status.value,
            "derate_factor": round(derate_factor, 2),
            "reversion_required": (status == SafetyStatus.CRITICAL_REVERSION_REQUIRED),
            "derating_active": (derate_factor < 1.0),
            "violations_count": len(violations),
            "violations": violations
        }
