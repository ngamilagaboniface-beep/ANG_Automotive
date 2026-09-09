"""
High-Fidelity BMW ECU & DoIP Gateway Simulator.
Emulates Bosch MEVD17, Siemens MSD80, and Bosch MG1 with complete ISO 13400 DoIP and ISO 14229 UDS stacks.
"""

from __future__ import annotations
import time
import math
import struct
import random
import threading
import socket
import logging
from typing import Optional, Dict, Any, Tuple
from ang_telematics.protocols.doip import (
    DoIPMessage, DoIPPayloadType, DoIPHeader,
    BMWLogicalAddress, RoutingActivationCode, DiagnosticMessageNackCode,
    VehicleAnnouncementMessage, RoutingActivationResponse, DiagnosticMessageAck
)
from ang_telematics.protocols.uds import (
    UDSService, UDSNRC, DiagnosticSessionType, RoutineControlType,
    BMWKnownRoutines, BMWDataIdentifier, UDSMessage, UDSNegativeResponse,
    UDSPositiveResponse, DiagnosticSessionControl, SecurityAccess,
    RoutineControl, RequestDownload, TransferData, RequestTransferExit,
    TelematicsEncoderDecoder
)
from ang_telematics.protocols.crypto import (
    BoschMEVD17Crypto, SiemensMSD80Crypto, BoschMG1Crypto,
    ChecksumEngine, RSAFlashVerifier, SeedKeyLevel
)
from ang_telematics.flashing.rom_manager import ECUType

logger = logging.getLogger(__name__)

