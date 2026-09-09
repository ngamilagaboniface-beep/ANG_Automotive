"""
ISO 14229-1 UDS (Unified Diagnostic Services) Protocol Engine.
Full implementation of UDS request/response serialization, positive response byte shift (+0x40),
Negative Response Code (NRC) parsing, Routine Control, 50Hz high-speed RAM logging DIDs,
and RequestDownload / TransferData flash streaming state machine.
"""

from __future__ import annotations
import struct
import enum
import logging
from typing import Optional, Dict, Any, List, Tuple, Union

logger = logging.getLogger(__name__)

# ----------------- UDS Service Identifiers ----------------- #

class UDSService(enum.IntEnum):
    DIAGNOSTIC_SESSION_CONTROL = 0x10
    ECU_RESET = 0x11
    CLEAR_DIAGNOSTIC_INFORMATION = 0x14
    READ_DTC_INFORMATION = 0x19
    READ_DATA_BY_IDENTIFIER = 0x22
    READ_MEMORY_BY_ADDRESS = 0x23
    READ_SCALING_DATA_BY_IDENTIFIER = 0x24
    SECURITY_ACCESS = 0x27
    COMMUNICATION_CONTROL = 0x28
    READ_DATA_BY_PERIODIC_IDENTIFIER = 0x2A
    DYNAMICALLY_DEFINE_DATA_IDENTIFIER = 0x2C
    WRITE_DATA_BY_IDENTIFIER = 0x2E
    INPUT_OUTPUT_CONTROL_BY_IDENTIFIER = 0x2F
    ROUTINE_CONTROL = 0x31
    REQUEST_DOWNLOAD = 0x34
    REQUEST_UPLOAD = 0x35
    TRANSFER_DATA = 0x36
    REQUEST_TRANSFER_EXIT = 0x37
    WRITE_MEMORY_BY_ADDRESS = 0x3D
    TESTER_PRESENT = 0x3E
    CONTROL_DTC_SETTING = 0x85
    NEGATIVE_RESPONSE = 0x7F

class UDSNRC(enum.IntEnum):
    POSITIVE_RESPONSE = 0x00
    GENERAL_REJECT = 0x10
    SERVICE_NOT_SUPPORTED = 0x11
    SUB_FUNCTION_NOT_SUPPORTED = 0x12
    INCORRECT_MESSAGE_LENGTH = 0x13
    RESPONSE_TOO_LONG = 0x14
    BUSY_REPEAT_REQUEST = 0x21
    CONDITIONS_NOT_CORRECT = 0x22
    REQUEST_SEQUENCE_ERROR = 0x24
    NO_RESPONSE_FROM_SUBNET_COMPONENT = 0x25
    FAILURE_PREVENTS_EXECUTION = 0x26
    REQUEST_OUT_OF_RANGE = 0x31
    SECURITY_ACCESS_DENIED = 0x33
    INVALID_KEY = 0x35
    EXCEED_NUMBER_OF_ATTEMPTS = 0x36
    REQUIRED_TIME_DELAY_NOT_EXPIRED = 0x37
    SECURE_DATA_TRANSMISSION_REQUIRED = 0x38
    UPLOAD_DOWNLOAD_NOT_ACCEPTED = 0x70
    TRANSFER_DATA_SUSPENDED = 0x71
    GENERAL_PROGRAMMING_FAILURE = 0x72
    WRONG_BLOCK_SEQUENCE_COUNTER = 0x73
    REQUEST_CORRECTLY_RECEIVED_RESPONSE_PENDING = 0x78
    SUB_FUNCTION_NOT_SUPPORTED_IN_ACTIVE_SESSION = 0x7E
    SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION = 0x7F

class DiagnosticSessionType(enum.IntEnum):
    DEFAULT = 0x01
    PROGRAMMING = 0x02
    EXTENDED = 0x03
    SAFETY_SYSTEM = 0x04

class RoutineControlType(enum.IntEnum):
    START_ROUTINE = 0x01
    STOP_ROUTINE = 0x02
    REQUEST_ROUTINE_RESULTS = 0x03

