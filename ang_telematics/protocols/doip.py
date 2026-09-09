"""
ISO 13400-2 DoIP (Diagnostic over Internet Protocol) Transport Layer Implementation.
Full implementation of DoIP header serialization, deserialization, message framing,
vehicle discovery, routing activation, and BMW gateway/DME logical addressing.
"""

from __future__ import annotations
import struct
import enum
import socket
import logging
from typing import Optional, Tuple, Dict, Any, Union

logger = logging.getLogger(__name__)

# ISO 13400-2 Protocol Constants
DOIP_PROTOCOL_VERSION_2012: int = 0x02
DOIP_INVERSE_VERSION_2012: int = 0xFD
DOIP_DEFAULT_UDP_PORT: int = 13400
DOIP_DEFAULT_TCP_PORT: int = 13400
DOIP_HEADER_LENGTH: int = 8

# BMW Specific Logical Addresses
class BMWLogicalAddress(enum.IntEnum):
    ZGW = 0x0010         # Central Gateway / FEM / BDC
    DME_MASTER = 0x0012  # Primary Engine Control Unit (MEVD17 / MSD80 / MG1)
    DME_SLAVE = 0x0013   # Secondary Engine Control Unit (V8/V12 secondary bank)
    EGS = 0x0018         # Electronic Transmission Control (ZF 8HP / GS7D36SG DKG)
    DSC = 0x0028         # Dynamic Stability Control (Brembo / Bosch ABS/DSC)
    KOMBI = 0x0060       # Instrument Cluster
    FEM_BDC = 0x0040     # Front Electronic Module / Body Domain Controller
    TESTER_STD = 0x0E00  # Standard Diagnostic Tool
    TESTER_FLASH = 0x0E80 # High-speed ECU Flashing Tool

class DoIPPayloadType(enum.IntEnum):
    GENERIC_NACK = 0x0000
    VEHICLE_IDENT_REQ = 0x0001
    VEHICLE_IDENT_REQ_EID = 0x0002
    VEHICLE_IDENT_REQ_VIN = 0x0003
    VEHICLE_ANNOUNCEMENT = 0x0004
    ROUTING_ACTIVATION_REQ = 0x0005
    ROUTING_ACTIVATION_RESP = 0x0006
    ALIVE_CHECK_REQ = 0x0007
    ALIVE_CHECK_RESP = 0x0008
    ENTITY_STATUS_REQ = 0x4001
    ENTITY_STATUS_RESP = 0x4002
    POWER_MODE_INFO_REQ = 0x4003
    POWER_MODE_INFO_RESP = 0x4004
    DIAGNOSTIC_MESSAGE = 0x8001
    DIAGNOSTIC_MESSAGE_ACK = 0x8002
    DIAGNOSTIC_MESSAGE_NACK = 0x8003

class GenericNackCode(enum.IntEnum):
    INCORRECT_PATTERN_FORMAT = 0x00
    UNKNOWN_PAYLOAD_TYPE = 0x01
    MESSAGE_TOO_LARGE = 0x02
    OUT_OF_MEMORY = 0x03
    INVALID_PAYLOAD_LENGTH = 0x04

class RoutingActivationCode(enum.IntEnum):
    UNKNOWN_SOURCE_ADDRESS = 0x00
    ALL_SOCKETS_REGISTERED = 0x01
    DIFFERENT_SOURCE_ADDRESS_ACTIVE = 0x02
    SOURCE_ADDRESS_ALREADY_ACTIVE = 0x03
    MISSING_AUTHENTICATION = 0x04
    REJECTED_CONFIRMATION = 0x05
    UNSUPPORTED_ACTIVATION_TYPE = 0x06
    SUCCESSFULLY_ROUTED = 0x10
    CONFIRMATION_REQUIRED = 0x11

class DiagnosticMessageNackCode(enum.IntEnum):
    INVALID_SOURCE_ADDRESS = 0x02
    UNKNOWN_TARGET_ADDRESS = 0x03
    MESSAGE_TOO_LARGE = 0x04
    OUT_OF_MEMORY = 0x05
    TARGET_UNREACHABLE = 0x06
    UNKNOWN_NETWORK = 0x07
    TRANSPORT_PROTOCOL_ERROR = 0x08