class SimulatedECU:
    """
    Stateful BMW Engine Control Unit Simulator.
    Simulates memory, bootloader, security access, live telemetry physics, and flash writing.
    """
    def __init__(
        self,
        ecu_type: str = ECUType.BOSCH_MEVD17,
        vin: str = "WBA3R9C50K5A12345",
        sw_id: str = "00001E8B001",
        logical_address: int = BMWLogicalAddress.DME_MASTER
    ) -> None:
        self.ecu_type = ecu_type
        self.vin = vin
        self.sw_id = sw_id
        self.logical_address = logical_address

        # State Machine
        self.active_session = DiagnosticSessionType.DEFAULT
        self.security_level_unlocked: int = 0
        self.active_seed: Optional[bytes] = None
        self.active_seed_level: int = 0

        # Flash memory state
        self.flash_erased: bool = False
        self.download_in_progress: bool = False
        self.download_address: int = 0
        self.download_size: int = 0
        self.expected_block_seq: int = 1
        self.received_flash_buffer: bytearray = bytearray()
        self.flash_successful: bool = False

        # Live engine simulation parameters
        self.engine_running: bool = True
        self.sim_time: float = 0.0
        self.throttle_input: float = 0.0 # 0.0 to 100.0%
        self.simulated_fault_injection: Optional[str] = None # e.g. "NRC_78", "NRC_33", "FAIL_CRC"

        # Thread for physics simulation
        self._lock = threading.Lock()

    def set_fault_injection(self, fault: Optional[str]) -> None:
        with self._lock:
            self.simulated_fault_injection = fault

    def set_throttle(self, throttle_pct: float) -> None:
        with self._lock:
            self.throttle_input = max(0.0, min(100.0, float(throttle_pct)))

    def get_live_telemetry_snapshot(self) -> Dict[str, Any]:
        """Calculates dynamic engine physics based on throttle, RPM, and thermal buildup."""
        with self._lock:
            self.sim_time += 0.05
            t = self.sim_time
            th = self.throttle_input

            # RPM dynamic modeling
            if th > 0:
                target_rpm = 1000.0 + (th / 100.0) * 6000.0
                rpm = target_rpm + (math.sin(t * 8.0) * 45.0)
            else:
                rpm = 750.0 + (math.sin(t * 2.0) * 15.0) # Idle

            speed_kmh = max(0.0, (rpm / 7000.0) * 240.0 * (th / 100.0))

            # Boost physics
            if th > 30.0:
                boost_tgt = 1013.25 + (th / 100.0) * 1250.0
                # Lagged actual boost
                boost_act = boost_tgt * (0.95 + 0.05 * math.sin(t * 5.0))
                wgdc = min(92.0, 25.0 + (th * 0.65))
            else:
                boost_tgt = 1013.25
                boost_act = 1013.25 + (math.sin(t * 3.0) * 10.0)
                wgdc = 0.0

            # Lambda / AFR
            if th > 80.0:
                l_act = 0.82 + (math.sin(t * 4.0) * 0.015)
                l_tgt = 0.82
            elif th > 30.0:
                l_act = 0.90 + (math.sin(t * 2.0) * 0.01)
                l_tgt = 0.90
            else:
                l_act = 1.00 + (math.sin(t) * 0.005)
                l_tgt = 1.00

            # Timing & Knock
            base_timing = 32.0 - (th * 0.18) + ((rpm - 1000.0) * 0.002)
            timing_cyls = [round(base_timing + math.sin(t + c) * 0.4, 1) for c in range(6)]

            # Knock retard (simulated if throttle is 100% and knock fault or high RPM)
            if th > 95.0 and rpm > 5800:
                knock_cyls = [0.0, 0.0, 0.8, 0.0, 1.2, 0.0]
            else:
                knock_cyls = [0.0] * 6

            # Thermal progression
            coolant = 92.0 + (th * 0.08) + math.sin(t * 0.1) * 2.0
            oil = 98.0 + (th * 0.12) + math.sin(t * 0.08) * 3.0
            egt = 450.0 + (th * 4.2) + (rpm * 0.03)

            hpfp = max(150.0, 200.0 - (th * 0.25))

            return {
                "rpm": round(rpm, 1),
                "speed": round(speed_kmh, 1),
                "pedal_pct": round(th, 1),
                "lambda_actual": round(l_act, 3),
                "lambda_target": round(l_tgt, 3),
                "afr_actual": round(l_act * 14.7, 2),
                "afr_target": round(l_tgt * 14.7, 2),
                "boost_target_hpa": round(boost_tgt, 1),
                "boost_actual_hpa": round(boost_act, 1),
                "boost_target_psi": round(max(0.0, (boost_tgt - 1013.25) * 0.0145038), 2),
                "boost_actual_psi": round(max(0.0, (boost_act - 1013.25) * 0.0145038), 2),
                "ignition_timing": timing_cyls,
                "knock_retard": knock_cyls,
                "wgdc": round(wgdc, 1),
                "coolant_c": round(coolant, 1),
                "oil_c": round(oil, 1),
                "egt_c": round(egt, 1),
                "ethanol_pct": 10.0,
                "hpfp_bar": round(hpfp, 1),
                "lpfp_bar": 6.8
            }

    def process_uds_request(self, request: UDSMessage) -> UDSMessage:
        """Processes incoming UDS request through state machine."""
        with self._lock:
            # Check fault injection
            if self.simulated_fault_injection == "NRC_78":
                self.simulated_fault_injection = None
                return UDSNegativeResponse(request.sid, UDSNRC.REQUEST_CORRECTLY_RECEIVED_RESPONSE_PENDING)
            elif self.simulated_fault_injection == "NRC_33":
                return UDSNegativeResponse(request.sid, UDSNRC.SECURITY_ACCESS_DENIED)
            elif self.simulated_fault_injection == "NRC_22":
                return UDSNegativeResponse(request.sid, UDSNRC.CONDITIONS_NOT_CORRECT)

            sid = request.sid

            # 1. DiagnosticSessionControl (0x10)
            if sid == UDSService.DIAGNOSTIC_SESSION_CONTROL:
                if len(request.data) < 1:
                    return UDSNegativeResponse(sid, UDSNRC.INCORRECT_MESSAGE_LENGTH)
                stype = request.data[0]
                if stype in [s.value for s in DiagnosticSessionType]:
                    self.active_session = DiagnosticSessionType(stype)
                    return DiagnosticSessionControl.build_response(self.active_session, 50, 5000)
                return UDSNegativeResponse(sid, UDSNRC.SUB_FUNCTION_NOT_SUPPORTED)

            # 2. ECUReset (0x11)
            elif sid == UDSService.ECU_RESET:
                self.active_session = DiagnosticSessionType.DEFAULT
                self.security_level_unlocked = 0
                self.download_in_progress = False
                return UDSPositiveResponse(sid, b"\x01")

            # 3. SecurityAccess (0x27)
            elif sid == UDSService.SECURITY_ACCESS:
                if len(request.data) < 1:
                    return UDSNegativeResponse(sid, UDSNRC.INCORRECT_MESSAGE_LENGTH)
                sub_func = request.data[0]

                # Request Seed (Odd sub-functions: 0x01, 0x03, 0x05)
                if sub_func % 2 == 1:
                    seed = bytes([random.randint(0, 255) for _ in range(8)])
                    self.active_seed = seed
                    self.active_seed_level = sub_func
                    return SecurityAccess.build_seed_response(sub_func, seed)

                # Send Key (Even sub-functions: 0x02, 0x04, 0x06)
                else:
                    if self.active_seed is None:
                        return UDSNegativeResponse(sid, UDSNRC.REQUEST_SEQUENCE_ERROR)
                    provided_key = request.data[1:]

                    # Calculate expected key
                    if self.ecu_type == ECUType.BOSCH_MEVD17:
                        expected_key = BoschMEVD17Crypto.calculate_key(self.active_seed, self.active_seed_level)
                    elif self.ecu_type == ECUType.SIEMENS_MSD80:
                        expected_key = SiemensMSD80Crypto.calculate_key(self.active_seed, self.active_seed_level)
                    else: # MG1
                        expected_key = BoschMG1Crypto.calculate_key(self.active_seed, self.active_seed_level)

                    if provided_key == expected_key:
                        self.security_level_unlocked = self.active_seed_level
                        self.active_seed = None
                        return SecurityAccess.build_key_accepted_response(sub_func)
                    else:
                        return UDSNegativeResponse(sid, UDSNRC.INVALID_KEY)

            # 4. ReadDataByIdentifier (0x22)
            elif sid == UDSService.READ_DATA_BY_IDENTIFIER:
                if len(request.data) < 2:
                    return UDSNegativeResponse(sid, UDSNRC.INCORRECT_MESSAGE_LENGTH)
                did = struct.unpack("!H", request.data[:2])[0]

                snap = self.get_live_telemetry_snapshot()

                if did == BMWDataIdentifier.VIN_DATA:
                    payload = struct.pack("!H", did) + self.vin.encode("ascii").ljust(17, b"\x00")
                    return UDSPositiveResponse(sid, payload)
                elif did == BMWDataIdentifier.CALIBRATION_ID_CVN:
                    payload = struct.pack("!H", did) + self.sw_id.encode("ascii").ljust(16, b"\x00")
                    return UDSPositiveResponse(sid, payload)
                elif did == BMWDataIdentifier.ENGINE_RPM:
                    payload = struct.pack("!H", did) + TelematicsEncoderDecoder.encode_rpm(snap["rpm"])
                    return UDSPositiveResponse(sid, payload)
                elif did == BMWDataIdentifier.VEHICLE_SPEED:
                    payload = struct.pack("!H", did) + TelematicsEncoderDecoder.encode_speed(snap["speed"])
                    return UDSPositiveResponse(sid, payload)
                elif did == BMWDataIdentifier.AFR_LAMBDA:
                    payload = struct.pack("!H", did) + TelematicsEncoderDecoder.encode_afr_lambda(snap["lambda_actual"], snap["lambda_target"])
                    return UDSPositiveResponse(sid, payload)
                elif did == BMWDataIdentifier.ACTUAL_BOOST_MAP:
                    payload = struct.pack("!H", did) + TelematicsEncoderDecoder.encode_boost(snap["boost_target_hpa"], snap["boost_actual_hpa"])
                    return UDSPositiveResponse(sid, payload)
                elif did == BMWDataIdentifier.IGNITION_TIMING_CYL1_6:
                    payload = struct.pack("!H", did) + TelematicsEncoderDecoder.encode_ignition_timing(snap["ignition_timing"])
                    return UDSPositiveResponse(sid, payload)
                elif did == BMWDataIdentifier.KNOCK_RETARD_CYL1_6:
                    payload = struct.pack("!H", did) + TelematicsEncoderDecoder.encode_knock_retard(snap["knock_retard"])
                    return UDSPositiveResponse(sid, payload)
                elif did == BMWDataIdentifier.WASTEGATE_DUTY_CYCLE:
                    payload = struct.pack("!H", did) + TelematicsEncoderDecoder.encode_wgdc(snap["wgdc"])
                    return UDSPositiveResponse(sid, payload)
                elif did == BMWDataIdentifier.COOLANT_TEMPERATURE:
                    payload = struct.pack("!H", did) + TelematicsEncoderDecoder.encode_temperatures(snap["coolant_c"], snap["oil_c"], snap["egt_c"])
                    return UDSPositiveResponse(sid, payload)
                else:
                    # Return full telemetry snapshot
                    payload = struct.pack("!H", did) + TelematicsEncoderDecoder.encode_telemetry_snapshot(snap)
                    return UDSPositiveResponse(sid, payload)

            # 5. RoutineControl (0x31)
            elif sid == UDSService.ROUTINE_CONTROL:
                if len(request.data) < 3:
                    return UDSNegativeResponse(sid, UDSNRC.INCORRECT_MESSAGE_LENGTH)
                ctype, r_id = struct.unpack("!BH", request.data[:3])

                if r_id == BMWKnownRoutines.CHECK_PREPROGRAMMING_DEPENDENCIES:
                    return RoutineControl.build_response(RoutineControlType(ctype), r_id, b"\x00")
                elif r_id == BMWKnownRoutines.CHECK_PROGRAMMING_DEPENDENCIES:
                    return RoutineControl.build_response(RoutineControlType(ctype), r_id, b"\x00")
                elif r_id == BMWKnownRoutines.ERASE_FLASH_MEMORY:
                    if self.active_session != DiagnosticSessionType.PROGRAMMING:
                        return UDSNegativeResponse(sid, UDSNRC.CONDITIONS_NOT_CORRECT)
                    if self.security_level_unlocked < 3:
                        return UDSNegativeResponse(sid, UDSNRC.SECURITY_ACCESS_DENIED)
                    self.flash_erased = True
                    self.received_flash_buffer.clear()
                    return RoutineControl.build_response(RoutineControlType(ctype), r_id, b"\x00")
                elif r_id == BMWKnownRoutines.VERIFY_MEMORY_CHECKSUM:
                    if self.simulated_fault_injection == "FAIL_CRC":
                        return UDSNegativeResponse(sid, UDSNRC.GENERAL_PROGRAMMING_FAILURE)
                    # Verify received buffer
                    if len(self.received_flash_buffer) == 0:
                        return UDSNegativeResponse(sid, UDSNRC.CONDITIONS_NOT_CORRECT)
                    self.flash_successful = True
                    return RoutineControl.build_response(RoutineControlType(ctype), r_id, b"\x00")
                elif r_id == BMWKnownRoutines.FORCE_BOOTLOADER_RECOVERY:
                    self.active_session = DiagnosticSessionType.PROGRAMMING
                    self.flash_erased = True
                    self.received_flash_buffer.clear()
                    return RoutineControl.build_response(RoutineControlType(ctype), r_id, b"\x00")
                else:
                    return RoutineControl.build_response(RoutineControlType(ctype), r_id, b"\x00")

            # 6. RequestDownload (0x34)
            elif sid == UDSService.REQUEST_DOWNLOAD:
                if self.active_session != DiagnosticSessionType.PROGRAMMING:
                    return UDSNegativeResponse(sid, UDSNRC.CONDITIONS_NOT_CORRECT)
                if self.security_level_unlocked < 3:
                    return UDSNegativeResponse(sid, UDSNRC.SECURITY_ACCESS_DENIED)
                self.download_in_progress = True
                self.expected_block_seq = 1
                self.received_flash_buffer.clear()
                return RequestDownload.build_response(2048)

            # 7. TransferData (0x36)
            elif sid == UDSService.TRANSFER_DATA:
                if not self.download_in_progress:
                    return UDSNegativeResponse(sid, UDSNRC.REQUEST_SEQUENCE_ERROR)
                if len(request.data) < 1:
                    return UDSNegativeResponse(sid, UDSNRC.INCORRECT_MESSAGE_LENGTH)
                seq = request.data[0]
                if seq != (self.expected_block_seq & 0xFF):
                    return UDSNegativeResponse(sid, UDSNRC.WRONG_BLOCK_SEQUENCE_COUNTER)
                chunk = request.data[1:]
                self.received_flash_buffer.extend(chunk)
                self.expected_block_seq = (self.expected_block_seq % 255) + 1
                return TransferData.build_response(seq)

            # 8. RequestTransferExit (0x37)
            elif sid == UDSService.REQUEST_TRANSFER_EXIT:
                if not self.download_in_progress:
                    return UDSNegativeResponse(sid, UDSNRC.REQUEST_SEQUENCE_ERROR)
                self.download_in_progress = False
                return RequestTransferExit.build_response()

            # 9. TesterPresent (0x3E)
            elif sid == UDSService.TESTER_PRESENT:
                return UDSPositiveResponse(sid, b"\x00")

            # 10. ControlDTCSetting (0x85)
            elif sid == UDSService.CONTROL_DTC_SETTING:
                return UDSPositiveResponse(sid, request.data)

            # 11. CommunicationControl (0x28)
            elif sid == UDSService.COMMUNICATION_CONTROL:
                return UDSPositiveResponse(sid, request.data[:1])

            else:
                return UDSNegativeResponse(sid, UDSNRC.SERVICE_NOT_SUPPORTED)


class DoIPSimulatorServer:
    """
    Simulated ISO 13400-2 Server listening on TCP/UDP sockets.
    Provides complete DoIP diagnostic gateway emulation for tests and live hardware bridge.
    """
    def __init__(
        self,
        host: str = "127.0.0.1",
        tcp_port: int = 13400,
        udp_port: int = 13400,
        ecu: Optional[SimulatedECU] = None
    ) -> None:
        self.host = host
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.ecu = ecu or SimulatedECU()
        self.running = False
        self._tcp_thread: Optional[threading.Thread] = None
        self._udp_thread: Optional[threading.Thread] = None
        self._tcp_socket: Optional[socket.socket] = None
        self._udp_socket: Optional[socket.socket] = None

    def start(self) -> None:
        self.running = True
        # Find open ports if 13400 is busy
        self._bind_sockets()
        self._tcp_thread = threading.Thread(target=self._run_tcp, daemon=True)
        self._udp_thread = threading.Thread(target=self._run_udp, daemon=True)
        self._tcp_thread.start()
        self._udp_thread.start()
        logger.info(f"DoIP Simulator Server started on TCP {self.host}:{self.tcp_port}, UDP {self.host}:{self.udp_port}")

    def stop(self) -> None:
        self.running = False
        if self._tcp_socket:
            try:
                self._tcp_socket.close()
            except Exception:
                pass
        if self._udp_socket:
            try:
                self._udp_socket.close()
            except Exception:
                pass

    def _bind_sockets(self) -> None:
        # Bind TCP
        s_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s_tcp.bind((self.host, self.tcp_port))
        except OSError:
            # Pick ephemeral port if default is occupied
            s_tcp.bind((self.host, 0))
            self.tcp_port = s_tcp.getsockname()[1]
        s_tcp.listen(5)
        self._tcp_socket = s_tcp

        # Bind UDP
        s_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s_udp.bind((self.host, self.udp_port))
        except OSError:
            s_udp.bind((self.host, 0))
            self.udp_port = s_udp.getsockname()[1]
        self._udp_socket = s_udp

    def _run_udp(self) -> None:
        assert self._udp_socket is not None
        self._udp_socket.settimeout(1.0)
        while self.running:
            try:
                data, addr = self._udp_socket.recvfrom(4096)
                if len(data) >= 8:
                    msg = DoIPMessage.unpack(data)
                    if msg.header.payload_type == DoIPPayloadType.VEHICLE_IDENT_REQ:
                        announcement = VehicleAnnouncementMessage(
                            vin=self.ecu.vin,
                            logical_address=self.ecu.logical_address,
                            eid=b"\x00\x1C\x69\xAA\xBB\xCC",
                            gid=b"\x00\x00\x00\x00\x00\x01"
                        )
                        self._udp_socket.sendto(announcement.pack(), addr)
            except socket.timeout:
                continue
            except Exception:
                if not self.running:
                    break

    def _run_tcp(self) -> None:
        assert self._tcp_socket is not None
        self._tcp_socket.settimeout(1.0)
        while self.running:
            try:
                conn, addr = self._tcp_socket.accept()
                client_thread = threading.Thread(target=self._handle_tcp_client, args=(conn,), daemon=True)
                client_thread.start()
            except socket.timeout:
                continue
            except Exception:
                if not self.running:
                    break

    def _handle_tcp_client(self, conn: socket.socket) -> None:
        conn.settimeout(5.0)
        buffer = bytearray()
        try:
            while self.running:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buffer.extend(chunk)

                while len(buffer) >= 8:
                    hdr = DoIPHeader.unpack(bytes(buffer[:8]))
                    total_len = 8 + hdr.payload_length
                    if len(buffer) < total_len:
                        break

                    msg_bytes = bytes(buffer[:total_len])
                    buffer = buffer[total_len:]

                    msg = DoIPMessage.unpack(msg_bytes)
                    rsp = self._process_doip_tcp_message(msg)
                    if rsp:
                        conn.sendall(rsp.pack())
        except Exception:
            pass
        finally:
            conn.close()

    def _process_doip_tcp_message(self, msg: DoIPMessage) -> Optional[DoIPMessage]:
        ptype = msg.header.payload_type

        # Routing Activation Request (0x0005)
        if ptype == DoIPPayloadType.ROUTING_ACTIVATION_REQ:
            info = RoutingActivationRequest.parse_payload(msg.payload)
            tester_addr = info["source_address"]
            return RoutingActivationResponse(
                tester_address=tester_addr,
                entity_address=self.ecu.logical_address,
                response_code=RoutingActivationCode.SUCCESSFULLY_ROUTED
            )

        # Alive Check Request (0x0007)
        elif ptype == DoIPPayloadType.ALIVE_CHECK_REQ:
            return DoIPMessage(DoIPPayloadType.ALIVE_CHECK_RESP, struct.pack("!H", self.ecu.logical_address))

        # Diagnostic Message (0x8001)
        elif ptype == DoIPPayloadType.DIAGNOSTIC_MESSAGE:
            diag_req = DiagnosticMessage.from_payload(msg.payload)
            uds_req = UDSMessage.unpack(diag_req.user_data)
            uds_rsp = self.ecu.process_uds_request(uds_req)

            # Build Diagnostic Message Positive Ack + Response
            diag_rsp = DiagnosticMessage(
                source_address=self.ecu.logical_address,
                target_address=diag_req.source_address,
                user_data=uds_rsp.pack()
            )
            return diag_rsp

        return None
