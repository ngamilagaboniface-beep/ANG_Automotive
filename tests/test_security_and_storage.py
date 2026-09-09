"""
Test Suite for mTLS Certificate Security, Hardware Binding, Encrypted Storage, and RBAC.
"""

import pytest
import os
import shutil
import tempfile
from ang_telematics.security.mtls_auth import MTLSHardwareAuth
from ang_telematics.security.encrypted_db import EncryptedStorageEngine
from ang_telematics.security.rbac import UserRole, Permission, has_permission

@pytest.fixture
def clean_db():
    db_file = os.path.join(tempfile.gettempdir(), "ang_test_encrypted.db")
    if os.path.exists(db_file):
        os.remove(db_file)
    yield db_file
    if os.path.exists(db_file):
        os.remove(db_file)

def test_mtls_client_certificate_issuance_and_verification():
    dongle_id = "ANG-ENET-PRO-9988"
    vin = "WBA3R9C50K5A12345"

    creds = MTLSHardwareAuth.issue_hardware_client_certificate(
        hardware_dongle_id=dongle_id,
        vin=vin,
        user_role="MASTER_TUNER"
    )

    assert "client_certificate_pem" in creds
    assert "client_private_key_pem" in creds

    # Verification with correct dongle ID
    res = MTLSHardwareAuth.verify_client_certificate(creds["client_certificate_pem"], expected_dongle_id=dongle_id)
    assert res["valid"] is True
    assert res["dongle_id"] == dongle_id
    assert res["vin"] == vin

    # Verification with wrong dongle ID must fail
    res_bad = MTLSHardwareAuth.verify_client_certificate(creds["client_certificate_pem"], expected_dongle_id="ANG-FAKE-DONGLE")
    assert res_bad["valid"] is False

def test_encrypted_storage_aes_gcm(clean_db):
    engine = EncryptedStorageEngine(db_path=clean_db)

    raw_bin = b"\xDE\xAD\xBE\xEF" * 1024 # 4KB binary
    rom_id = engine.store_rom(
        vin="WBA3R9C50K5A12345",
        ecu_type="BOSCH_MEVD17",
        stage_name="STAGE_2",
        cal_version="ANG_V3.4",
        rom_bytes=raw_bin
    )
    assert rom_id > 0

    # Read back and decrypt
    decrypted_bin = engine.load_rom(rom_id)
    assert decrypted_bin == raw_bin

    # List records
    roms = engine.list_roms()
    assert len(roms) == 1
    assert roms[0]["vin"] == "WBA3R9C50K5A12345"
    assert roms[0]["stage_name"] == "STAGE_2"

def test_rbac_permissions_matrix():
    # Master Tuner has all permissions
    assert has_permission("MASTER_TUNER", Permission.EXECUTE_ECU_FLASH) is True
    assert has_permission("MASTER_TUNER", Permission.ACCESS_SUPPLIER_SECURITY_L5) is True
    assert has_permission("MASTER_TUNER", Permission.EDIT_3D_ENGINE_MAPS) is True

    # Calibrator can edit maps and flash, but cannot access Supplier L5
    assert has_permission("CALIBRATOR", Permission.EDIT_3D_ENGINE_MAPS) is True
    assert has_permission("CALIBRATOR", Permission.ACCESS_SUPPLIER_SECURITY_L5) is False

    # Diagnostic Tech can view live telemetry and clear DTCs, but cannot flash ECU
    assert has_permission("DIAGNOSTIC_TECH", Permission.VIEW_LIVE_TELEMETRY) is True
    assert has_permission("DIAGNOSTIC_TECH", Permission.READ_CLEAR_DTC) is True
    assert has_permission("DIAGNOSTIC_TECH", Permission.EXECUTE_ECU_FLASH) is False

    # Vehicle Owner can view telemetry and switch preset stages, but cannot edit raw tables
    assert has_permission("VEHICLE_OWNER", Permission.SWITCH_STAGE_PRESETS) is True
    assert has_permission("VEHICLE_OWNER", Permission.EDIT_3D_ENGINE_MAPS) is False
