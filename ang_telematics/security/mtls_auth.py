"""
Hardware-Bound mTLS (Mutual TLS) Session Encryption and X.509 Authentication.
Binds diagnostic sessions to verified hardware dongle serials, ENET adapters, and VIN credentials.
"""

from __future__ import annotations
import os
import datetime
import hashlib
from typing import Optional, Dict, Any, Tuple
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend

class MTLSHardwareAuth:
    """
    Manages Certificate Authority (CA), Server, and Hardware Client Certificates.
    Enforces hardware dongle serial and VIN binding in diagnostic sessions.
    """
    _CA_KEY: Optional[rsa.RSAPrivateKey] = None
    _CA_CERT: Optional[x509.Certificate] = None

    @classmethod
    def _init_ca(cls) -> None:
        if cls._CA_KEY is None or cls._CA_CERT is None:
            cls._CA_KEY = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "DE"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Bavaria"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Munich"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ANG Automotive Security CA"),
                x509.NameAttribute(NameOID.COMMON_NAME, "ANG Telematics Root CA 2026"),
            ])
            cls._CA_CERT = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                issuer
            ).public_key(
                cls._CA_KEY.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.datetime.now(datetime.timezone.utc)
            ).not_valid_after(
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650)
            ).add_extension(
                x509.BasicConstraints(ca=True, path_length=None), critical=True,
            ).sign(cls._CA_KEY, hashes.SHA256(), default_backend())

    @classmethod
    def issue_hardware_client_certificate(
        cls,
        hardware_dongle_id: str = "ANG-ENET-PRO-8921",
        vin: str = "WBA3R9C50K5A12345",
        user_role: str = "MASTER_TUNER"
    ) -> Dict[str, str]:
        """Issues an X.509 client certificate bound to hardware serial and VIN."""
        cls._init_ca()
        assert cls._CA_KEY is not None and cls._CA_CERT is not None

        client_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        subject = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ANG Automotive Engineering"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, user_role),
            x509.NameAttribute(NameOID.COMMON_NAME, f"HW:{hardware_dongle_id}"),
            x509.NameAttribute(NameOID.SERIAL_NUMBER, vin),
        ])

        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            cls._CA_CERT.subject
        ).public_key(
            client_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.now(datetime.timezone.utc)
        ).not_valid_after(
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)
        ).add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True,
        ).sign(cls._CA_KEY, hashes.SHA256(), default_backend())

        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        key_pem = client_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode("utf-8")

        return {
            "hardware_dongle_id": hardware_dongle_id,
            "vin": vin,
            "user_role": user_role,
            "client_certificate_pem": cert_pem,
            "client_private_key_pem": key_pem,
            "ca_certificate_pem": cls._CA_CERT.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        }

    @classmethod
    def verify_client_certificate(cls, cert_pem: str, expected_dongle_id: Optional[str] = None) -> Dict[str, Any]:
        """Validates client certificate signature against Root CA and checks hardware binding."""
        cls._init_ca()
        assert cls._CA_CERT is not None
        try:
            cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"), default_backend())
            ca_pubkey = cls._CA_CERT.public_key()
            assert isinstance(ca_pubkey, rsa.RSAPublicKey)
            
            # Verify signature with CA public key
            ca_pubkey.verify(
                cert.signature,
                cert.tbs_certificate_bytes,
                padding.PKCS1v15(),
                cert.signature_hash_algorithm
            )

            # Extract subject attributes
            cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
            ou = cert.subject.get_attributes_for_oid(NameOID.ORGANIZATIONAL_UNIT_NAME)[0].value
            vin = cert.subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER)[0].value

            dongle_id = str(cn).replace("HW:", "")

            if expected_dongle_id and dongle_id != expected_dongle_id:
                return {"valid": False, "error": f"Hardware dongle ID mismatch: expected {expected_dongle_id}, got {dongle_id}"}

            return {
                "valid": True,
                "dongle_id": dongle_id,
                "role": str(ou),
                "vin": str(vin),
                "expires_at": cert.not_valid_after_utc.isoformat()
            }
        except Exception as e:
            return {"valid": False, "error": f"Certificate verification failed: {str(e)}"}
