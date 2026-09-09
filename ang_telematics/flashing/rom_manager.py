"""
BMW ECU ROM Binary Parser, Calibration Table Extractor, Map Patcher, and Checksum Recalculator.
Supports Bosch MEVD17 (N20/N55/S55), Siemens MSD80/81/85 (N54/N63), and Bosch MG1/MD1 (B48/B58/S58).
"""

from __future__ import annotations
import struct
import copy
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from ang_telematics.protocols.crypto import ChecksumEngine, RSAFlashVerifier

class ECUType:
    BOSCH_MEVD17 = "BOSCH_MEVD17"
    SIEMENS_MSD80 = "SIEMENS_MSD80"
    BOSCH_MG1 = "BOSCH_MG1"

class CalibrationMap2D:
    """Represents a 1D curve / lookup table (X-axis -> Z values)."""
    def __init__(self, name: str, x_axis: List[float], values: List[float], unit: str = "") -> None:
        self.name = name
        self.x_axis = [float(x) for x in x_axis]
        self.values = [float(v) for v in values]
        self.unit = unit

    def interpolate(self, x: float) -> float:
        return float(np.interp(x, self.x_axis, self.values))

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "x_axis": self.x_axis, "values": self.values, "unit": self.unit}

class CalibrationMap3D:
    """Represents a 2D surface table (X-axis [RPM] x Y-axis [Load %] -> Z matrix)."""
    def __init__(
        self,
        name: str,
        x_axis: List[float],  # e.g., RPM (1000 - 7500)
        y_axis: List[float],  # e.g., Engine Load % (20% - 220%)
        matrix: List[List[float]], # Z values (Timing deg, Target Boost hPa, Lambda)
        unit: str = "",
        min_limit: float = -30.0,
        max_limit: float = 3500.0
    ) -> None:
        self.name = name
        self.x_axis = [float(x) for x in x_axis]
        self.y_axis = [float(y) for y in y_axis]
        self.matrix = [[float(val) for val in row] for row in matrix]
        self.unit = unit
        self.min_limit = min_limit
        self.max_limit = max_limit

    def get_value(self, x_idx: int, y_idx: int) -> float:
        return self.matrix[y_idx][x_idx]

    def set_value(self, x_idx: int, y_idx: int, value: float) -> None:
        clamped = max(self.min_limit, min(self.max_limit, float(value)))
        self.matrix[y_idx][x_idx] = round(clamped, 3)

    def interpolate(self, x: float, y: float) -> float:
        """Bilinear interpolation across the 3D surface mesh."""
        x_clipped = max(self.x_axis[0], min(self.x_axis[-1], x))
        y_clipped = max(self.y_axis[0], min(self.y_axis[-1], y))

        # Find bounding indices
        x_idx = np.searchsorted(self.x_axis, x_clipped)
        y_idx = np.searchsorted(self.y_axis, y_clipped)

        x1_idx = max(0, x_idx - 1)
        x2_idx = min(len(self.x_axis) - 1, x_idx)
        y1_idx = max(0, y_idx - 1)
        y2_idx = min(len(self.y_axis) - 1, y_idx)

        x1, x2 = self.x_axis[x1_idx], self.x_axis[x2_idx]
        y1, y2 = self.y_axis[y1_idx], self.y_axis[y2_idx]

        q11 = self.matrix[y1_idx][x1_idx]
        q12 = self.matrix[y2_idx][x1_idx]
        q21 = self.matrix[y1_idx][x2_idx]
        q22 = self.matrix[y2_idx][x2_idx]

        if x1 == x2 and y1 == y2:
            return q11
        elif x1 == x2:
            return q11 + (q12 - q11) * ((y_clipped - y1) / (y2 - y1 if y2 != y1 else 1.0))
        elif y1 == y2:
            return q11 + (q21 - q11) * ((x_clipped - x1) / (x2 - x1 if x2 != x1 else 1.0))

        # Standard bilinear formula
        dx = (x_clipped - x1) / (x2 - x1)
        dy = (y_clipped - y1) / (y2 - y1)

        r1 = q11 * (1 - dx) + q21 * dx
        r2 = q12 * (1 - dx) + q22 * dx
        return float(r1 * (1 - dy) + r2 * dy)

    def offset_all(self, delta: float) -> None:
        """Apply uniform offset with safety clamping."""
        for y_idx in range(len(self.matrix)):
            for x_idx in range(len(self.matrix[y_idx])):
                new_v = max(self.min_limit, min(self.max_limit, self.matrix[y_idx][x_idx] + delta))
                self.matrix[y_idx][x_idx] = round(new_v, 3)

    def scale_all(self, factor: float) -> None:
        """Apply multiplier scaling with safety clamping."""
        for y_idx in range(len(self.matrix)):
            for x_idx in range(len(self.matrix[y_idx])):
                new_v = max(self.min_limit, min(self.max_limit, self.matrix[y_idx][x_idx] * factor))
                self.matrix[y_idx][x_idx] = round(new_v, 3)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "x_axis": self.x_axis,
            "y_axis": self.y_axis,
            "matrix": self.matrix,
            "unit": self.unit,
            "min_limit": self.min_limit,
            "max_limit": self.max_limit
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalibrationMap3D":
        return cls(
            name=data["name"],
            x_axis=data["x_axis"],
            y_axis=data["y_axis"],
            matrix=data["matrix"],
            unit=data.get("unit", ""),
            min_limit=data.get("min_limit", -30.0),
            max_limit=data.get("max_limit", 3500.0)
        )


