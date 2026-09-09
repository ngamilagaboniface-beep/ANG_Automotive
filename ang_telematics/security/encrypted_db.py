"""
Encrypted SQLite and File Storage Layer for ECU Binary Calibration Maps, Datalogs, and Flash Logs.
Uses AES-256-GCM authenticated encryption for sensitive tuning binaries and customer vehicle records.
"""

from __future__ import annotations
import os
import sqlite3
import json
import base64
import time
import tempfile
from typing import Dict, Any, List, Optional, Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

class EncryptedStorageEngine:
    """
    Cryptographic storage engine using AES-256-GCM.
    Derives key from master secret using PBKDF2-HMAC-SHA256 with fixed salt.
    """
    def __init__(self, db_path: Optional[str] = None, master_secret: str = "ANG_BMW_MOTORSPORT_KEY_2026") -> None:
        self.db_path = db_path or os.path.join(tempfile.gettempdir(), "ang_secure_telematics.db")
        self._master_secret = master_secret
        self._aesgcm = self._derive_key(master_secret)
        self._init_sqlite()

    def _derive_key(self, secret: str) -> AESGCM:
        salt = b"ANG_AUTOMOTIVE_PBKDF2_SALT_BMW_V3"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000
        )
        key = kdf.derive(secret.encode("utf-8"))
        return AESGCM(key)

    def encrypt_data(self, plaintext: bytes) -> Tuple[bytes, bytes]:
        """Returns (ciphertext, nonce)."""
        nonce = os.urandom(12) # 96-bit standard nonce for AES-GCM
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)
        return ciphertext, nonce

    def decrypt_data(self, ciphertext: bytes, nonce: bytes) -> bytes:
        return self._aesgcm.decrypt(nonce, ciphertext, None)

    def _init_sqlite(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS calibration_roms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vin TEXT NOT NULL,
                ecu_type TEXT NOT NULL,
                stage_name TEXT NOT NULL,
                calibration_version TEXT NOT NULL,
                encrypted_payload BLOB NOT NULL,
                nonce BLOB NOT NULL,
                sha256_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS datalogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_name TEXT NOT NULL,
                vin TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                summary_json TEXT NOT NULL,
                encrypted_csv BLOB NOT NULL,
                nonce BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS flash_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vin TEXT NOT NULL,
                ecu_type TEXT NOT NULL,
                stage TEXT NOT NULL,
                tuner_role TEXT NOT NULL,
                dongle_id TEXT NOT NULL,
                status TEXT NOT NULL,
                log_details TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def store_rom(self, vin: str, ecu_type: str, stage_name: str, cal_version: str, rom_bytes: bytes) -> int:
        import hashlib
        sha_hex = hashlib.sha256(rom_bytes).hexdigest()
        ciphertext, nonce = self.encrypt_data(rom_bytes)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO calibration_roms (vin, ecu_type, stage_name, calibration_version, encrypted_payload, nonce, sha256_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (vin, ecu_type, stage_name, cal_version, ciphertext, nonce, sha_hex)
        )
        row_id = cur.lastrowid
        conn.commit()
        conn.close()
        return int(row_id or 0)

    def load_rom(self, rom_id: int) -> Optional[bytes]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT encrypted_payload, nonce FROM calibration_roms WHERE id = ?", (rom_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        ciphertext, nonce = row
        return self.decrypt_data(ciphertext, nonce)

    def list_roms(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, vin, ecu_type, stage_name, calibration_version, sha256_hash, created_at FROM calibration_roms ORDER BY id DESC")
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "id": r[0], "vin": r[1], "ecu_type": r[2], "stage_name": r[3],
                "calibration_version": r[4], "sha256": r[5], "created_at": r[6]
            }
            for r in rows
        ]

    def record_flash_audit(self, vin: str, ecu_type: str, stage: str, tuner_role: str, dongle_id: str, status: str, log_details: str) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO flash_audit_logs (vin, ecu_type, stage, tuner_role, dongle_id, status, log_details) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (vin, ecu_type, stage, tuner_role, dongle_id, status, log_details)
        )
        conn.commit()
        conn.close()

    def get_flash_audit_logs(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, vin, ecu_type, stage, tuner_role, dongle_id, status, log_details, created_at FROM flash_audit_logs ORDER BY id DESC")
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "id": r[0], "vin": r[1], "ecu_type": r[2], "stage": r[3],
                "tuner_role": r[4], "dongle_id": r[5], "status": r[6],
                "log_details": r[7], "created_at": r[8]
            }
            for r in rows
        ]