class DoIPHeader:
    """ISO 13400-2 8-byte DoIP Header structure."""
    def __init__(
        self,
        payload_type: Union[DoIPPayloadType, int],
        payload_length: int,
        protocol_version: int = DOIP_PROTOCOL_VERSION_2012,
        inverse_version: Optional[int] = None
    ) -> None:
        self.protocol_version = protocol_version
        self.inverse_version = (0xFF ^ protocol_version) if inverse_version is None else inverse_version
        self.payload_type = DoIPPayloadType(payload_type) if isinstance(payload_type, int) else payload_type
        self.payload_length = payload_length

    def pack(self) -> bytes:
        return struct.pack(
            "!BBHI",
            self.protocol_version,
            self.inverse_version,
            int(self.payload_type),
            self.payload_length
        )

    @classmethod
    def unpack(cls, data: bytes) -> "DoIPHeader":
        if len(data) < DOIP_HEADER_LENGTH:
            raise ValueError(f"Data length {len(data)} is less than required header length {DOIP_HEADER_LENGTH}")
        proto_ver, inv_ver, p_type, p_len = struct.unpack("!BBHI", data[:DOIP_HEADER_LENGTH])
        if proto_ver != (0xFF ^ inv_ver) and proto_ver != 0xFF:
            raise ValueError(f"Header protocol version mismatch: ver=0x{proto_ver:02X}, inv=0x{inv_ver:02X}")
        try:
            ptype_enum = DoIPPayloadType(p_type)
        except ValueError:
            ptype_enum = p_type  # type: ignore
        return cls(ptype_enum, p_len, proto_ver, inv_ver)

class DoIPMessage:
    """Base DoIP Message with header and payload serialization."""
    def __init__(
        self,
        payload_type: Union[DoIPPayloadType, int],
        payload: bytes = b"",
        protocol_version: int = DOIP_PROTOCOL_VERSION_2012
    ) -> None:
        self.header = DoIPHeader(payload_type, len(payload), protocol_version)
        self.payload = payload

    def pack(self) -> bytes:
        self.header.payload_length = len(self.payload)
        return self.header.pack() + self.payload

    @classmethod
    def unpack(cls, data: bytes) -> "DoIPMessage":
        if len(data) < DOIP_HEADER_LENGTH:
            raise ValueError(f"Buffer too short for DoIP message: {len(data)} bytes")
        header = DoIPHeader.unpack(data[:DOIP_HEADER_LENGTH])
        expected_total = DOIP_HEADER_LENGTH + header.payload_length
        if len(data) < expected_total:
            raise ValueError(f"Incomplete DoIP frame: expected {expected_total} bytes, got {len(data)} bytes")
        payload = data[DOIP_HEADER_LENGTH:expected_total]
        return cls(header.payload_type, payload, header.protocol_version)

    def __repr__(self) -> str:
        return f"<DoIPMessage type={self.header.payload_type.name if isinstance(self.header.payload_type, DoIPPayloadType) else hex(self.header.payload_type)} len={len(self.payload)}>"

# ----------------- Specific DoIP Message Types ----------------- #

class VehicleIdentificationRequest(DoIPMessage):
    def __init__(self) -> None:
        super().__init__(DoIPPayloadType.VEHICLE_IDENT_REQ, b"")

class VehicleAnnouncementMessage(DoIPMessage):
    """
    Vehicle Announcement / Vehicle Identification Response (0x0004).
    Contains: VIN (17 bytes), Logical Address (2 bytes), EID/MAC (6 bytes), GID (6 bytes),
    Further Action Required (1 byte), Optional Sync Status (1 byte).
    """
    def __init__(
        self,
        vin: str,
        logical_address: int,
        eid: bytes,
        gid: bytes,
        further_action_required: int = 0x00,
        sync_status: Optional[int] = 0x00
    ) -> None:
        vin_bytes = vin.encode("ascii")[:17].ljust(17, b"\x00")
        eid_bytes = eid[:6].ljust(6, b"\x00")
        gid_bytes = gid[:6].ljust(6, b"\x00")
        payload = vin_bytes + struct.pack("!H", logical_address) + eid_bytes + gid_bytes + struct.pack("!B", further_action_required)
        if sync_status is not None:
            payload += struct.pack("!B", sync_status)
        super().__init__(DoIPPayloadType.VEHICLE_ANNOUNCEMENT, payload)
        self.vin = vin
        self.logical_address = logical_address
        self.eid = eid_bytes
        self.gid = gid_bytes
        self.further_action_required = further_action_required
        self.sync_status = sync_status

    @classmethod
    def parse_payload(cls, payload: bytes) -> Dict[str, Any]:
        if len(payload) < 32:
            raise ValueError(f"Payload length {len(payload)} insufficient for Vehicle Announcement (min 32)")
        vin = payload[:17].decode("ascii", errors="replace").rstrip("\x00")
        logical_addr = struct.unpack("!H", payload[17:19])[0]
        eid = payload[19:25]
        gid = payload[25:31]
        action = payload[31]
        sync = payload[32] if len(payload) > 32 else None
        return {
            "vin": vin,
            "logical_address": logical_addr,
            "eid": eid.hex(),
            "gid": gid.hex(),
            "further_action_required": action,
            "sync_status": sync
        }