class ECURomPackage:
    """
    Complete calibrated ECU ROM package with calibration maps, user customization flags,
    binary image generation, and checksum verification blocks.
    """
    def __init__(
        self,
        ecu_type: str = ECUType.BOSCH_MEVD17,
        software_id: str = "00001E8B001",
        vin: str = "WBA3R9C50K5A12345",
        calibration_version: str = "ANG_STAGE2_V3.4"
    ) -> None:
        self.ecu_type = ecu_type
        self.software_id = software_id
        self.vin = vin
        self.calibration_version = calibration_version

        # Customization Toggles
        self.vmax_speed_limit_kmh: float = 330.0  # 250 -> 330 / unlimited
        self.vmax_disabled: bool = True
        self.flex_fuel_ethanol_pct: float = 10.0  # Default E10 pump gas
        self.burble_enabled: bool = True
        self.burble_duration_sec: float = 1.5     # 0.0 to 4.0s
        self.burble_retard_angle: float = -14.0   # -5 to -25 deg ATDC
        self.burble_min_rpm: float = 2600.0       # Trailing throttle threshold
        self.burble_aggression: str = "MEDIUM"    # SOFT, MEDIUM, HARD, GTS_CS, FLAME
        self.cold_start_cat_heating_enabled: bool = False # Delete cold start roar
        self.exhaust_flap_sport_open: bool = True
        self.linear_throttle_mapping: bool = True

        # Factory & Tuned 3D Engine Tables
        self.tables: Dict[str, CalibrationMap3D] = {}
        self._initialize_default_tables()

    def _initialize_default_tables(self) -> None:
        rpm_axis = [1000.0, 1500.0, 2000.0, 2500.0, 3000.0, 3500.0, 4000.0, 4500.0, 5000.0, 5500.0, 6000.0, 6500.0, 7000.0, 7500.0]
        load_axis = [20.0, 40.0, 60.0, 80.0, 100.0, 120.0, 140.0, 160.0, 180.0, 200.0, 220.0]

        # 1. Base Ignition Timing Table (°BTDC)
        timing_matrix = []
        for load in load_axis:
            row = []
            for rpm in rpm_axis:
                # Realistic BMW S55/B58 ignition timing progression
                base_t = 35.0 - (load * 0.14) + ((rpm - 1000) * 0.0025)
                row.append(round(max(-10.0, min(42.0, base_t)), 1))
            timing_matrix.append(row)
        self.tables["ignition_timing"] = CalibrationMap3D("Ignition Timing Main", rpm_axis, load_axis, timing_matrix, "°BTDC", -25.0, 50.0)

        # 2. Target AFR / Lambda Table
        lambda_matrix = []
        for load in load_axis:
            row = []
            for rpm in rpm_axis:
                if load <= 80.0:
                    l_val = 1.000  # Stoichiometric cruise
                elif load <= 140.0:
                    l_val = 1.000 - ((load - 80.0) * 0.0018)
                else:
                    l_val = 0.890 - ((load - 140.0) * 0.0012) - (0.02 if rpm > 5500 else 0.0)
                row.append(round(max(0.72, min(1.05, l_val)), 3))
            lambda_matrix.append(row)
        self.tables["target_lambda"] = CalibrationMap3D("Target Lambda / AFR", rpm_axis, load_axis, lambda_matrix, "Lambda", 0.65, 1.15)

        # 3. Boost Target Table (hPa Absolute)
        boost_matrix = []
        pedal_axis = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        for pedal in pedal_axis:
            row = []
            for rpm in rpm_axis:
                if pedal < 30.0:
                    b_val = 1013.0
                else:
                    # Stage 2 boost target up to ~2250 hPa (1.25 bar boost / ~18 PSI)
                    ratio = (pedal - 30.0) / 70.0
                    peak_boost = 2250.0 if (rpm >= 2500 and rpm <= 5500) else (2050.0 if rpm > 5500 else 1600.0)
                    b_val = 1013.0 + ratio * (peak_boost - 1013.0)
                row.append(round(b_val, 1))
            boost_matrix.append(row)
        self.tables["target_boost"] = CalibrationMap3D("Target Boost Absolute", rpm_axis, pedal_axis, boost_matrix, "hPa", 1000.0, 3200.0)

        # 4. Wastegate Duty Cycle Feedforward Map (WGDC %)
        wgdc_matrix = []
        for pedal in pedal_axis:
            row = []
            for rpm in rpm_axis:
                if pedal < 20.0:
                    wg_val = 0.0
                else:
                    wg_val = min(92.0, 15.0 + (pedal * 0.65) + (rpm / 1000.0 * 2.5))
                row.append(round(wg_val, 1))
            wgdc_matrix.append(row)
        self.tables["wgdc_base"] = CalibrationMap3D("Wastegate Duty Cycle Base", rpm_axis, pedal_axis, wgdc_matrix, "%", 0.0, 100.0)

        # 5. Torque Limiter (Nm vs RPM)
        torque_matrix = []
        gear_axis = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        for gear in gear_axis:
            row = []
            for rpm in rpm_axis:
                max_t = 680.0 if gear >= 3.0 else (550.0 if gear == 1.0 else 620.0)
                if rpm > 6500:
                    max_t -= (rpm - 6500) * 0.1
                row.append(round(max_t, 1))
            torque_matrix.append(row)
        self.tables["torque_limiters"] = CalibrationMap3D("Torque Limiters by Gear", rpm_axis, gear_axis, torque_matrix, "Nm", 100.0, 1000.0)

    def apply_stage(self, stage_name: str) -> None:
        """Configures map presets for Stage 1, Stage 2, Stage 2+ E85, or Stock."""
        stage_upper = stage_name.upper()
        if "STOCK" in stage_upper:
            self.vmax_disabled = False
            self.burble_enabled = False
            self.tables["target_boost"].scale_all(0.80)
            self.tables["ignition_timing"].offset_all(-2.5)
            self.tables["torque_limiters"].scale_all(0.82)
            self.calibration_version = "BMW_OEM_FACTORY_STOCK"
        elif "STAGE_1" in stage_upper:
            self.vmax_disabled = True
            self.burble_enabled = True
            self.burble_duration_sec = 1.2
            self.burble_aggression = "SOFT"
            self.tables["target_boost"].scale_all(1.08)
            self.tables["ignition_timing"].offset_all(1.5)
            self.tables["torque_limiters"].scale_all(1.12)
            self.calibration_version = "ANG_STAGE_1_93OCT"
        elif "STAGE_2_E85" in stage_upper or "STAGE_2+" in stage_upper:
            self.vmax_disabled = True
            self.burble_enabled = True
            self.burble_duration_sec = 2.2
            self.burble_aggression = "GTS_CS"
            self.flex_fuel_ethanol_pct = 85.0
            self.tables["target_boost"].scale_all(1.22)
            self.tables["ignition_timing"].offset_all(4.5)
            self.tables["torque_limiters"].scale_all(1.28)
            self.calibration_version = "ANG_STAGE_2_PLUS_E85"
        else: # STAGE_2 Standard
            self.vmax_disabled = True
            self.burble_enabled = True
            self.burble_duration_sec = 1.8
            self.burble_aggression = "MEDIUM"
            self.tables["target_boost"].scale_all(1.15)
            self.tables["ignition_timing"].offset_all(2.5)
            self.tables["torque_limiters"].scale_all(1.20)
            self.calibration_version = "ANG_STAGE_2_93OCT"

    def apply_flex_fuel_scaling(self, ethanol_pct: float) -> None:
        """
        Calculates ethanol blend scalar and updates ignition timing advance and fuel enrichment.
        Ethanol increases knock resistance allowing up to +5.0° timing and requiring ~30% more fuel.
        """
        self.flex_fuel_ethanol_pct = max(0.0, min(100.0, float(ethanol_pct)))
        e_fraction = self.flex_fuel_ethanol_pct / 100.0 # 0.0 to 1.0

        # Ethanol timing adder (up to +4.5° at E85)
        timing_offset = e_fraction * 4.5
        self.tables["ignition_timing"].offset_all(timing_offset)

        # Target Lambda adjustment for E85 cooling & cylinder preservation
        for y in range(len(self.tables["target_lambda"].matrix)):
            for x in range(len(self.tables["target_lambda"].matrix[y])):
                orig_l = self.tables["target_lambda"].matrix[y][x]
                if orig_l < 1.0:
                    # Enrich slightly for E85 maximum power rich lambda (0.82 -> 0.78)
                    new_l = orig_l - (e_fraction * 0.04)
                    self.tables["target_lambda"].matrix[y][x] = round(max(0.70, new_l), 3)

    def generate_binary_flash_image(self) -> bytes:
        """
        Serializes entire calibrated ROM package into structured binary format
        with embedded headers, table maps, flags, RSA signature, and CRC32 checksums.
        """
        # Header block: 128 bytes
        header_magic = b"ANG_BMW_ROM_V3\x00\x00" # 16 bytes
        ecu_type_b = self.ecu_type.encode("ascii")[:16].ljust(16, b"\x00")
        sw_id_b = self.software_id.encode("ascii")[:16].ljust(16, b"\x00")
        vin_b = self.vin.encode("ascii")[:17].ljust(17, b"\x00")
        cal_ver_b = self.calibration_version.encode("ascii")[:24].ljust(24, b"\x00")

        vmax_flag = 0xFF if self.vmax_disabled else 0x00
        cat_heat_flag = 0x01 if self.cold_start_cat_heating_enabled else 0x00
        flap_flag = 0x01 if self.exhaust_flap_sport_open else 0x00
        lin_throt_flag = 0x01 if self.linear_throttle_mapping else 0x00

        flags_packed = struct.pack(
            "!BBBBfffff",
            vmax_flag,
            cat_heat_flag,
            flap_flag,
            lin_throt_flag,
            self.vmax_speed_limit_kmh,
            self.flex_fuel_ethanol_pct,
            self.burble_duration_sec,
            self.burble_retard_angle,
            self.burble_min_rpm
        )
        flags_packed = flags_packed.ljust(39, b"\x00") # Total 128 header bytes

        header_chunk = header_magic + ecu_type_b + sw_id_b + vin_b + cal_ver_b + flags_packed

        # Calibration Data Blocks (Serializing 3D tables into binary matrix floats)
        body_chunks = bytearray()
        for tbl_name, tbl in sorted(self.tables.items()):
            name_b = tbl_name.encode("ascii")[:32].ljust(32, b"\x00")
            num_x = len(tbl.x_axis)
            num_y = len(tbl.y_axis)
            meta = struct.pack("!32sHH", name_b, num_x, num_y)
            x_b = struct.pack(f"!{num_x}f", *tbl.x_axis)
            y_b = struct.pack(f"!{num_y}f", *tbl.y_axis)
            flat_matrix = [item for sublist in tbl.matrix for item in sublist]
            m_b = struct.pack(f"!{len(flat_matrix)}f", *flat_matrix)
            body_chunks.extend(meta + x_b + y_b + m_b)

        raw_payload = bytes(header_chunk) + bytes(body_chunks)

        # Calculate Checksums
        additive32 = ChecksumEngine.bmw_additive_32(raw_payload)
        crc32_val = ChecksumEngine.crc32(raw_payload)
        md5_digest = ChecksumEngine.md5(raw_payload)
        sha256_digest = ChecksumEngine.sha256(raw_payload)

        # Generate RSA-2048 flash signature
        rsa_sig = RSAFlashVerifier.sign_payload(raw_payload)

        # Trailing Security Block: [Additive32(4), CRC32(4), MD5(16), SHA256(32), RSA_Signature(256)]
        security_trailer = struct.pack("!II16s32s256s", additive32, crc32_val, md5_digest, sha256_digest, rsa_sig)

        final_rom = raw_payload + security_trailer
        return final_rom

    @classmethod
    def parse_binary_flash_image(cls, data: bytes) -> "ECURomPackage":
        """Unpacks and verifies binary flash ROM image."""
        if len(data) < 128 + 312:  # Min header + security trailer
            raise ValueError(f"ROM binary too small: {len(data)} bytes")

        security_trailer = data[-312:]
        raw_payload = data[:-312]

        add32, crc, md5_d, sha_d, rsa_sig = struct.unpack("!II16s32s256s", security_trailer)

        # Verify Checksums
        calc_add32 = ChecksumEngine.bmw_additive_32(raw_payload)
        calc_crc = ChecksumEngine.crc32(raw_payload)
        calc_md5 = ChecksumEngine.md5(raw_payload)
        calc_sha = ChecksumEngine.sha256(raw_payload)

        if crc != calc_crc or sha_d != calc_sha:
            raise ValueError("ROM Checksum verification failure: Payload corrupted or altered")

        if not RSAFlashVerifier.verify_signature(raw_payload, rsa_sig):
            raise ValueError("RSA Secure Boot verification failure: Invalid cryptographic signature")

        # Unpack Header
        header = raw_payload[:128]
        magic = header[:16].rstrip(b"\x00")
        if not magic.startswith(b"ANG_BMW_ROM"):
            raise ValueError("Invalid ROM magic identifier")

        ecu_type = header[16:32].decode("ascii", errors="ignore").rstrip("\x00")
        sw_id = header[32:48].decode("ascii", errors="ignore").rstrip("\x00")
        vin = header[48:65].decode("ascii", errors="ignore").rstrip("\x00")
        cal_ver = header[65:89].decode("ascii", errors="ignore").rstrip("\x00")

        vmax_flag, cat_flag, flap_flag, lin_flag, vmax_spd, e_pct, b_dur, b_ret, b_rpm = struct.unpack("!BBBBfffff", header[89:89+24])

        instance = cls(ecu_type, sw_id, vin, cal_ver)
        instance.vmax_disabled = (vmax_flag == 0xFF)
        instance.cold_start_cat_heating_enabled = (cat_flag == 0x01)
        instance.exhaust_flap_sport_open = (flap_flag == 0x01)
        instance.linear_throttle_mapping = (lin_flag == 0x01)
        instance.vmax_speed_limit_kmh = vmax_spd
        instance.flex_fuel_ethanol_pct = e_pct
        instance.burble_duration_sec = b_dur
        instance.burble_retard_angle = b_ret
        instance.burble_min_rpm = b_rpm

        # Unpack Table Blocks
        pos = 128
        while pos < len(raw_payload):
            if pos + 36 > len(raw_payload):
                break
            name_b, nx, ny = struct.unpack("!32sHH", raw_payload[pos:pos+36])
            pos += 36
            t_name = name_b.decode("ascii", errors="ignore").rstrip("\x00")
            x_bytes_len = nx * 4
            y_bytes_len = ny * 4
            m_bytes_len = nx * ny * 4

            if pos + x_bytes_len + y_bytes_len + m_bytes_len > len(raw_payload):
                break

            x_axis = list(struct.unpack(f"!{nx}f", raw_payload[pos:pos+x_bytes_len]))
            pos += x_bytes_len
            y_axis = list(struct.unpack(f"!{ny}f", raw_payload[pos:pos+y_bytes_len]))
            pos += y_bytes_len
            m_flat = struct.unpack(f"!{nx*ny}f", raw_payload[pos:pos+m_bytes_len])
            pos += m_bytes_len

            matrix = []
            for y_i in range(ny):
                matrix.append(list(m_flat[y_i*nx:(y_i+1)*nx]))

            instance.tables[t_name] = CalibrationMap3D(t_name, x_axis, y_axis, matrix)

        return instance

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ecu_type": self.ecu_type,
            "software_id": self.software_id,
            "vin": self.vin,
            "calibration_version": self.calibration_version,
            "vmax_disabled": self.vmax_disabled,
            "vmax_speed_limit_kmh": self.vmax_speed_limit_kmh,
            "flex_fuel_ethanol_pct": self.flex_fuel_ethanol_pct,
            "burble_enabled": self.burble_enabled,
            "burble_duration_sec": self.burble_duration_sec,
            "burble_retard_angle": self.burble_retard_angle,
            "burble_min_rpm": self.burble_min_rpm,
            "burble_aggression": self.burble_aggression,
            "cold_start_cat_heating_enabled": self.cold_start_cat_heating_enabled,
            "exhaust_flap_sport_open": self.exhaust_flap_sport_open,
            "linear_throttle_mapping": self.linear_throttle_mapping,
            "tables": {k: v.to_dict() for k, v in self.tables.items()}
        }
