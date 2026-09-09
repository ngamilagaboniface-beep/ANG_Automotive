# ANG Automotive - Windows Setup & Deployment Guide

This guide provides step-by-step instructions to run the **ANG Automotive BMW Diagnostic & Remote ECU Tuning Platform** natively on **Windows 10 / Windows 11 / Windows Server**.

---

## ⚡ Quick Start (1-Click Run on Windows)

1. **Install Python 3.10 or newer:**
   - Download from [python.org/downloads](https://www.python.org/downloads/).
   - ⚠️ **Important:** During installation, check the box **`"Add Python to PATH"`**.

2. **Launch the Application:**
   - Double-click **`run_windows.bat`** (or open PowerShell and run `.\run_windows.ps1`).
   - The script will automatically:
     - Create an isolated Python virtual environment (`venv`).
     - Install all required cryptographic, numerical, and automotive protocol libraries.
     - Start the ISO 13400 DoIP gateway and web server on port `5000`.
     - Automatically open your default web browser to `http://localhost:5000`.

---

## 🔧 Connecting to a BMW Vehicle on Windows (ENET Cable / ICOM)

### 1. Physical Cable Connection
- Plug the **OBD2 connector** of your **BMW ENET Cable** into the vehicle's OBD2 port (under the steering column).
- Plug the **RJ45 Ethernet connector** into your Windows PC (or via USB-C to Gigabit Ethernet adapter).
- Turn the vehicle ignition **ON** (Engine OFF, press start button without touching the brake).

### 2. Configure Windows Ethernet Adapter (APIPA / Static IP)
BMW F-Series / G-Series vehicles use **APIPA (Automatic Private IP Addressing)** for DoIP communication:
1. Open **Windows Settings** $\rightarrow$ **Network & Internet** $\rightarrow$ **Ethernet**.
2. Click **Edit IP Settings** $\rightarrow$ Set to **Automatic (DHCP)**.
3. Windows will automatically assign an IP in the `169.254.x.x` range (Subnet: `255.255.0.0`).
4. Alternatively, set Static IP:
   - **IP Address:** `169.254.1.100`
   - **Subnet Mask:** `255.255.0.0`
   - **Default Gateway:** *(Leave blank)*

### 3. Windows Defender Firewall Rule (Allowing Port 13400)
To allow Windows to communicate over ISO 13400 DoIP:
1. Open **Windows PowerShell as Administrator** and run:
   ```powershell
   New-NetFirewallRule -DisplayName "ANG BMW DoIP 13400 TCP" -Direction Inbound -LocalPort 13400 -Protocol TCP -Action Allow
   New-NetFirewallRule -DisplayName "ANG BMW DoIP 13400 UDP" -Direction Inbound -LocalPort 13400 -Protocol UDP -Action Allow
   ```

---

## 🧪 Running Automated Verification Tests on Windows

To verify all ISO 13400 DoIP headers, ISO 14229 UDS positive response byte shifts, Seed-Key crypto routines, and fail-safe flashing rollback handlers:

- Double-click **`setup_windows.bat`**, or run in CMD:
  ```cmd
  venv\Scripts\activate.bat
  pytest -v
  ```
- All 43 test suites will run and output green checkmarks.

---

## 🛠️ Supported BMW Engine Control Units on Windows

| ECU Generation | Engine Families | Models Supported | Protocol Layer |
| :--- | :--- | :--- | :--- |
| **Bosch MEVD17** | N20, N55, S55 | F80 M3, F82 M4, F87 M2, F30 335i, F22 M235i | ISO 13400 DoIP / ISO 14229 UDS |
| **Siemens MSD80/81/85** | N54, N63, S63 | E90/E92 335i, 135i, F10 M5, E70 X5M | ISO 13400 DoIP / ISO 14229 UDS |
| **Bosch MG1 / MD1** | B48, B58, S58, B57 | G20 M340i, G80 M3, G82 M4, Toyota Supra A90 | ISO 13400 DoIP / ISO 14229 UDS |

---

## ❓ Troubleshooting on Windows

- **Port 5000 Already in Use:**
  - If another Windows service is using port 5000, start with:
    ```cmd
    python -c "from app import app; app.run(port=5050)"
    ```
  - Open `http://localhost:5050` in your browser.

- **PowerShell ExecutionPolicy Restriction:**
  - If PowerShell blocks `.\run_windows.ps1`, run:
    ```powershell
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\run_windows.ps1
    ```
