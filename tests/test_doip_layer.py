"""
Test Suite for ISO 13400-2 DoIP Transport Layer.
Tests frame structures, headers, payloads, logical addresses, routing activation, and error framing.
"""

import pytest
import struct
from ang_telematics.protocols.doip import (
    DoIPHeader, DoIPMessage, DoIPPayloadType,
    BMWLogicalAddress, GenericNackCode, RoutingActivationCode, DiagnosticMessageNackCode,
    VehicleIdentificationRequest, VehicleAnnouncementMessage,
    RoutingActivationRequest, RoutingActivationResponse,
    DiagnosticMessage, DiagnosticMessageAck, DiagnosticMessageNack,
    AliveCheckRequest, AliveCheckResponse
)

def test_doip_header_packing_and_unpacking():
    header = DoIPHeader(payload_type=DoIPPayloadType.ROUTING_ACTIVATION_REQ, payload_length=7)
    packed = header.pack()

    assert len(packed) == 8
    assert packed[0] == 0x02  # ISO 13400-2 Version
    assert packed[1] == 0xFD  # Inverse Version (0xFF ^ 0x02)
    assert packed[2:4] == b"\x00\x05"  # Payload type 0x0005
    assert packed[4:8] == struct.pack("!I", 7)

    unpacked = DoIPHeader.unpack(packed)
    assert unpacked.protocol_version == 0x02
    assert unpacked.inverse_version == 0xFD
    assert unpacked.payload_type == DoIPPayloadType.ROUTING_ACTIVATION_REQ
    assert unpacked.payload_length == 7

def test_doip_header_invalid_inverse_version_rejection():
    # Corrupted inverse version
    corrupt_data = bytes([0x02, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00, 0x07])
    with pytest.raises(ValueError, match="Header protocol version mismatch"):
        DoIPHeader.unpack(corrupt_data)

def test_vehicle_announcement_message():
    vin = "WBA3R9C50K5A12345"
    logical_addr = BMWLogicalAddress.DME_MASTER
    eid = b"\x00\x1C\x69\xAA\xBB\xCC"
    gid = b"\x00\x00\x00\x00\x00\x01"

    msg = VehicleAnnouncementMessage(vin, logical_addr, eid, gid)
    packed = msg.pack()

    unpacked = DoIPMessage.unpack(packed)
    assert unpacked.header.payload_type == DoIPPayloadType.VEHICLE_ANNOUNCEMENT
    parsed = VehicleAnnouncementMessage.parse_payload(unpacked.payload)

    assert parsed["vin"] == vin
    assert parsed["logical_address"] == BMWLogicalAddress.DME_MASTER
    assert parsed["eid"] == "001c69aabbcc"
    assert parsed["gid"] == "000000000001"

def test_routing_activation_request_and_response():
    req = RoutingActivationRequest(source_address=BMWLogicalAddress.TESTER_FLASH)
    req_packed = req.pack()
    unpacked_req = DoIPMessage.unpack(req_packed)
    req_info = RoutingActivationRequest.parse_payload(unpacked_req.payload)
    assert req_info["source_address"] == BMWLogicalAddress.TESTER_FLASH

    resp = RoutingActivationResponse(
        tester_address=BMWLogicalAddress.TESTER_FLASH,
        entity_address=BMWLogicalAddress.ZGW,
        response_code=RoutingActivationCode.SUCCESSFULLY_ROUTED
    )
    resp_packed = resp.pack()
    unpacked_resp = DoIPMessage.unpack(resp_packed)
    resp_info = RoutingActivationResponse.parse_payload(unpacked_resp.payload)

    assert resp_info["tester_address"] == BMWLogicalAddress.TESTER_FLASH
    assert resp_info["entity_address"] == BMWLogicalAddress.ZGW
    assert resp_info["response_code"] == RoutingActivationCode.SUCCESSFULLY_ROUTED

def test_diagnostic_message_framing():
    uds_payload = b"\x22\xF1\x90"  # Read DID 0xF190 (VIN)
    diag_msg = DiagnosticMessage(
        source_address=BMWLogicalAddress.TESTER_FLASH,
        target_address=BMWLogicalAddress.DME_MASTER,
        user_data=uds_payload
    )
    packed = diag_msg.pack()

    unpacked_doip = DoIPMessage.unpack(packed)
    assert unpacked_doip.header.payload_type == DoIPPayloadType.DIAGNOSTIC_MESSAGE

    diag_unpacked = DiagnosticMessage.from_payload(unpacked_doip.payload)
    assert diag_unpacked.source_address == BMWLogicalAddress.TESTER_FLASH
    assert diag_unpacked.target_address == BMWLogicalAddress.DME_MASTER
    assert diag_unpacked.user_data == uds_payload

def test_diagnostic_message_ack_and_nack():
    ack = DiagnosticMessageAck(BMWLogicalAddress.DME_MASTER, BMWLogicalAddress.TESTER_FLASH, ack_code=0x00)
    ack_packed = ack.pack()
    unpacked_ack = DoIPMessage.unpack(ack_packed)
    assert unpacked_ack.header.payload_type == DoIPPayloadType.DIAGNOSTIC_MESSAGE_ACK

    nack = DiagnosticMessageNack(BMWLogicalAddress.DME_MASTER, BMWLogicalAddress.TESTER_FLASH, DiagnosticMessageNackCode.UNKNOWN_TARGET_ADDRESS)
    nack_packed = nack.pack()
    unpacked_nack = DoIPMessage.unpack(nack_packed)
    assert unpacked_nack.header.payload_type == DoIPPayloadType.DIAGNOSTIC_MESSAGE_NACK
    assert unpacked_nack.payload[4] == DiagnosticMessageNackCode.UNKNOWN_TARGET_ADDRESS

def test_bmw_logical_addresses_enum():
    assert BMWLogicalAddress.ZGW == 0x0010
    assert BMWLogicalAddress.DME_MASTER == 0x0012
    assert BMWLogicalAddress.DME_SLAVE == 0x0013
    assert BMWLogicalAddress.EGS == 0x0018
    assert BMWLogicalAddress.DSC == 0x0028
    assert BMWLogicalAddress.TESTER_FLASH == 0x0E80