class BMWKnownRoutines(enum.IntEnum):
    ERASE_FLASH_MEMORY = 0xFF00
    CHECK_PREPROGRAMMING_DEPENDENCIES = 0xFF01
    CHECK_PROGRAMMING_DEPENDENCIES = 0xFF02
    VERIFY_MEMORY_CHECKSUM = 0x0202
    FORCE_BOOTLOADER_RECOVERY = 0x0204

class BMWDataIdentifier(enum.IntEnum):
    # Standard UDS Identification
    BOOT_SOFTWARE_IDENT = 0xF180
    APPLICATION_SOFTWARE_IDENT = 0xF181
    APPLICATION_DATA_IDENT = 0xF182
    BOOT_SOFTWARE_FINGERPRINT = 0xF183
    ECU_MANUFACTURING_DATE = 0xF18B
    ECU_SERIAL_NUMBER = 0xF18C
    VIN_DATA = 0xF190
    VEHICLE_MANUFACTURER_ECU_HW_NUMBER = 0xF191
    SYSTEM_SUPPLIER_ECU_HW_NUMBER = 0xF192
    SYSTEM_SUPPLIER_ECU_SW_NUMBER = 0xF194
    CALIBRATION_ID_CVN = 0xF188
    # High-Speed 50Hz Real-Time Telematics DIDs
    ENGINE_RPM = 0xF40C
    VEHICLE_SPEED = 0xF40D
    AFR_LAMBDA = 0x0100
    BOOST_TARGET = 0x0101
    ACTUAL_BOOST_MAP = 0x0102
    IGNITION_TIMING_CYL1_6 = 0x0103
    KNOCK_RETARD_CYL1_6 = 0x0104
    WASTEGATE_DUTY_CYCLE = 0x0105
    COOLANT_TEMPERATURE = 0x0106
    OIL_TEMPERATURE = 0x0107
    EXHAUST_GAS_TEMPERATURE = 0x0108
    ETHANOL_CONTENT = 0x0109
    THROTTLE_PEDAL_POSITION = 0x010A
    MASS_AIRFLOW_LOAD = 0x010B
    FUEL_PRESSURE_RAIL = 0x010C

# ----------------- UDS Message Construction & Parsing ----------------- #

class UDSMessage:
    """Represents a generic UDS frame."""
    def __init__(self, sid: Union[UDSService, int], data: bytes = b"") -> None:
        self.sid = int(sid)
        self.data = data

    def pack(self) -> bytes:
        return struct.pack("!B", self.sid) + self.data

    @property
    def is_negative_response(self) -> bool:
        return self.sid == UDSService.NEGATIVE_RESPONSE

    @property
    def is_positive_response(self) -> bool:
        return not self.is_negative_response and (self.sid >= 0x40 and self.sid <= 0x7E)

    @classmethod
    def unpack(cls, raw: bytes) -> "UDSMessage":
        if len(raw) < 1:
            raise ValueError("Raw UDS byte buffer cannot be empty")
        sid = raw[0]
        data = raw[1:]
        if sid == UDSService.NEGATIVE_RESPONSE:
            if len(data) < 2:
                raise ValueError("Negative response must contain at least rejected SID and NRC")
            rej_sid, nrc_code = struct.unpack("!BB", data[:2])
            return UDSNegativeResponse(rej_sid, UDSNRC(nrc_code) if nrc_code in [c.value for c in UDSNRC] else nrc_code)
        return cls(sid, data)

    def __repr__(self) -> str:
        try:
            s_name = UDSService(self.sid).name
        except ValueError:
            s_name = f"0x{self.sid:02X}"
        return f"<UDSMessage SID={s_name} data_len={len(self.data)}>"

class UDSNegativeResponse(UDSMessage):
    """0x7F Negative Response Message: [0x7F, RejectedSID, NRC]."""
    def __init__(self, rejected_sid: int, nrc: Union[UDSNRC, int]) -> None:
        self.rejected_sid = rejected_sid
        self.nrc = UDSNRC(nrc) if isinstance(nrc, int) and nrc in [c.value for c in UDSNRC] else nrc
        super().__init__(UDSService.NEGATIVE_RESPONSE, struct.pack("!BB", rejected_sid, int(self.nrc)))

    @property
    def is_pending(self) -> bool:
        return self.nrc == UDSNRC.REQUEST_CORRECTLY_RECEIVED_RESPONSE_PENDING

    def __repr__(self) -> str:
        nrc_name = self.nrc.name if isinstance(self.nrc, UDSNRC) else f"0x{int(self.nrc):02X}"
        return f"<UDSNegativeResponse RejSID=0x{self.rejected_sid:02X} NRC={nrc_name}>"

