"""
Test Suite for ECU Flashing Pipeline, Safeguards, and Automatic Rollback Engine.
Tests full flash sequence and fail-safe recovery on simulated faults.
"""

import pytest
import os
import shutil
import tempfile
from ang_telematics.flashing.ecu_flasher import ECUFlasher, FlashingState, FlashingError
from ang_telematics.flashing.rom_manager import ECURomPackage, ECUType
from ang_telematics.hardware_bridge.ecu_simulator import SimulatedECU
from ang_telematics.protocols.uds import UDSMessage

@pytest.fixture
def clean_backup_dir():
    dir_path = os.path.join(tempfile.gettempdir(), "ang_test_flasher_backups")
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
    os.makedirs(dir_path, exist_ok=True)
    yield dir_path
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)

def test_successful_ecu_flash_pipeline(clean_backup_dir):
    # Setup Simulated ECU
    sim_ecu = SimulatedECU(ecu_type=ECUType.BOSCH_MEVD17, vin="WBA3R9C50K5A12345", sw_id="00001E8B001")

    # Connect transport function directly to simulated ECU
    def transport_send(msg: UDSMessage) -> UDSMessage:
        return sim_ecu.process_uds_request(msg)

    flasher = ECUFlasher(
        transport_send_fn=transport_send,
        ecu_type=ECUType.BOSCH_MEVD17,
        backup_dir=clean_backup_dir
    )

    # Target Stage 2 ROM package
    target_rom = ECURomPackage(ecu_type=ECUType.BOSCH_MEVD17, software_id="00001E8B001", vin="WBA3R9C50K5A12345")
    target_rom.apply_stage("STAGE_2")

    # Execute Flash
    success = flasher.flash_ecu(target_rom, battery_voltage=13.5)

    assert success is True
    assert flasher.current_state == FlashingState.COMPLETED
    assert flasher.flash_progress_pct == 100.0
    assert sim_ecu.flash_successful is True

    # Check that backup file was created
    assert flasher.last_backup_path is not None
    assert os.path.exists(flasher.last_backup_path)
    assert os.path.getsize(flasher.last_backup_path) > 500

def test_flashing_low_voltage_abort(clean_backup_dir):
    sim_ecu = SimulatedECU()
    flasher = ECUFlasher(lambda m: sim_ecu.process_uds_request(m), backup_dir=clean_backup_dir)
    target_rom = ECURomPackage()

    # Low battery voltage (11.4V < 12.0V)
    with pytest.raises(FlashingError, match="Battery voltage too low"):
        flasher.flash_ecu(target_rom, battery_voltage=11.4)

def test_automatic_rollback_on_flash_erase_fault(clean_backup_dir):
    sim_ecu = SimulatedECU(ecu_type=ECUType.BOSCH_MEVD17)
    flasher = ECUFlasher(lambda m: sim_ecu.process_uds_request(m), backup_dir=clean_backup_dir)
    target_rom = ECURomPackage()

    # Simulate fault injection at ERASE_FLASH step
    with pytest.raises(FlashingError):
        flasher.flash_ecu(target_rom, battery_voltage=13.8, simulate_fault_at_step="ERASE_FLASH")

    # Verify rollback was executed and logged
    log_text = " ".join(flasher.flashing_log)
    assert "ENGAGING FAIL-SAFE AUTOMATIC ROLLBACK HANDLER" in log_text
    assert "EMERGENCY ROLLBACK SUCCESSFUL" in log_text
    assert flasher.current_state == FlashingState.FAILED

def test_automatic_rollback_on_transfer_fault(clean_backup_dir):
    sim_ecu = SimulatedECU(ecu_type=ECUType.BOSCH_MEVD17)
    flasher = ECUFlasher(lambda m: sim_ecu.process_uds_request(m), backup_dir=clean_backup_dir)
    target_rom = ECURomPackage()

    # Simulate fault injection during block streaming
    with pytest.raises(FlashingError):
        flasher.flash_ecu(target_rom, battery_voltage=13.8, simulate_fault_at_step="TRANSFER_DATA")

    log_text = " ".join(flasher.flashing_log)
    assert "ENGAGING FAIL-SAFE AUTOMATIC ROLLBACK HANDLER" in log_text
    assert "EMERGENCY ROLLBACK SUCCESSFUL" in log_text
