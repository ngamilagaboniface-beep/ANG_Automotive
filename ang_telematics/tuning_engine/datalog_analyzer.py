"""
High-Frequency Datalog Parser, Telematics Stream Processor, and Statistical Engine.
Parses CSV/JSON/Binary telematics, computes performance statistics, and generates tuning insights.
"""

from __future__ import annotations
import io
import csv
import json
import numpy as np
from typing import Dict, Any, List, Optional, Union
from ang_telematics.tuning_engine.safety_monitor import EngineSafetyMonitor

class DatalogSession:
    """Represents a parsed multi-channel time-series datalog session."""
    def __init__(self) -> None:
        self.timestamps: List[float] = []
        self.rpm: List[float] = []
        self.speed: List[float] = []
        self.pedal: List[float] = []
        self.boost_target: List[float] = []
        self.boost_actual: List[float] = []
        self.lambda_actual: List[float] = []
        self.lambda_target: List[float] = []
        self.ignition_timing: List[List[float]] = [] # [Cyl1..6] per sample
        self.knock_retard: List[List[float]] = []    # [Cyl1..6] per sample
        self.wgdc: List[float] = []
        self.coolant_c: List[float] = []
        self.oil_c: List[float] = []
        self.egt_c: List[float] = []
        self.hpfp_bar: List[float] = []
        self.lpfp_bar: List[float] = []
        self.ethanol_pct: List[float] = []

    def add_sample(self, sample: Dict[str, Any]) -> None:
        self.timestamps.append(float(sample.get("time", len(self.timestamps) * 0.02)))
        self.rpm.append(float(sample.get("rpm", 0.0)))
        self.speed.append(float(sample.get("speed", 0.0)))
        self.pedal.append(float(sample.get("pedal_pct", 0.0)))
        self.boost_target.append(float(sample.get("boost_target_hpa", 1013.0)))
        self.boost_actual.append(float(sample.get("boost_actual_hpa", 1013.0)))
        self.lambda_actual.append(float(sample.get("lambda_actual", 1.0)))
        self.lambda_target.append(float(sample.get("lambda_target", 1.0)))

        timing = sample.get("ignition_timing", [15.0]*6)
        if isinstance(timing, (int, float)):
            timing = [float(timing)] * 6
        self.ignition_timing.append([float(t) for t in timing[:6]])

        knock = sample.get("knock_retard", [0.0]*6)
        if isinstance(knock, (int, float)):
            knock = [float(knock)] * 6
        self.knock_retard.append([float(k) for k in knock[:6]])

        self.wgdc.append(float(sample.get("wgdc", 0.0)))
        self.coolant_c.append(float(sample.get("coolant_c", 90.0)))
        self.oil_c.append(float(sample.get("oil_c", 95.0)))
        self.egt_c.append(float(sample.get("egt_c", 650.0)))
        self.hpfp_bar.append(float(sample.get("hpfp_bar", 200.0)))
        self.lpfp_bar.append(float(sample.get("lpfp_bar", 6.5)))
        self.ethanol_pct.append(float(sample.get("ethanol_pct", 10.0)))

    @property
    def sample_count(self) -> int:
        return len(self.rpm)


class DatalogParser:
    """Parses raw CSV or JSON strings/files into DatalogSession instances."""

    @classmethod
    def parse_csv(cls, csv_text: str) -> DatalogSession:
        session = DatalogSession()
        reader = csv.DictReader(io.StringIO(csv_text.strip()))

        for row in reader:
            # Map common CSV header aliases
            rpm = float(row.get("RPM", row.get("Engine RPM", row.get("rpm", 0))))
            pedal = float(row.get("Pedal", row.get("Accel Pedal", row.get("pedal_pct", 0))))
            b_tgt = float(row.get("Boost Target", row.get("Target Boost", row.get("boost_target_hpa", 1013))))
            b_act = float(row.get("Actual Boost", row.get("Boost Actual", row.get("boost_actual_hpa", 1013))))
            l_act = float(row.get("Lambda", row.get("Lambda Actual", row.get("lambda_actual", 1.0))))
            l_tgt = float(row.get("Lambda Target", row.get("lambda_target", 1.0)))
            wgdc = float(row.get("WGDC", row.get("Wastegate DC", row.get("wgdc", 0))))
            coolant = float(row.get("Coolant Temp", row.get("coolant_c", 90)))
            oil = float(row.get("Oil Temp", row.get("oil_c", 95)))
            egt = float(row.get("EGT", row.get("egt_c", 650)))
            hpfp = float(row.get("HPFP", row.get("Rail Pressure", row.get("hpfp_bar", 200))))
            eth = float(row.get("Ethanol", row.get("ethanol_pct", 10)))

            # Parse cylinder timings
            timing = []
            for c in range(1, 7):
                k_name = f"Timing Cyl {c}"
                if k_name in row:
                    timing.append(float(row[k_name]))
            if not timing:
                timing = [float(row.get("Timing", row.get("Ignition Timing", 15.0)))] * 6

            # Parse cylinder knock
            knock = []
            for c in range(1, 7):
                k_name = f"Knock Cyl {c}"
                if k_name in row:
                    knock.append(float(row[k_name]))
            if not knock:
                knock = [float(row.get("Knock Retard", 0.0))] * 6

            session.add_sample({
                "rpm": rpm,
                "pedal_pct": pedal,
                "boost_target_hpa": b_tgt,
                "boost_actual_hpa": b_act,
                "lambda_actual": l_act,
                "lambda_target": l_tgt,
                "ignition_timing": timing,
                "knock_retard": knock,
                "wgdc": wgdc,
                "coolant_c": coolant,
                "oil_c": oil,
                "egt_c": egt,
                "hpfp_bar": hpfp,
                "ethanol_pct": eth
            })

        return session

    @classmethod
    def parse_json(cls, json_data: Union[str, List[Dict[str, Any]]]) -> DatalogSession:
        session = DatalogSession()
        if isinstance(json_data, str):
            items = json.loads(json_data)
        else:
            items = json_data

        for item in items:
            session.add_sample(item)

        return session