class UDSPositiveResponse(UDSMessage):
    """Helper for positive response (+0x40 shift)."""
    def __init__(self, request_sid: int, data: bytes = b"") -> None:
        positive_sid = request_sid + 0x40
        super().__init__(positive_sid, data)
        self.original_request_sid = request_sid

# ----------------- Service Builders & Parsers ----------------- #

class DiagnosticSessionControl:
    @staticmethod
    def build_request(session_type: DiagnosticSessionType) -> UDSMessage:
        return UDSMessage(UDSService.DIAGNOSTIC_SESSION_CONTROL, struct.pack("!B", int(session_type)))

    @staticmethod
    def build_response(session_type: DiagnosticSessionType, p2_server_max_ms: int = 50, p2_star_server_max_ms: int = 5000) -> UDSMessage:
        # P2: 1ms resolution (uint16), P2*: 10ms resolution (uint16)
        p2_val = int(p2_server_max_ms)
        p2_star_val = int(p2_star_server_max_ms // 10)
        payload = struct.pack("!BHH", int(session_type), p2_val, p2_star_val)
        return UDSPositiveResponse(UDSService.DIAGNOSTIC_SESSION_CONTROL, payload)

    @staticmethod
    def parse_response(msg: UDSMessage) -> Dict[str, Any]:
        if msg.sid != UDSService.DIAGNOSTIC_SESSION_CONTROL + 0x40:
            raise ValueError(f"Invalid positive response SID: 0x{msg.sid:02X}")
        if len(msg.data) < 1:
            raise ValueError("Payload too short for DiagnosticSessionControl response")
        session_type = msg.data[0]
        p2_ms = None
        p2_star_ms = None
        if len(msg.data) >= 5:
            p2_val, p2_star_val = struct.unpack("!HH", msg.data[1:5])
            p2_ms = p2_val
            p2_star_ms = p2_star_val * 10
        return {
            "session_type": DiagnosticSessionType(session_type) if session_type in [s.value for s in DiagnosticSessionType] else session_type,
            "p2_max_ms": p2_ms,
            "p2_star_max_ms": p2_star_ms
        }

class SecurityAccess:
    @staticmethod
    def build_request_seed(sub_function: int) -> UDSMessage:
        return UDSMessage(UDSService.SECURITY_ACCESS, struct.pack("!B", sub_function))

    @staticmethod
    def build_send_key(sub_function: int, key: bytes) -> UDSMessage:
        return UDSMessage(UDSService.SECURITY_ACCESS, struct.pack("!B", sub_function) + key)

    @staticmethod
    def build_seed_response(sub_function: int, seed: bytes) -> UDSMessage:
        return UDSPositiveResponse(UDSService.SECURITY_ACCESS, struct.pack("!B", sub_function) + seed)

    @staticmethod
    def build_key_accepted_response(sub_function: int) -> UDSMessage:
        return UDSPositiveResponse(UDSService.SECURITY_ACCESS, struct.pack("!B", sub_function))

class RoutineControl:
    @staticmethod
    def build_request(control_type: RoutineControlType, routine_id: Union[BMWKnownRoutines, int], option_record: bytes = b"") -> UDSMessage:
        payload = struct.pack("!BH", int(control_type), int(routine_id)) + option_record
        return UDSMessage(UDSService.ROUTINE_CONTROL, payload)

    @staticmethod
    def build_response(control_type: RoutineControlType, routine_id: Union[BMWKnownRoutines, int], routine_status_record: bytes = b"") -> UDSMessage:
        payload = struct.pack("!BH", int(control_type), int(routine_id)) + routine_status_record
        return UDSPositiveResponse(UDSService.ROUTINE_CONTROL, payload)

    @staticmethod
    def parse_response(msg: UDSMessage) -> Dict[str, Any]:
        if msg.sid != UDSService.ROUTINE_CONTROL + 0x40:
            raise ValueError(f"Invalid positive response SID: 0x{msg.sid:02X}")
        if len(msg.data) < 3:
            raise ValueError("Payload too short for RoutineControl response")
        ctype, r_id = struct.unpack("!BH", msg.data[:3])
        status_record = msg.data[3:]
        return {
            "control_type": RoutineControlType(ctype) if ctype in [c.value for c in RoutineControlType] else ctype,
            "routine_id": r_id,
            "status_record": status_record
        }

class RequestDownload:
    @staticmethod
    def build_request(
        memory_address: int,
        memory_size: int,
        data_format_identifier: int = 0x00,
        address_bytes: int = 4,
        size_bytes: int = 4
    ) -> UDSMessage:
        address_and_length_format = ((size_bytes & 0x0F) << 4) | (address_bytes & 0x0F)
        addr_fmt = f"!{address_bytes}s"
        size_fmt = f"!{size_bytes}s"
        addr_packed = memory_address.to_bytes(address_bytes, byteorder="big")
        size_packed = memory_size.to_bytes(size_bytes, byteorder="big")
        payload = struct.pack("!BB", data_format_identifier, address_and_length_format) + addr_packed + size_packed
        return UDSMessage(UDSService.REQUEST_DOWNLOAD, payload)

    @staticmethod
    def build_response(max_number_of_block_length: int = 4095) -> UDSMessage:
        # 2-byte max block length representation
        len_format = 0x20  # 2 bytes length parameter
        payload = struct.pack("!BH", len_format, max_number_of_block_length)
        return UDSPositiveResponse(UDSService.REQUEST_DOWNLOAD, payload)

    @staticmethod
    def parse_response(msg: UDSMessage) -> int:
        if msg.sid != UDSService.REQUEST_DOWNLOAD + 0x40:
            raise ValueError(f"Invalid positive response SID: 0x{msg.sid:02X}")
        if len(msg.data) < 2:
            raise ValueError("Payload too short for RequestDownload response")
        len_format = msg.data[0]
        num_len_bytes = (len_format >> 4) & 0x0F
        if num_len_bytes == 0 or len(msg.data) < 1 + num_len_bytes:
            num_len_bytes = len(msg.data) - 1
        max_len = int.from_bytes(msg.data[1:1+num_len_bytes], byteorder="big")
        return max_len

class TransferData:
    @staticmethod
    def build_request(block_sequence_counter: int, data_record: bytes) -> UDSMessage:
        payload = struct.pack("!B", block_sequence_counter & 0xFF) + data_record
        return UDSMessage(UDSService.TRANSFER_DATA, payload)

    @staticmethod
    def build_response(block_sequence_counter: int, response_record: bytes = b"") -> UDSMessage:
        payload = struct.pack("!B", block_sequence_counter & 0xFF) + response_record
        return UDSPositiveResponse(UDSService.TRANSFER_DATA, payload)

    @staticmethod
    def parse_response(msg: UDSMessage) -> Dict[str, Any]:
        if msg.sid != UDSService.TRANSFER_DATA + 0x40:
            raise ValueError(f"Invalid positive response SID: 0x{msg.sid:02X}")
        if len(msg.data) < 1:
            raise ValueError("Payload too short for TransferData response")
        seq = msg.data[0]
        record = msg.data[1:]
        return {"block_sequence_counter": seq, "record": record}

class RequestTransferExit:
    @staticmethod
    def build_request(transfer_request_parameter_record: bytes = b"") -> UDSMessage:
        return UDSMessage(UDSService.REQUEST_TRANSFER_EXIT, transfer_request_parameter_record)

    @staticmethod
    def build_response(transfer_response_parameter_record: bytes = b"") -> UDSMessage:
        return UDSPositiveResponse(UDSService.REQUEST_TRANSFER_EXIT, transfer_response_parameter_record)


# ----------------- 50Hz High-Speed Live Telematics DIDs ----------------- #

class TelematicsEncoderDecoder:
    """Encodes and decodes 50Hz live sensor DIDs with exact scaling formulas."""

    @staticmethod
    def encode_rpm(rpm: float) -> bytes:
        val = int(max(0.0, min(16383.75, rpm)) / 0.25)
        return struct.pack("!H", val)

    @staticmethod
    def decode_rpm(data: bytes) -> float:
        val = struct.unpack("!H", data[:2])[0]
        return round(val * 0.25, 2)

    @staticmethod
    def encode_speed(speed_kmh: float) -> bytes:
        val = int(max(0, min(255, round(speed_kmh))))
        return struct.pack("!B", val)

    @staticmethod
    def decode_speed(data: bytes) -> float:
        return float(data[0])

    @staticmethod
    def encode_afr_lambda(lambda_actual: float, lambda_target: float) -> bytes:
        act_val = int(max(0.0, min(65.535, lambda_actual)) * 1000)
        tgt_val = int(max(0.0, min(65.535, lambda_target)) * 1000)
        return struct.pack("!HH", act_val, tgt_val)

    @staticmethod
    def decode_afr_lambda(data: bytes) -> Dict[str, float]:
        act_val, tgt_val = struct.unpack("!HH", data[:4])
        l_act = act_val / 1000.0
        l_tgt = tgt_val / 1000.0
        return {
            "lambda_actual": round(l_act, 3),
            "lambda_target": round(l_tgt, 3),
            "afr_actual": round(l_act * 14.7, 2),
            "afr_target": round(l_tgt * 14.7, 2)
        }

    @staticmethod
    def encode_boost(boost_target_hpa: float, boost_actual_hpa: float) -> bytes:
        tgt = int(max(0, min(65535, round(boost_target_hpa))))
        act = int(max(0, min(65535, round(boost_actual_hpa))))
        return struct.pack("!HH", tgt, act)

    @staticmethod
    def decode_boost(data: bytes) -> Dict[str, float]:
        tgt, act = struct.unpack("!HH", data[:4])
        bar_act = act / 1000.0
        bar_tgt = tgt / 1000.0
        # Gauge PSI (relative to 1013.25 hPa)
        psi_act = max(0.0, (act - 1013.25) * 0.0145038)
        psi_tgt = max(0.0, (tgt - 1013.25) * 0.0145038)
        return {
            "boost_target_hpa": float(tgt),
            "boost_actual_hpa": float(act),
            "boost_target_bar": round(bar_tgt, 3),
            "boost_actual_bar": round(bar_act, 3),
            "boost_target_psi": round(psi_tgt, 2),
            "boost_actual_psi": round(psi_act, 2)
        }

    @staticmethod
    def encode_ignition_timing(cyl_advances: List[float]) -> bytes:
        # 6 cylinders signed int16 (0.1 deg / bit)
        advs = [int(round(a * 10)) for a in cyl_advances[:6]]
        while len(advs) < 6:
            advs.append(0)
        return struct.pack("!6h", *advs)

    @staticmethod
    def decode_ignition_timing(data: bytes) -> List[float]:
        vals = struct.unpack("!6h", data[:12])
        return [round(v / 10.0, 1) for v in vals]

    @staticmethod
    def encode_knock_retard(cyl_retards: List[float]) -> bytes:
        # 6 cylinders uint8 (0.1 deg / bit)
        rets = [int(max(0.0, min(25.5, r)) * 10) for r in cyl_retards[:6]]
        while len(rets) < 6:
            rets.append(0)
        return struct.pack("!6B", *rets)

    @staticmethod
    def decode_knock_retard(data: bytes) -> List[float]:
        vals = struct.unpack("!6B", data[:6])
        return [round(v / 10.0, 1) for v in vals]

    @staticmethod
    def encode_wgdc(wgdc_pct: float) -> bytes:
        val = int(max(0.0, min(100.0, wgdc_pct)) * 10)
        return struct.pack("!H", val)

    @staticmethod
    def decode_wgdc(data: bytes) -> float:
        val = struct.unpack("!H", data[:2])[0]
        return round(val / 10.0, 1)

    @staticmethod
    def encode_temperatures(coolant_c: float, oil_c: float, egt_c: float) -> bytes:
        c_val = int(max(-40.0, min(215.0, coolant_c)) + 40)
        o_val = int(max(-40.0, min(215.0, oil_c)) + 40)
        egt_val = int(max(0.0, min(1500.0, egt_c)))
        return struct.pack("!BBH", c_val, o_val, egt_val)

    @staticmethod
    def decode_temperatures(data: bytes) -> Dict[str, float]:
        c_val, o_val, egt_val = struct.unpack("!BBH", data[:4])
        return {
            "coolant_c": float(c_val - 40),
            "oil_c": float(o_val - 40),
            "egt_c": float(egt_val)
        }

    @staticmethod
    def encode_telemetry_snapshot(snap: Dict[str, Any]) -> bytes:
        """Packs full multi-DID telemetry snapshot frame."""
        rpm_b = TelematicsEncoderDecoder.encode_rpm(snap.get("rpm", 0.0))
        speed_b = TelematicsEncoderDecoder.encode_speed(snap.get("speed", 0.0))
        afr_b = TelematicsEncoderDecoder.encode_afr_lambda(snap.get("lambda_actual", 1.0), snap.get("lambda_target", 1.0))
        boost_b = TelematicsEncoderDecoder.encode_boost(snap.get("boost_target_hpa", 1013.25), snap.get("boost_actual_hpa", 1013.25))
        timing_b = TelematicsEncoderDecoder.encode_ignition_timing(snap.get("ignition_timing", [15.0]*6))
        knock_b = TelematicsEncoderDecoder.encode_knock_retard(snap.get("knock_retard", [0.0]*6))
        wgdc_b = TelematicsEncoderDecoder.encode_wgdc(snap.get("wgdc", 0.0))
        temps_b = TelematicsEncoderDecoder.encode_temperatures(snap.get("coolant_c", 90.0), snap.get("oil_c", 95.0), snap.get("egt_c", 650.0))
        eth_b = struct.pack("!B", int(max(0, min(100, snap.get("ethanol_pct", 10)))))
        pedal_b = struct.pack("!H", int(max(0, min(100, snap.get("pedal_pct", 0))) * 10))
        fuel_b = struct.pack("!HH", int(snap.get("hpfp_bar", 200.0) * 10), int(snap.get("lpfp_bar", 6.5) * 10))
        return rpm_b + speed_b + afr_b + boost_b + timing_b + knock_b + wgdc_b + temps_b + eth_b + pedal_b + fuel_b

    @staticmethod
    def decode_telemetry_snapshot(raw: bytes) -> Dict[str, Any]:
        """Unpacks full multi-DID telemetry snapshot frame."""
        if len(raw) < 38:
            raise ValueError(f"Raw telemetry frame too short: {len(raw)} bytes (expected >= 38)")
        rpm = TelematicsEncoderDecoder.decode_rpm(raw[0:2])
        speed = TelematicsEncoderDecoder.decode_speed(raw[2:3])
        afr = TelematicsEncoderDecoder.decode_afr_lambda(raw[3:7])
        boost = TelematicsEncoderDecoder.decode_boost(raw[7:11])
        timing = TelematicsEncoderDecoder.decode_ignition_timing(raw[11:23])
        knock = TelematicsEncoderDecoder.decode_knock_retard(raw[23:29])
        wgdc = TelematicsEncoderDecoder.decode_wgdc(raw[29:31])
        temps = TelematicsEncoderDecoder.decode_temperatures(raw[31:35])
        eth = raw[35]
        pedal = struct.unpack("!H", raw[36:38])[0] / 10.0
        hpfp, lpfp = 200.0, 6.5
        if len(raw) >= 42:
            h_val, l_val = struct.unpack("!HH", raw[38:42])
            hpfp = h_val / 10.0
            lpfp = l_val / 10.0

        return {
            "rpm": rpm,
            "speed": speed,
            "lambda_actual": afr["lambda_actual"],
            "lambda_target": afr["lambda_target"],
            "afr_actual": afr["afr_actual"],
            "afr_target": afr["afr_target"],
            "boost_target_hpa": boost["boost_target_hpa"],
            "boost_actual_hpa": boost["boost_actual_hpa"],
            "boost_target_psi": boost["boost_target_psi"],
            "boost_actual_psi": boost["boost_actual_psi"],
            "ignition_timing": timing,
            "knock_retard": knock,
            "wgdc": wgdc,
            "coolant_c": temps["coolant_c"],
            "oil_c": temps["oil_c"],
            "egt_c": temps["egt_c"],
            "ethanol_pct": eth,
            "pedal_pct": pedal,
            "hpfp_bar": hpfp,
            "lpfp_bar": lpfp
        }
