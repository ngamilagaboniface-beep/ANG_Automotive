"""
Test Suite for ISO 14229 UDS Protocol Engine.
Tests positive response byte shifts (+0x40), NRC handling, Routine Control,
flashing services (0x34, 0x36, 0x37), and 50Hz high-speed telemetry DID encoding/decoding.
"""

import pytest
import struct
from ang_telematics.protocols.uds import (
    UDSService, UDSNRC, DiagnosticSessionType, RoutineControlType,
    BMWKnownRoutines, BMWDataIdentifier, UDSMessage, UDSNegativeResponse,
    UDSPositiveResponse, DiagnosticSessionControl, SecurityAccess,
    RoutineControl, RequestDownload, TransferData, RequestTransferExit,
    TelematicsEncoderDecoder
)

def test_uds_positive_response_byte_shift():
    # DiagnosticSessionControl (0x10) -> Positive response is 0x50 (+0x40)
    pos_rsp = DiagnosticSessionControl.build_response(DiagnosticSessionType.PROGRAMMING, 50, 5000)
    assert pos_rsp.sid == 0x50
    assert pos_rsp.is_positive_response
    assert not pos_rsp.is_negative_response

    parsed = DiagnosticSessionControl.parse_response(pos_rsp)
    assert parsed["session_type"] == DiagnosticSessionType.PROGRAMMING
    assert parsed["p2_max_ms"] == 50
    assert parsed["p2_star_max_ms"] == 5000

    # ReadDataByIdentifier (0x22) -> Positive response is 0x62 (+0x40)
    rdbi_rsp = UDSPositiveResponse(UDSService.READ_DATA_BY_IDENTIFIER, b"\xF1\x90WBA3R9C50K5A12345")
    assert rdbi_rsp.sid == 0x62

    # RoutineControl (0x31) -> Positive response is 0x71 (+0x40)
    rc_rsp = RoutineControl.build_response(RoutineControlType.START_ROUTINE, BMWKnownRoutines.ERASE_FLASH_MEMORY, b"\x00")
    assert rc_rsp.sid == 0x71

def test_uds_negative_response_handling():
    raw_nrc_msg = bytes([0x7F, 0x10, 0x12])  # 0x7F, Rejected SID 0x10, NRC 0x12 (SubFunctionNotSupported)
    unpacked = UDSMessage.unpack(raw_nrc_msg)

    assert isinstance(unpacked, UDSNegativeResponse)
    assert unpacked.is_negative_response
    assert not unpacked.is_positive_response
    assert unpacked.rejected_sid == 0x10
    assert unpacked.nrc == UDSNRC.SUB_FUNCTION_NOT_SUPPORTED

    # Test all specified NRCs
    nrc_codes = [
        UDSNRC.SERVICE_NOT_SUPPORTED,
        UDSNRC.SUB_FUNCTION_NOT_SUPPORTED,
        UDSNRC.INCORRECT_MESSAGE_LENGTH,
        UDSNRC.CONDITIONS_NOT_CORRECT,
        UDSNRC.REQUEST_SEQUENCE_ERROR,
        UDSNRC.REQUEST_OUT_OF_RANGE,
        UDSNRC.SECURITY_ACCESS_DENIED,
        UDSNRC.INVALID_KEY,
        UDSNRC.EXCEED_NUMBER_OF_ATTEMPTS,
        UDSNRC.REQUEST_CORRECTLY_RECEIVED_RESPONSE_PENDING,
        UDSNRC.SUB_FUNCTION_NOT_SUPPORTED_IN_ACTIVE_SESSION,
    ]
    for nrc in nrc_codes:
        nrc_msg = UDSNegativeResponse(0x27, nrc)
        packed = nrc_msg.pack()
        unpacked_nrc = UDSMessage.unpack(packed)
        assert isinstance(unpacked_nrc, UDSNegativeResponse)
        assert unpacked_nrc.nrc == nrc

def test_response_pending_nrc_78():
    pending_msg = UDSNegativeResponse(0x31, UDSNRC.REQUEST_CORRECTLY_RECEIVED_RESPONSE_PENDING)
    assert pending_msg.is_pending
    assert pending_msg.nrc == 0x78

def test_security_access_seed_and_key_messages():
    # Level 3 (Programming)
    req_seed = SecurityAccess.build_request_seed(0x03)
    assert req_seed.sid == 0x27
    assert req_seed.data == b"\x03"

    test_seed = bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88])
    resp_seed = SecurityAccess.build_seed_response(0x03, test_seed)
    assert resp_seed.sid == 0x67
    assert resp_seed.data == b"\x03" + test_seed

    test_key = bytes([0xAA, 0xBB, 0xCC, 0xDD])
    send_key = SecurityAccess.build_send_key(0x04, test_key)
    assert send_key.sid == 0x27
    assert send_key.data == b"\x04" + test_key

    key_ok = SecurityAccess.build_key_accepted_response(0x04)
    assert key_ok.sid == 0x67
    assert key_ok.data == b"\x04"

