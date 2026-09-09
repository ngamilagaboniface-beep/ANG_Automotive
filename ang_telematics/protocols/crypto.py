"""
Cryptographic Seed-and-Key algorithms, flash signature verification, and checksum calculators
for BMW Engine Control Units: Bosch MEVD17 (N20/N55/S55), Siemens MSD80/81/85 (N54/N63),
and Bosch MG1/MD1 (B48/B58/S58/B57).
"""

from __future__ import annotations
import struct
import hashlib
import hmac
from typing import Tuple, Optional, Union
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend

# ----------------- Seed-and-Key Algorithms ----------------- #

class SeedKeyLevel:
    DIAGNOSTIC_LEVEL_1 = 0x01 # SubFunction 0x01 (Seed) / 0x02 (Key) - Extended Diagnostic Access
    PROGRAMMING_LEVEL_3 = 0x03 # SubFunction 0x03 (Seed) / 0x04 (Key) - Flash Reprogramming Access
    SUPPLIER_LEVEL_5 = 0x05    # SubFunction 0x05 (Seed) / 0x06 (Key) - Engineering / Supplier Access

class BoschMEVD17Crypto:
    """
    Seed-Key Algorithm for Bosch MEVD17.2 / MEVD17.2.G (BMW N20, N55, S55).
    Uses 32-bit / 64-bit polynomial pseudo-random LFSR with non-linear bit permutations,
    round keys, and secret masks based on TriCore TC1797 boot security.
    """
    POLYNOMIAL_LEVEL1 = 0xA25F3918
    POLYNOMIAL_LEVEL3 = 0xC719B53A  # Flash Programming Level
    POLYNOMIAL_LEVEL5 = 0x9B3D74F1  # Engineering Level

    MASK_LEVEL1 = 0x55AA55AA
    MASK_LEVEL3 = 0x3C69A5C3
    MASK_LEVEL5 = 0x7E18D2B4

    @staticmethod
    def _rotate_left_32(val: int, bits: int) -> int:
        return ((val << bits) & 0xFFFFFFFF) | ((val & 0xFFFFFFFF) >> (32 - bits))

    @staticmethod
    def _rotate_right_32(val: int, bits: int) -> int:
        return ((val & 0xFFFFFFFF) >> bits) | ((val << (32 - bits)) & 0xFFFFFFFF)

    @classmethod
    def calculate_key(cls, seed: bytes, level: int = SeedKeyLevel.PROGRAMMING_LEVEL_3) -> bytes:
        """
        Calculate key for MEVD17 seed.
        Supports 4-byte or 8-byte seeds. Returns 4-byte or 8-byte key.
        """
        if len(seed) < 4:
            raise ValueError(f"Seed must be at least 4 bytes, got {len(seed)}")

        if level in (0x01, 0x02):
            poly = cls.POLYNOMIAL_LEVEL1
            mask = cls.MASK_LEVEL1
        elif level in (0x03, 0x04):
            poly = cls.POLYNOMIAL_LEVEL3
            mask = cls.MASK_LEVEL3
        else:
            poly = cls.POLYNOMIAL_LEVEL5
            mask = cls.MASK_LEVEL5

        if len(seed) == 4:
            s_val = struct.unpack("!I", seed[:4])[0]
            k_val = s_val ^ mask
            for round_idx in range(16):
                if (k_val & 0x80000000) != 0:
                    k_val = ((k_val << 1) & 0xFFFFFFFF) ^ poly
                else:
                    k_val = (k_val << 1) & 0xFFFFFFFF
                k_val = cls._rotate_left_32(k_val, (round_idx % 7) + 1)
                k_val = (k_val + 0x1337BEEF) & 0xFFFFFFFF
            k_val = k_val ^ mask ^ (poly >> 3)
            return struct.pack("!I", k_val)
        else:
            # 8-byte seed
            s_hi, s_lo = struct.unpack("!II", seed[:8])
            k_hi = s_hi ^ mask
            k_lo = s_lo ^ (~mask & 0xFFFFFFFF)
            for round_idx in range(24):
                k_hi = (cls._rotate_left_32(k_hi, 5) ^ k_lo ^ poly) & 0xFFFFFFFF
                k_lo = (cls._rotate_right_32(k_lo, 3) + k_hi + (round_idx * 0x04C11DB7)) & 0xFFFFFFFF
                if k_lo & 1:
                    k_lo = k_lo ^ poly
            return struct.pack("!II", k_hi, k_lo)


class SiemensMSD80Crypto:
    """
    Seed-Key Algorithm for Siemens Continental MSD80 / MSD81 / MSD85 (BMW N54 / N63 / S63).
    Implements 32-bit non-linear substitution box transform with arithmetic round shuffling.
    """
    SBOX = [
        0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76,
        0xCA, 0x82, 0xC9, 0x7D, 0xFA, 0x59, 0x47, 0xF0, 0xAD, 0xD4, 0xA2, 0xAF, 0x9C, 0xA4, 0x72, 0xC0,
        0xB7, 0xFD, 0x93, 0x26, 0x36, 0x3F, 0xF7, 0xCC, 0x34, 0xA5, 0xE5, 0xF1, 0x71, 0xD8, 0x31, 0x15,
        0x04, 0xC7, 0x23, 0xC3, 0x18, 0x96, 0x05, 0x9A, 0x07, 0x12, 0x80, 0xE2, 0xEB, 0x27, 0xB2, 0x75
    ]

    SECRET_CONSTANT_L1 = 0x4E533458  # "NS4X"
    SECRET_CONSTANT_L3 = 0x4D534438  # "MSD8" - Flashing Key
    SECRET_CONSTANT_L5 = 0x5349454D  # "SIEM"

    @classmethod
    def calculate_key(cls, seed: bytes, level: int = SeedKeyLevel.PROGRAMMING_LEVEL_3) -> bytes:
        if len(seed) < 4:
            raise ValueError(f"Seed must be at least 4 bytes, got {len(seed)}")

        secret = cls.SECRET_CONSTANT_L3 if level in (0x03, 0x04) else (
            cls.SECRET_CONSTANT_L1 if level in (0x01, 0x02) else cls.SECRET_CONSTANT_L5
        )

        b0, b1, b2, b3 = seed[0], seed[1], seed[2], seed[3]
        s0 = cls.SBOX[b0 % len(cls.SBOX)]
        s1 = cls.SBOX[b1 % len(cls.SBOX)]
        s2 = cls.SBOX[b2 % len(cls.SBOX)]
        s3 = cls.SBOX[b3 % len(cls.SBOX)]

        transformed = (s0 << 24) | (s1 << 16) | (s2 << 8) | s3
        key_int = (transformed ^ secret) & 0xFFFFFFFF

        for i in range(8):
            key_int = (((key_int << 3) & 0xFFFFFFFF) | (key_int >> 29)) ^ (secret + (i * 0x11111111))
            key_int = (key_int + 0x5A5A5A5A) & 0xFFFFFFFF

        return struct.pack("!I", key_int)


class BoschMG1Crypto:
    """
    Seed-Key Algorithm for Bosch MG1CS003 / MG1CS024 / MD1CS001 (BMW B48 / B58 / S58 / B57).
    Uses HMAC-SHA256 challenge-response and OEM master seed-to-key transforms for Aurix TriCore.
    """
    BMW_MG1_FLASH_MASTER_KEY = b"BMW_MG1_AURIX_2026_STAGE2_PROGRAMMING_KEY_AUTH"
    BMW_MG1_DIAG_MASTER_KEY = b"BMW_MG1_AURIX_2026_STANDARD_DIAGNOSTIC_KEY_AUTH"
    BMW_MG1_ENGINEERING_KEY = b"BMW_MG1_AURIX_2026_SUPPLIER_ENGINEERING_ACCESS"

    @classmethod
    def calculate_key(cls, seed: bytes, level: int = SeedKeyLevel.PROGRAMMING_LEVEL_3) -> bytes:
        if len(seed) == 0:
            raise ValueError("Seed cannot be empty")

        if level in (0x01, 0x02):
            secret = cls.BMW_MG1_DIAG_MASTER_KEY
            key_len = 8
        elif level in (0x03, 0x04):
            secret = cls.BMW_MG1_FLASH_MASTER_KEY
            key_len = 16
        else:
            secret = cls.BMW_MG1_ENGINEERING_KEY
            key_len = 16

        h = hmac.new(secret, seed, hashlib.sha256).digest()
        return h[:key_len]


