"""
Test Suite for Cryptographic Seed-and-Key algorithms, Checksum verification, and RSA Flash Signing.
"""

import pytest
import struct
from ang_telematics.protocols.crypto import (
    BoschMEVD17Crypto, SiemensMSD80Crypto, BoschMG1Crypto,
    ChecksumEngine, RSAFlashVerifier, SeedKeyLevel
)

def test_bosch_mevd17_seed_key():
    # 4-byte seed test
    seed4 = bytes([0x12, 0x34, 0x56, 0x78])
    key4_l1 = BoschMEVD17Crypto.calculate_key(seed4, SeedKeyLevel.DIAGNOSTIC_LEVEL_1)
    key4_l3 = BoschMEVD17Crypto.calculate_key(seed4, SeedKeyLevel.PROGRAMMING_LEVEL_3)
    key4_l5 = BoschMEVD17Crypto.calculate_key(seed4, SeedKeyLevel.SUPPLIER_LEVEL_5)

    assert len(key4_l1) == 4
    assert len(key4_l3) == 4
    assert len(key4_l5) == 4
    assert key4_l1 != key4_l3  # Different levels must produce distinct keys
    assert key4_l3 != key4_l5

    # Determinism check
    assert BoschMEVD17Crypto.calculate_key(seed4, SeedKeyLevel.PROGRAMMING_LEVEL_3) == key4_l3

    # 8-byte seed test
    seed8 = bytes([0xDE, 0xAD, 0xBE, 0xEF, 0xCA, 0xFE, 0xBA, 0xBE])
    key8_l3 = BoschMEVD17Crypto.calculate_key(seed8, SeedKeyLevel.PROGRAMMING_LEVEL_3)
    assert len(key8_l3) == 8

def test_siemens_msd80_seed_key():
    seed = bytes([0x45, 0x67, 0x89, 0xAB])
    key_l1 = SiemensMSD80Crypto.calculate_key(seed, SeedKeyLevel.DIAGNOSTIC_LEVEL_1)
    key_l3 = SiemensMSD80Crypto.calculate_key(seed, SeedKeyLevel.PROGRAMMING_LEVEL_3)

    assert len(key_l1) == 4
    assert len(key_l3) == 4
    assert key_l1 != key_l3
    # Determinism check
    assert SiemensMSD80Crypto.calculate_key(seed, SeedKeyLevel.PROGRAMMING_LEVEL_3) == key_l3

def test_bosch_mg1_seed_key():
    seed = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])
    key_l1 = BoschMG1Crypto.calculate_key(seed, SeedKeyLevel.DIAGNOSTIC_LEVEL_1)
    key_l3 = BoschMG1Crypto.calculate_key(seed, SeedKeyLevel.PROGRAMMING_LEVEL_3)

    assert len(key_l1) == 8
    assert len(key_l3) == 16
    assert BoschMG1Crypto.calculate_key(seed, SeedKeyLevel.PROGRAMMING_LEVEL_3) == key_l3

def test_checksum_algorithms():
    payload = b"ANG_BMW_ECU_CALIBRATION_TEST_DATA_STREAM_2026"

    # CRC32
    crc = ChecksumEngine.crc32(payload)
    assert isinstance(crc, int)
    assert crc > 0
    assert ChecksumEngine.crc32(payload) == crc

    # BMW Additive 32-bit
    add32 = ChecksumEngine.bmw_additive_32(payload)
    assert isinstance(add32, int)
    assert 0 <= add32 <= 0xFFFFFFFF

    # Bosch Additive 16-bit
    add16 = ChecksumEngine.bosch_additive_16(payload)
    assert isinstance(add16, int)
    assert 0 <= add16 <= 0xFFFF

    # MD5 & SHA256
    md5_d = ChecksumEngine.md5(payload)
    assert len(md5_d) == 16
    sha_d = ChecksumEngine.sha256(payload)
    assert len(sha_d) == 32

def test_rsa_flash_signature_verification():
    flash_bin = b"\x00\x11\x22\x33" * 256  # 1024 bytes binary
    signature = RSAFlashVerifier.sign_payload(flash_bin)
    assert len(signature) == 256  # RSA-2048 produces 256-byte signature

    # Valid signature
    assert RSAFlashVerifier.verify_signature(flash_bin, signature) is True

    # Tampered payload must fail
    tampered_bin = bytearray(flash_bin)
    tampered_bin[10] ^= 0xFF
    assert RSAFlashVerifier.verify_signature(bytes(tampered_bin), signature) is False
