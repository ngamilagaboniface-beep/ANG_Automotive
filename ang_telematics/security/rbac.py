"""
Role-Based Access Control (RBAC) for Automotive Diagnostics and Remote ECU Flashing.
Controls permissions between Master Tuners, Calibrators, Technicians, and Vehicle Owners.
"""

from __future__ import annotations
import enum
from functools import wraps
from typing import Set, Dict, Any, Callable
from flask import abort, jsonify, request, session

class UserRole(str, enum.Enum):
    MASTER_TUNER = "MASTER_TUNER"
    CALIBRATOR = "CALIBRATOR"
    DIAGNOSTIC_TECH = "DIAGNOSTIC_TECH"
    VEHICLE_OWNER = "VEHICLE_OWNER"

class Permission(str, enum.Enum):
    VIEW_LIVE_TELEMETRY = "VIEW_LIVE_TELEMETRY"
    READ_CLEAR_DTC = "READ_CLEAR_DTC"
    RUN_DATALOG_ANALYSIS = "RUN_DATALOG_ANALYSIS"
    SWITCH_STAGE_PRESETS = "SWITCH_STAGE_PRESETS"
    EDIT_3D_ENGINE_MAPS = "EDIT_3D_ENGINE_MAPS"
    RUN_AI_CALIBRATOR = "RUN_AI_CALIBRATOR"
    EXECUTE_ECU_FLASH = "EXECUTE_ECU_FLASH"
    OVERRIDE_BURBLE_VMAX = "OVERRIDE_BURBLE_VMAX"
    ACCESS_SUPPLIER_SECURITY_L5 = "ACCESS_SUPPLIER_SECURITY_L5"
    EXPORT_ENCRYPTED_BIN = "EXPORT_ENCRYPTED_BIN"

ROLE_PERMISSIONS: Dict[UserRole, Set[Permission]] = {
    UserRole.MASTER_TUNER: {
        Permission.VIEW_LIVE_TELEMETRY,
        Permission.READ_CLEAR_DTC,
        Permission.RUN_DATALOG_ANALYSIS,
        Permission.SWITCH_STAGE_PRESETS,
        Permission.EDIT_3D_ENGINE_MAPS,
        Permission.RUN_AI_CALIBRATOR,
        Permission.EXECUTE_ECU_FLASH,
        Permission.OVERRIDE_BURBLE_VMAX,
        Permission.ACCESS_SUPPLIER_SECURITY_L5,
        Permission.EXPORT_ENCRYPTED_BIN
    },
    UserRole.CALIBRATOR: {
        Permission.VIEW_LIVE_TELEMETRY,
        Permission.READ_CLEAR_DTC,
        Permission.RUN_DATALOG_ANALYSIS,
        Permission.SWITCH_STAGE_PRESETS,
        Permission.EDIT_3D_ENGINE_MAPS,
        Permission.RUN_AI_CALIBRATOR,
        Permission.EXECUTE_ECU_FLASH,
        Permission.OVERRIDE_BURBLE_VMAX
    },
    UserRole.DIAGNOSTIC_TECH: {
        Permission.VIEW_LIVE_TELEMETRY,
        Permission.READ_CLEAR_DTC,
        Permission.RUN_DATALOG_ANALYSIS,
        Permission.SWITCH_STAGE_PRESETS
    },
    UserRole.VEHICLE_OWNER: {
        Permission.VIEW_LIVE_TELEMETRY,
        Permission.RUN_DATALOG_ANALYSIS,
        Permission.SWITCH_STAGE_PRESETS,
        Permission.OVERRIDE_BURBLE_VMAX
    }
}

def has_permission(role_str: str, permission: Permission) -> bool:
    try:
        role = UserRole(role_str)
        return permission in ROLE_PERMISSIONS.get(role, set())
    except ValueError:
        return False

def require_permission(permission: Permission):
    def decorator(f: Callable):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check user role from header, session or param
            role_str = request.headers.get("X-User-Role", session.get("role", "MASTER_TUNER"))
            if not has_permission(role_str, permission):
                return jsonify({
                    "error": "Forbidden: Insufficient privileges",
                    "required_permission": permission.value,
                    "user_role": role_str
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator
