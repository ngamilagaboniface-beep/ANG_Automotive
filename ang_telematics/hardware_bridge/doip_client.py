"""
High-Performance DoIP / UDS Diagnostic Client.
Connects to BMW ENET / ICOM / DoIP hardware bridges over TCP/UDP sockets.
"""

from __future__ import annotations
import socket
import struct
import time
import logging
from typing import Optional, Dict, Any, List
from ang_telematics.protocols.doip import (
    DoIPMessage, DoIPPayloadType, DoIPHeader,
    BMWLogicalAddress, RoutingActivationCode,
    VehicleIdentificationRequest, VehicleAnnouncementMessage,
    RoutingActivationRequest, RoutingActivationResponse, DiagnosticMessage
)
from ang_telematics.protocols.uds import UDSMessage, UDSNegativeResponse, UDSNRC

logger = logging.getLogger(__name__)

class DoIPClient:
    """
    ISO 13400 DoIP Diagnostic Client.
    Manages UDP discovery and persistent TCP diagnostic sessions.
    """
    def __init__(
        self,
        tester_address: int = BMWLogicalAddress.TESTER_FLASH,
        target_address: int = BMWLogicalAddress.DME_MASTER,
        timeout: float = 3.0
    ) -> None:
        self.tester_address = tester_address
        self.target_address = target_address
        self.timeout = timeout
        self.tcp_socket: Optional[socket.socket] = None
        self.is_connected = False
        self.vehicle_info: Optional[Dict[str, Any]] = None

    def discover_vehicle(self, broadcast_ip: str = "255.255.255.255", udp_port: int = 13400, timeout: float = 1.5) -> Optional[Dict[str, Any]]:
        """Sends UDP broadcast to discover DoIP entities on network."""
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_sock.settimeout(timeout)

        req = VehicleIdentificationRequest()
        try:
            udp_sock.sendto(req.pack(), (broadcast_ip, udp_port))
            data, addr = udp_sock.recvfrom(4096)
            if len(data) >= 8:
                msg = DoIPMessage.unpack(data)
                if msg.header.payload_type == DoIPPayloadType.VEHICLE_ANNOUNCEMENT:
                    parsed = VehicleAnnouncementMessage.parse_payload(msg.payload)
                    parsed["ip_address"] = addr[0]
                    self.vehicle_info = parsed
                    return parsed
        except (socket.timeout, OSError):
            pass
        finally:
            udp_sock.close()
        return None

    def connect(self, host: str, port: int = 13400) -> bool:
        """Establishes TCP connection and activates routing."""
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.settimeout(self.timeout)
        self.tcp_socket.connect((host, port))

        # Send Routing Activation Request (0x0005)
        req = RoutingActivationRequest(source_address=self.tester_address)
        self.tcp_socket.sendall(req.pack())

        # Receive Routing Activation Response (0x0006)
        hdr_bytes = self._recv_exact(8)
        hdr = DoIPHeader.unpack(hdr_bytes)
        payload = self._recv_exact(hdr.payload_length)

        if hdr.payload_type == DoIPPayloadType.ROUTING_ACTIVATION_RESP:
            resp = RoutingActivationResponse.parse_payload(payload)
            if resp["response_code"] == RoutingActivationCode.SUCCESSFULLY_ROUTED:
                self.is_connected = True
                logger.info(f"DoIP Routing successfully activated on {host}:{port}")
                return True
            else:
                logger.error(f"DoIP Routing activation failed with code: {resp['response_code']}")
                return False
        return False

    def send_uds(self, uds_req: UDSMessage) -> UDSMessage:
        """Sends UDS request inside DoIP Diagnostic Message (0x8001) and returns UDS response."""
        if not self.is_connected or not self.tcp_socket:
            raise ConnectionError("DoIP client is not connected to gateway")

        # Encapsulate in DoIP Diagnostic Message
        diag_msg = DiagnosticMessage(
            source_address=self.tester_address,
            target_address=self.target_address,
            user_data=uds_req.pack()
        )
        self.tcp_socket.sendall(diag_msg.pack())

        # Read response loop
        while True:
            hdr_bytes = self._recv_exact(8)
            hdr = DoIPHeader.unpack(hdr_bytes)
            payload = self._recv_exact(hdr.payload_length)

            if hdr.payload_type == DoIPPayloadType.DIAGNOSTIC_MESSAGE_ACK:
                # Positive ACK received, continue reading actual Diagnostic Message
                continue
            elif hdr.payload_type == DoIPPayloadType.DIAGNOSTIC_MESSAGE_NACK:
                raise ConnectionError(f"DoIP Gateway NACK received: code {payload[4] if len(payload)>4 else 'unknown'}")
            elif hdr.payload_type == DoIPPayloadType.DIAGNOSTIC_MESSAGE:
                diag_rsp = DiagnosticMessage.from_payload(payload)
                uds_rsp = UDSMessage.unpack(diag_rsp.user_data)
                return uds_rsp
            else:
                logger.debug(f"Received non-diagnostic DoIP frame: {hdr.payload_type}")

    def close(self) -> None:
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except Exception:
                pass
            self.tcp_socket = None
        self.is_connected = False

    def _recv_exact(self, length: int) -> bytes:
        assert self.tcp_socket is not None
        buf = bytearray()
        while len(buf) < length:
            chunk = self.tcp_socket.recv(length - len(buf))
            if not chunk:
                raise ConnectionResetError("DoIP TCP connection closed unexpectedly")
            buf.extend(chunk)
        return bytes(buf)