def test_routine_control_erase_and_checksum():
    req = RoutineControl.build_request(RoutineControlType.START_ROUTINE, BMWKnownRoutines.ERASE_FLASH_MEMORY, struct.pack("!II", 0x08000000, 0x00080000))
    assert req.sid == 0x31
    assert len(req.data) == 3 + 8

    resp = RoutineControl.build_response(RoutineControlType.START_ROUTINE, BMWKnownRoutines.ERASE_FLASH_MEMORY, b"\x00")
    assert resp.sid == 0x71
    parsed = RoutineControl.parse_response(resp)
    assert parsed["control_type"] == RoutineControlType.START_ROUTINE
    assert parsed["routine_id"] == BMWKnownRoutines.ERASE_FLASH_MEMORY

def test_flash_streaming_services():
    # 0x34 RequestDownload
    req_dl = RequestDownload.build_request(0x08000000, 262144)
    assert req_dl.sid == 0x34

    rsp_dl = RequestDownload.build_response(4095)
    assert rsp_dl.sid == 0x74
    max_len = RequestDownload.parse_response(rsp_dl)
    assert max_len == 4095

    # 0x36 TransferData
    payload_chunk = b"\xAA" * 1024
    req_td = TransferData.build_request(1, payload_chunk)
    assert req_td.sid == 0x36
    assert req_td.data[0] == 1  # Sequence counter
    assert req_td.data[1:] == payload_chunk

    rsp_td = TransferData.build_response(1)
    assert rsp_td.sid == 0x76
    td_parsed = TransferData.parse_response(rsp_td)
    assert td_parsed["block_sequence_counter"] == 1

    # 0x37 RequestTransferExit
    req_exit = RequestTransferExit.build_request()
    assert req_exit.sid == 0x37
    rsp_exit = RequestTransferExit.build_response()
    assert rsp_exit.sid == 0x77

def test_50hz_telematics_encoder_decoder():
    # RPM
    rpm_val = 6520.5
    rpm_b = TelematicsEncoderDecoder.encode_rpm(rpm_val)
    decoded_rpm = TelematicsEncoderDecoder.decode_rpm(rpm_b)
    assert abs(decoded_rpm - rpm_val) <= 0.25

    # AFR / Lambda
    l_act, l_tgt = 0.825, 0.840
    afr_b = TelematicsEncoderDecoder.encode_afr_lambda(l_act, l_tgt)
    decoded_afr = TelematicsEncoderDecoder.decode_afr_lambda(afr_b)
    assert decoded_afr["lambda_actual"] == 0.825
    assert decoded_afr["lambda_target"] == 0.840
    assert abs(decoded_afr["afr_actual"] - (0.825 * 14.7)) < 0.05

    # Boost (Target & Actual)
    b_tgt, b_act = 2250.0, 2245.0
    boost_b = TelematicsEncoderDecoder.encode_boost(b_tgt, b_act)
    decoded_boost = TelematicsEncoderDecoder.decode_boost(boost_b)
    assert decoded_boost["boost_target_hpa"] == 2250.0
    assert decoded_boost["boost_actual_hpa"] == 2245.0
    assert decoded_boost["boost_actual_bar"] == 2.245

    # Ignition Timing 6 Cylinders
    advances = [14.5, 14.0, 15.2, 14.8, 14.2, 15.0]
    timing_b = TelematicsEncoderDecoder.encode_ignition_timing(advances)
    decoded_timing = TelematicsEncoderDecoder.decode_ignition_timing(timing_b)
    assert decoded_timing == advances

    # Knock Retard 6 Cylinders
    retards = [0.0, 0.0, 1.2, 0.0, 0.0, 2.4]
    knock_b = TelematicsEncoderDecoder.encode_knock_retard(retards)
    decoded_knock = TelematicsEncoderDecoder.decode_knock_retard(knock_b)
    assert decoded_knock == retards

    # Full Multi-DID snapshot serialization
    snapshot = {
        "rpm": 5800.0,
        "speed": 160.0,
        "pedal_pct": 100.0,
        "lambda_actual": 0.82,
        "lambda_target": 0.82,
        "boost_target_hpa": 2200.0,
        "boost_actual_hpa": 2190.0,
        "ignition_timing": [12.0, 12.0, 11.5, 12.0, 12.0, 12.0],
        "knock_retard": [0.0, 0.0, 0.5, 0.0, 0.0, 0.0],
        "wgdc": 68.5,
        "coolant_c": 92.0,
        "oil_c": 98.0,
        "egt_c": 820.0,
        "ethanol_pct": 30,
        "hpfp_bar": 195.0,
        "lpfp_bar": 6.5
    }
    encoded_snap = TelematicsEncoderDecoder.encode_telemetry_snapshot(snapshot)
    decoded_snap = TelematicsEncoderDecoder.decode_telemetry_snapshot(encoded_snap)

    assert decoded_snap["rpm"] == 5800.0
    assert decoded_snap["speed"] == 160.0
    assert decoded_snap["lambda_actual"] == 0.82
    assert decoded_snap["boost_actual_hpa"] == 2190.0
    assert decoded_snap["wgdc"] == 68.5
    assert decoded_snap["coolant_c"] == 92.0
    assert decoded_snap["hpfp_bar"] == 195.0