class DatalogAnalyzer:
    """
    Statistical analyzer and AI calibration recommendation engine for datalogs.
    """

    @classmethod
    def analyze(cls, session: DatalogSession) -> Dict[str, Any]:
        if session.sample_count == 0:
            return {"error": "Empty datalog session"}

        rpm_arr = np.array(session.rpm)
        boost_tgt_arr = np.array(session.boost_target)
        boost_act_arr = np.array(session.boost_actual)
        lambda_act_arr = np.array(session.lambda_actual)
        wgdc_arr = np.array(session.wgdc)
        coolant_arr = np.array(session.coolant_c)
        oil_arr = np.array(session.oil_c)
        egt_arr = np.array(session.egt_c)
        hpfp_arr = np.array(session.hpfp_bar)
        pedal_arr = np.array(session.pedal)

        # Knock arrays across cylinders
        knock_matrix = np.array(session.knock_retard) # (N, 6)
        max_knock_per_cyl = np.max(knock_matrix, axis=0).tolist()
        overall_max_knock = float(np.max(knock_matrix))

        # WOT Mask (Wide Open Throttle pull samples)
        wot_mask = (pedal_arr > 75.0) | (boost_act_arr > 1300.0)
        wot_count = int(np.sum(wot_mask))

        # Boost Metrics
        boost_error = boost_act_arr - boost_tgt_arr
        boost_mae = float(np.mean(np.abs(boost_error)))
        max_boost_psi = float(np.max((boost_act_arr - 1013.25) * 0.0145038))

        # Fueling Metrics during WOT
        if wot_count > 0:
            wot_lambda_mean = float(np.mean(lambda_act_arr[wot_mask]))
            wot_lambda_max = float(np.max(lambda_act_arr[wot_mask]))
            min_hpfp_wot = float(np.min(hpfp_arr[wot_mask]))
            mean_wgdc_wot = float(np.mean(wgdc_arr[wot_mask]))
        else:
            wot_lambda_mean = float(np.mean(lambda_act_arr))
            wot_lambda_max = float(np.max(lambda_act_arr))
            min_hpfp_wot = float(np.min(hpfp_arr))
            mean_wgdc_wot = float(np.mean(wgdc_arr))

        # Safety Violations Scan across all frames
        critical_violations: List[str] = []
        for i in range(session.sample_count):
            frame = {
                "rpm": session.rpm[i],
                "pedal_pct": session.pedal[i],
                "boost_target_hpa": session.boost_target[i],
                "boost_actual_hpa": session.boost_actual[i],
                "lambda_actual": session.lambda_actual[i],
                "ignition_timing": session.ignition_timing[i],
                "knock_retard": session.knock_retard[i],
                "coolant_c": session.coolant_c[i],
                "oil_c": session.oil_c[i],
                "egt_c": session.egt_c[i],
                "hpfp_bar": session.hpfp_bar[i]
            }
            eval_res = EngineSafetyMonitor.evaluate_telemetry_frame(frame)
            if eval_res["reversion_required"]:
                critical_violations.extend(eval_res["violations"])

        # Deduplicate violations
        unique_violations = list(dict.fromkeys(critical_violations))

        # AI Diagnostic Recommendations
        recommendations: List[Dict[str, str]] = []

        # 1. Knock analysis
        if overall_max_knock > 3.0:
            recommendations.append({
                "severity": "CRITICAL",
                "category": "IGNITION_KNOCK",
                "message": f"Excessive knock retard detected ({overall_max_knock:.1f}°). Octane rating insufficient or ignition advance too aggressive.",
                "action": f"Reduce ignition timing advance by {min(4.0, overall_max_knock - 1.0):.1f}° or increase fuel octane (E30 / 100 RON)."
            })
        elif overall_max_knock > 1.5:
            recommendations.append({
                "severity": "WARNING",
                "category": "IGNITION_KNOCK",
                "message": f"Minor knock corrections observed ({overall_max_knock:.1f}°). Knock control system active.",
                "action": "Trim 1.0° timing in the 4500-6000 RPM high-load region for improved consistency."
            })
        else:
            recommendations.append({
                "severity": "HEALTHY",
                "category": "IGNITION_KNOCK",
                "message": "Clean ignition timing curve with zero significant knock corrections.",
                "action": "Timing maps are operating within optimal safety margin."
            })

        # 2. Boost & WGDC analysis
        if mean_wgdc_wot > 90.0 and boost_mae > 150.0:
            recommendations.append({
                "severity": "WARNING",
                "category": "BOOST_CONTROL",
                "message": f"Wastegate duty cycle saturating at {mean_wgdc_wot:.1f}% while boost is under target.",
                "action": "Check charge pipes, turbo inlet, or boost solenoids for potential boost leak."
            })
        elif np.max(boost_error) > 300.0:
            recommendations.append({
                "severity": "WARNING",
                "category": "BOOST_CONTROL",
                "message": f"Boost overshoot spike detected (+{np.max(boost_error):.0f} hPa).",
                "action": "Adjust PID derivative gain or lower base WGDC feedforward map around initial spool."
            })
        else:
            recommendations.append({
                "severity": "HEALTHY",
                "category": "BOOST_CONTROL",
                "message": f"Boost tracking tight (MAE {boost_mae:.1f} hPa, Max Boost {max_boost_psi:.1f} PSI).",
                "action": "Boost control loop is well linearized."
            })

        # 3. Fueling & Fuel System analysis
        if min_hpfp_wot < 145.0:
            recommendations.append({
                "severity": "CRITICAL",
                "category": "FUELING",
                "message": f"High Pressure Fuel Pump rail pressure dropped to {min_hpfp_wot:.1f} bar under WOT (minimum safe: 140 bar).",
                "action": "Fuel pump flow limit reached. Upgrade HPFP or reduce ethanol blend / boost target."
            })
        elif wot_lambda_max > 0.86:
            recommendations.append({
                "severity": "WARNING",
                "category": "FUELING",
                "message": f"Lean AFR condition detected under WOT (Lambda {wot_lambda_max:.3f} / AFR {wot_lambda_max*14.7:.1f}).",
                "action": "Enrich high-load target lambda table to maintain Lambda 0.80 - 0.84 under full boost."
            })
        else:
            recommendations.append({
                "severity": "HEALTHY",
                "category": "FUELING",
                "message": f"Fuel system healthy (WOT Mean Lambda {wot_lambda_mean:.3f}, Min HPFP {min_hpfp_wot:.1f} bar).",
                "action": "Fuel delivery is stable."
            })

        # 4. Thermal & Intercooler analysis
        max_egt = float(np.max(egt_arr))
        max_coolant = float(np.max(coolant_arr))
        max_oil = float(np.max(oil_arr))

        if max_egt > 920.0 or max_oil > 125.0:
            recommendations.append({
                "severity": "WARNING",
                "category": "THERMAL",
                "message": f"High thermal load reached (EGT {max_egt:.0f}°C, Oil {max_oil:.0f}°C).",
                "action": "Increase component protection fuel enrichment and allow cool-down laps."
            })
        else:
            recommendations.append({
                "severity": "HEALTHY",
                "category": "THERMAL",
                "message": f"Thermal profile optimal (Max EGT {max_egt:.0f}°C, Oil {max_oil:.0f}°C, Coolant {max_coolant:.0f}°C).",
                "action": "Cooling systems operating in normal range."
            })

        return {
            "summary": {
                "sample_count": session.sample_count,
                "duration_seconds": round(session.sample_count * 0.02, 2),
                "peak_rpm": float(np.max(rpm_arr)),
                "peak_boost_psi": round(max_boost_psi, 2),
                "peak_boost_hpa": round(float(np.max(boost_act_arr)), 1),
                "wot_pull_samples": wot_count,
                "max_knock_retard": round(overall_max_knock, 2),
                "max_knock_per_cylinder": [round(k, 1) for k in max_knock_per_cyl],
                "wot_mean_lambda": round(wot_lambda_mean, 3),
                "min_hpfp_bar": round(min_hpfp_wot, 1),
                "peak_egt_c": round(max_egt, 1),
                "peak_oil_c": round(max_oil, 1),
                "peak_coolant_c": round(max_coolant, 1),
                "mean_wgdc_wot": round(mean_wgdc_wot, 1),
                "boost_mae_hpa": round(boost_mae, 1)
            },
            "safety_assessment": {
                "reversion_required": len(unique_violations) > 0,
                "critical_violations": unique_violations
            },
            "recommendations": recommendations
        }
