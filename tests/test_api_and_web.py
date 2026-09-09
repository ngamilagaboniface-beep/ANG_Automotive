"""
Test Suite for Flask Web Application, REST Endpoints, and Telematics Controllers.
"""

import pytest
import json
from app import app, db, User, Car, Part

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            if not User.query.filter_by(username='admin').first():
                db.session.add(User(username='admin', password='ANG2026_Admin', role="MASTER_TUNER"))
                db.session.commit()
        yield client

def test_index_page(client):
    res = client.get('/')
    assert res.status_code == 200
    assert b"ANG AUTOMOTIVE" in res.data
    assert b"Live 50Hz Gauges" in res.data
    assert b"3D Surface Map Visualizer" in res.data

def test_api_get_rom(client):
    res = client.get('/api/ecu/rom')
    assert res.status_code == 200
    data = json.loads(res.data)
    assert "ecu_type" in data
    assert "tables" in data
    assert "ignition_timing" in data["tables"]
    assert "target_boost" in data["tables"]

def test_api_apply_stage(client):
    res = client.post('/api/ecu/apply_stage', json={"stage": "STAGE_2_E85"})
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["calibration_version"] == "ANG_STAGE_2_PLUS_E85"
    assert data["flex_fuel_ethanol_pct"] == 85.0

def test_api_live_telemetry(client):
    res = client.get('/api/telemetry/live')
    assert res.status_code == 200
    data = json.loads(res.data)
    assert "rpm" in data
    assert "boost_actual_psi" in data
    assert "lambda_actual" in data
    assert "safety" in data
    assert data["safety"]["status"] in ["SAFE", "WARNING", "DERATED"]

def test_api_dtc_read_and_clear(client):
    res_read = client.get('/api/dtc/read')
    assert res_read.status_code == 200
    dtcs = json.loads(res_read.data)["dtcs"]
    assert len(dtcs) > 0

    res_clear = client.post('/api/dtc/clear')
    assert res_clear.status_code == 200

    res_read2 = client.get('/api/dtc/read')
    assert len(json.loads(res_read2.data)["dtcs"]) == 0

def test_api_datalog_analyzer(client):
    csv_sample = """RPM,Pedal,Boost Target,Actual Boost,Lambda,Lambda Target,Timing,Knock Retard,WGDC,Coolant Temp,Oil Temp,EGT,HPFP,Ethanol
2500,50,1500,1490,0.92,0.92,18.0,0.0,30,90,92,550,200,10
4000,100,2200,2180,0.82,0.82,13.5,0.0,65,91,95,720,195,10
"""
    res = client.post('/api/datalog/analyze', json={"csv_content": csv_sample})
    assert res.status_code == 200
    data = json.loads(res.data)
    assert "summary" in data
    assert data["summary"]["peak_rpm"] == 4000.0
    assert len(data["recommendations"]) > 0

def test_api_flash_ecu_success(client):
    # Get current ROM
    rom_res = client.get('/api/ecu/rom')
    rom_data = json.loads(rom_res.data)

    res = client.post('/api/ecu/flash', json={"rom": rom_data, "battery_voltage": 13.8})
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["success"] is True
    assert data["state"] == "COMPLETED"

def test_api_flash_ecu_simulate_fault_and_rollback(client):
    rom_res = client.get('/api/ecu/rom')
    rom_data = json.loads(rom_res.data)

    # Trigger simulated fault at TRANSFER_DATA
    res = client.post('/api/ecu/flash', json={"rom": rom_data, "simulate_fault": "TRANSFER_DATA", "battery_voltage": 13.8})
    assert res.status_code == 400
    data = json.loads(res.data)
    assert data["success"] is False
    assert any("ROLLBACK" in l for l in data["log"])

def test_api_security_certificate_issuance(client):
    res = client.post('/api/security/issue_cert', json={
        "dongle_id": "ANG-ENET-PRO-7711",
        "vin": "WBA3R9C50K5A99887",
        "role": "MASTER_TUNER"
    })
    assert res.status_code == 200
    data = json.loads(res.data)
    assert "client_certificate_pem" in data
    assert "ca_certificate_pem" in data

    # Verify cert
    res_v = client.post('/api/security/verify_cert', json={
        "cert_pem": data["client_certificate_pem"],
        "dongle_id": "ANG-ENET-PRO-7711"
    })
    assert res_v.status_code == 200
    assert json.loads(res_v.data)["valid"] is True