class RoutingActivationRequest(DoIPMessage):
    """
    Routing Activation Request (0x0005).
    Source Address (2 bytes), Activation Type (1 byte), Reserved (4 bytes), Optional OEM Specific (4 bytes).
    """
    def __init__(
        self,
        source_address: int = BMWLogicalAddress.TESTER_FLASH,
        activation_type: int = 0x00, # 0x00 Default, 0xE0 BMW Central Security
        oem_reserved: bytes = b"\x00\x00\x00\x00"
    ) -> None:
        payload = struct.pack("!HB4s", source_address, activation_type, b"\x00\x00\x00\x00") + oem_reserved[:4]
        super().__init__(DoIPPayloadType.ROUTING_ACTIVATION_REQ, payload)
        self.source_address = source_address
        self.activation_type = activation_type

    @classmethod
    def parse_payload(cls, payload: bytes) -> Dict[str, Any]:
        if len(payload) < 7:
            raise ValueError("Payload too short for Routing Activation Request")
        src_addr, act_type = struct.unpack("!HB", payload[:3])
        return {"source_address": src_addr, "activation_type": act_type}

class RoutingActivationResponse(DoIPMessage):
    """
    Routing Activation Response (0x0006).
    Tester Logical Address (2 bytes), Entity Logical Address (2 bytes), Response Code (1 byte),
    Reserved (4 bytes), Optional OEM Specific (4 bytes).
    """
    def __init__(
        self,
        tester_address: int,
        entity_address: int,
        response_code: RoutingActivationCode = RoutingActivationCode.SUCCESSFULLY_ROUTED,
        oem_reserved: bytes = b"\x00\x00\x00\x00"
    ) -> None:
        payload = struct.pack("!HHB4s", tester_address, entity_address, int(response_code), b"\x00\x00\x00\x00") + oem_reserved[:4]
        super().__init__(DoIPPayloadType.ROUTING_ACTIVATION_RESP, payload)
        self.tester_address = tester_address
        self.entity_address = entity_address
        self.response_code = response_code

    @classmethod
    def parse_payload(cls, payload: bytes) -> Dict[str, Any]:
        if len(payload) < 9:
            raise ValueError("Payload too short for Routing Activation Response")
        t_addr, e_addr, code = struct.unpack("!HHB", payload[:5])
        return {
            "tester_address": t_addr,
            "entity_address": e_addr,
            "response_code": RoutingActivationCode(code) if code in [c.value for c in RoutingActivationCode] else code
        }

class DiagnosticMessage(DoIPMessage):
    """
    DoIP Diagnostic Message (0x8001).
    Source Address (2 bytes), Target Address (2 bytes), Diagnostic User Data / UDS payload (N bytes).
    """
    def __init__(
        self,
        source_address: int,
        target_address: int,
        user_data: bytes
    ) -> None:
        payload = struct.pack("!HH", source_address, target_address) + user_data
        super().__init__(DoIPPayloadType.DIAGNOSTIC_MESSAGE, payload)
        self.source_address = source_address
        self.target_address = target_address
        self.user_data = user_data

    @classmethod
    def from_payload(cls, payload: bytes) -> "DiagnosticMessage":
        if len(payload) < 4:
            raise ValueError("Payload too short for Diagnostic Message (minimum 4 bytes for addressing)")
        src_addr, tgt_addr = struct.unpack("!HH", payload[:4])
        user_data = payload[4:]
        msg = cls(src_addr, tgt_addr, user_data)
        return msg

class DiagnosticMessageAck(DoIPMessage):
    """DoIP Diagnostic Message Positive Ack (0x8002)."""
    def __init__(self, source_address: int, target_address: int, ack_code: int = 0x00, previous_data: bytes = b"") -> None:
        payload = struct.pack("!HHB", source_address, target_address, ack_code) + previous_data
        super().__init__(DoIPPayloadType.DIAGNOSTIC_MESSAGE_ACK, payload)
        self.source_address = source_address
        self.target_address = target_address
        self.ack_code = ack_code

class DiagnosticMessageNack(DoIPMessage):
    """DoIP Diagnostic Message Negative Ack (0x8003)."""
    def __init__(self, source_address: int, target_address: int, nack_code: DiagnosticMessageNackCode) -> None:
        payload = struct.pack("!HHB", source_address, target_address, int(nack_code))
        super().__init__(DoIPPayloadType.DIAGNOSTIC_MESSAGE_NACK, payload)
        self.source_address = source_address
        self.target_address = target_address
        self.nack_code = nack_code

class AliveCheckRequest(DoIPMessage):
    def __init__(self) -> None:
        super().__init__(DoIPPayloadType.ALIVE_CHECK_REQ, b"")

class AliveCheckResponse(DoIPMessage):
    def __init__(self, source_address: int) -> None:
        super().__init__(DoIPPayloadType.ALIVE_CHECK_RESP, struct.pack("!H", source_address))
        self.source_address = source_address