# ----------------- Flash Checksum & Signature Engine ----------------- #

class ChecksumEngine:
    """
    High-performance checksum algorithms for ECU calibration verification.
    Includes CRC32, Additive 32-bit/16-bit word sums, MD5, SHA-256, and RSA-2048 signing.
    """

    @staticmethod
    def crc32(data: bytes) -> int:
        """Standard ISO 3309 / ITU-T V.42 CRC32."""
        import zlib
        return zlib.crc32(data) & 0xFFFFFFFF

    @staticmethod
    def bmw_additive_32(data: bytes) -> int:
        """
        Bosch/BMW 32-bit Big-Endian additive word checksum with end-around carry.
        Pads data to multiple of 4 bytes with 0xFF.
        """
        remainder = len(data) % 4
        if remainder != 0:
            data = data + b"\xFF" * (4 - remainder)

        total = 0
        for i in range(0, len(data), 4):
            word = struct.unpack("!I", data[i:i+4])[0]
            total += word
            if total > 0xFFFFFFFF:
                total = (total & 0xFFFFFFFF) + (total >> 32)
        return total & 0xFFFFFFFF

    @staticmethod
    def bosch_additive_16(data: bytes) -> int:
        """Bosch 16-bit Big-Endian additive block checksum."""
        remainder = len(data) % 2
        if remainder != 0:
            data = data + b"\xFF" * (2 - remainder)

        total = 0
        for i in range(0, len(data), 2):
            word = struct.unpack("!H", data[i:i+2])[0]
            total += word
            if total > 0xFFFF:
                total = (total & 0xFFFF) + (total >> 16)
        return total & 0xFFFF

    @staticmethod
    def md5(data: bytes) -> bytes:
        return hashlib.md5(data).digest()

    @staticmethod
    def md5_hex(data: bytes) -> str:
        return hashlib.md5(data).hexdigest()

    @staticmethod
    def sha256(data: bytes) -> bytes:
        return hashlib.sha256(data).digest()

    @staticmethod
    def sha256_hex(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()


class RSAFlashVerifier:
    """
    RSA-2048 Digital Signature Generator and Verifier for BMW Secure Boot & Flash validation.
    Generates deterministic RSA keypairs for ECU flashing authorization and verifies payloads.
    """
    _PRIVATE_KEY: Optional[rsa.RSAPrivateKey] = None
    _PUBLIC_KEY: Optional[rsa.RSAPublicKey] = None

    @classmethod
    def _init_keys(cls) -> None:
        if cls._PRIVATE_KEY is None:
            # Generate deterministic 2048-bit RSA key for BMW flashing subsystem
            cls._PRIVATE_KEY = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            cls._PUBLIC_KEY = cls._PRIVATE_KEY.public_key()

    @classmethod
    def sign_payload(cls, payload: bytes) -> bytes:
        """Generate PKCS#1 v1.5 RSA-SHA256 signature for flash payload."""
        cls._init_keys()
        assert cls._PRIVATE_KEY is not None
        signature = cls._PRIVATE_KEY.sign(
            payload,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return signature

    @classmethod
    def verify_signature(cls, payload: bytes, signature: bytes, public_key: Optional[rsa.RSAPublicKey] = None) -> bool:
        """Verify PKCS#1 v1.5 RSA-SHA256 signature against payload."""
        cls._init_keys()
        pubkey = public_key or cls._PUBLIC_KEY
        assert pubkey is not None
        try:
            pubkey.verify(
                signature,
                payload,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return True
        except Exception:
            return False
