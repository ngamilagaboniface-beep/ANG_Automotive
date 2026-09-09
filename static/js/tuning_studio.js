/**
 * ANG Automotive - BMW ECU Tuning Studio & Telematics Orchestrator.
 * Full integration of WebGL 3D maps, 50Hz gauges, UDS flashing pipeline, AI datalog analysis, and security.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Initialize Gauges, Oscilloscope, and 3D Surface Visualizer
  const gauges = new TelematicsGauges();
  const oscilloscope = new TelemetryOscilloscope('telemetry-canvas');
  const surface3D = new SurfaceVisualizer3D('webgl-surface-canvas');

  // State
  let activeRomData = null;
  let activeTableName = 'ignition_timing';
  let isFlashing = false;
  let currentRole = 'MASTER_TUNER';

  // DOM Elements
  const tabButtons = document.querySelectorAll('.m-nav-btn, .nav-tab');
  const tabPanes = document.querySelectorAll('.tab-pane');
  const tableSelector = document.getElementById('table-selector');
  const stagePresetSelect = document.getElementById('stage-preset-select');
  const ethSlider = document.getElementById('flex-fuel-slider');
  const ethValBadge = document.getElementById('flex-fuel-val');
  const burbleDurationSlider = document.getElementById('burble-duration-slider');
  const burbleDurationVal = document.getElementById('burble-duration-val');
  const burbleAggressionSelect = document.getElementById('burble-aggression-select');
  const vmaxToggle = document.getElementById('toggle-vmax');
  const coldStartToggle = document.getElementById('toggle-cold-start');
  const flapToggle = document.getElementById('toggle-exhaust-flap');
  const linearThrottleToggle = document.getElementById('toggle-linear-throttle');

  const flashBtn = document.getElementById('btn-flash-ecu');
  const rollbackTestBtn = document.getElementById('btn-test-rollback');
  const flashProgressBar = document.getElementById('flash-progress-bar');
  const flashStatusText = document.getElementById('flash-status-text');
  const terminalConsole = document.getElementById('terminal-console');

  // Tab Navigation Handler
  tabButtons.forEach(btn => {
    btn.addEventListener('click', (e) => {
      const targetTab = btn.getAttribute('data-tab');
      if (!targetTab) return; // standard href link
      e.preventDefault();
      tabButtons.forEach(b => {
        if (b.getAttribute('data-tab')) b.classList.remove('active');
      });
      tabPanes.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const pane = document.getElementById(`tab-${targetTab}`);
      if (pane) pane.classList.add('active');

      if (targetTab === 'maps' && surface3D) {
        setTimeout(() => surface3D._resizeCanvas(), 60);
      }
    });
  });

  // M1 / M2 Drive Mode Steering Buttons
  const btnM1 = document.getElementById('btn-m1-mode');
  const btnM2 = document.getElementById('btn-m2-mode');

  if (btnM1) {
    btnM1.addEventListener('click', async () => {
      btnM1.classList.toggle('active-m1');
      if (btnM2) btnM2.classList.remove('active-m2');
      if (btnM1.classList.contains('active-m1')) {
        logTerminal(`[M DRIVE] M1 SPORT PLUS ACTIVATED: Stage 2 93 Octane, Active Flaps OPEN, Linear Throttle ON.`, 'info');
        if (stagePresetSelect) {
          stagePresetSelect.value = 'STAGE_2';
          stagePresetSelect.dispatchEvent(new Event('change'));
        }
      } else {
        logTerminal(`[M DRIVE] COMFORT MODE: OEM Baseline.`, 'info');
        if (stagePresetSelect) {
          stagePresetSelect.value = 'STOCK';
          stagePresetSelect.dispatchEvent(new Event('change'));
        }
      }
    });
  }

  if (btnM2) {
    btnM2.addEventListener('click', async () => {
      btnM2.classList.toggle('active-m2');
      if (btnM1) btnM1.classList.remove('active-m1');
      if (btnM2.classList.contains('active-m2')) {
        logTerminal(`[M DRIVE] M2 TRACK / E85 KILL MAP ACTIVATED: Stage 2+ E85, +4.5° Timing, Max Boost 22.5 PSI, GTS Overrun!`, 'warn');
        if (stagePresetSelect) {
          stagePresetSelect.value = 'STAGE_2_E85';
          stagePresetSelect.dispatchEvent(new Event('change'));
        }
      } else {
        logTerminal(`[M DRIVE] COMFORT MODE: OEM Baseline.`, 'info');
        if (stagePresetSelect) {
          stagePresetSelect.value = 'STOCK';
          stagePresetSelect.dispatchEvent(new Event('change'));
        }
      }
    });
  }

  // 1. Fetch ECU ROM Calibration Tables
  async function loadCalibrationRom() {
    try {
      const res = await fetch('/api/ecu/rom');
      const data = await res.json();
      activeRomData = data;
      populateTableSelector();
      loadActiveTable();
      updateCustomizationUI();
    } catch (err) {
      console.error('Failed to load ECU ROM:', err);
      logTerminal(`Error loading ECU calibration: ${err.message}`, 'error');
    }
  }

  function populateTableSelector() {
    if (!activeRomData || !activeRomData.tables || !tableSelector) return;
    tableSelector.innerHTML = '';
    Object.keys(activeRomData.tables).forEach(name => {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = activeRomData.tables[name].name;
      tableSelector.appendChild(opt);
    });
    tableSelector.value = activeTableName;
  }

  function loadActiveTable() {
    if (!activeRomData || !activeRomData.tables) return;
    const tbl = activeRomData.tables[activeTableName];
    if (!tbl) return;

    if (surface3D) surface3D.setData(tbl);
    render2DTableEditor(tbl);
  }

  if (tableSelector) {
    tableSelector.addEventListener('change', (e) => {
      activeTableName = e.target.value;
      loadActiveTable();
    });
  }

  // 2. Render 2D Spreadsheet Grid synchronized with 3D WebGL
  function render2DTableEditor(tbl) {
    const container = document.getElementById('table-grid-container');
    if (!container) return;

    let html = `<table class="table-matrix"><thead><tr><th>Load / RPM</th>`;
    tbl.x_axis.forEach(x => {
      html += `<th>${x.toFixed(0)}</th>`;
    });
    html += `</tr></thead><tbody>`;

    tbl.matrix.forEach((row, yIdx) => {
      const yVal = tbl.y_axis[yIdx];
      html += `<tr><th>${yVal.toFixed(0)}</th>`;
      row.forEach((val, xIdx) => {
        const isSel = (surface3D.selectedCell.x === xIdx && surface3D.selectedCell.y === yIdx);
        html += `<td class="cal-cell ${isSel ? 'selected' : ''}" data-x="${xIdx}" data-y="${yIdx}">${val.toFixed(tbl.unit === 'Lambda' ? 3 : 1)}</td>`;
      });
      html += `</tr>`;
    });
    html += `</tbody></table>`;
    container.innerHTML = html;

    // Attach Cell Click Handler
    container.querySelectorAll('.cal-cell').forEach(cell => {
      cell.addEventListener('click', () => {
        const x = parseInt(cell.getAttribute('data-x'));
        const y = parseInt(cell.getAttribute('data-y'));
        surface3D.selectedCell = { x, y };
        surface3D.render();
        container.querySelectorAll('.cal-cell').forEach(c => c.classList.remove('selected'));
        cell.classList.add('selected');
        const input = document.getElementById('selected-cell-val');
        if (input) input.value = tbl.matrix[y][x];
      });
    });
  }

  // 3D cell pick callback -> updates 2D spreadsheet highlight
  if (surface3D) {
    surface3D.onCellSelectedCallback = (x, y, val) => {
      const cellInput = document.getElementById('selected-cell-val');
      if (cellInput) cellInput.value = val;
      const container = document.getElementById('table-grid-container');
      if (container) {
        container.querySelectorAll('.cal-cell').forEach(c => c.classList.remove('selected'));
        const targetCell = container.querySelector(`.cal-cell[data-x="${x}"][data-y="${y}"]`);
        if (targetCell) targetCell.classList.add('selected');
      }
    };
  }

  // Edit Single Selected Cell
  const applyCellBtn = document.getElementById('btn-apply-cell');
  if (applyCellBtn) {
    applyCellBtn.addEventListener('click', () => {
      if (!activeRomData || !activeRomData.tables) return;
      const tbl = activeRomData.tables[activeTableName];
      const cellInput = document.getElementById('selected-cell-val');
      const newVal = parseFloat(cellInput ? cellInput.value : NaN);
      if (isNaN(newVal)) return;

      const { x, y } = surface3D.selectedCell;
      tbl.matrix[y][x] = newVal;
      surface3D.setData(tbl);
      render2DTableEditor(tbl);
    });
  }

  // Bulk Table Offset (+0.5 / -0.5)
  document.querySelectorAll('.btn-table-offset').forEach(btn => {
    btn.addEventListener('click', () => {
      if (!activeRomData || !activeRomData.tables) return;
      const tbl = activeRomData.tables[activeTableName];
      const delta = parseFloat(btn.getAttribute('data-delta'));
      tbl.matrix.forEach((row, y) => {
        row.forEach((val, x) => {
          tbl.matrix[y][x] = Math.round((val + delta) * 10) / 10;
        });
      });
      surface3D.setData(tbl);
      render2DTableEditor(tbl);
    });
  });

  // 3. Multi-Map Customization Event Handlers
  if (ethSlider && ethValBadge) {
    ethSlider.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value);
      ethValBadge.textContent = `E${val.toFixed(0)}`;
      if (activeRomData) activeRomData.flex_fuel_ethanol_pct = val;
    });
  }

  if (burbleDurationSlider && burbleDurationVal) {
    burbleDurationSlider.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value);
      burbleDurationVal.textContent = `${val.toFixed(1)}s`;
      if (activeRomData) activeRomData.burble_duration_sec = val;
    });
  }

  if (stagePresetSelect) {
    stagePresetSelect.addEventListener('change', async (e) => {
      const stage = e.target.value;
      logTerminal(`Applying Preset Calibration Profile: ${stage}...`, 'info');
      try {
        const res = await fetch('/api/ecu/apply_stage', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ stage })
        });
        const data = await res.json();
        activeRomData = data;
        loadActiveTable();
        updateCustomizationUI();
        logTerminal(`Profile ${stage} successfully synthesized & loaded into workspace.`, 'success');
      } catch (err) {
        logTerminal(`Error applying stage preset: ${err.message}`, 'error');
      }
    });
  }

  function updateCustomizationUI() {
    if (!activeRomData) return;
    if (vmaxToggle) vmaxToggle.checked = activeRomData.vmax_disabled;
    if (coldStartToggle) coldStartToggle.checked = activeRomData.cold_start_cat_heating_enabled;
    if (flapToggle) flapToggle.checked = activeRomData.exhaust_flap_sport_open;
    if (linearThrottleToggle) linearThrottleToggle.checked = activeRomData.linear_throttle_mapping;
    if (ethSlider && ethValBadge) {
      ethSlider.value = activeRomData.flex_fuel_ethanol_pct;
      ethValBadge.textContent = `E${Math.round(activeRomData.flex_fuel_ethanol_pct)}`;
    }
    if (burbleDurationSlider && burbleDurationVal) {
      burbleDurationSlider.value = activeRomData.burble_duration_sec;
      burbleDurationVal.textContent = `${activeRomData.burble_duration_sec.toFixed(1)}s`;
    }
    const calVerBadge = document.getElementById('current-cal-version');
    if (calVerBadge) calVerBadge.textContent = activeRomData.calibration_version;
  }

  // 4. Safe ECU Flashing Pipeline Execution
  if (flashBtn) {
    flashBtn.addEventListener('click', () => executeFlashingSequence(false));
  }
  if (rollbackTestBtn) {
    rollbackTestBtn.addEventListener('click', () => executeFlashingSequence(true));
  }

  async function executeFlashingSequence(simulateFault) {
    if (isFlashing) return;
    isFlashing = true;
    if (flashBtn) flashBtn.disabled = true;
    if (rollbackTestBtn) rollbackTestBtn.disabled = true;

    logTerminal(`====================================================`, 'info');
    logTerminal(`INITIATING UDS ISO 14229 OVER DoIP ISO 13400 FLASHING`, 'info');
    logTerminal(`Simulate Fault Mode: ${simulateFault ? 'YES (TRANSFER_DATA FAILURE)' : 'NO (PRODUCTION RUN)'}`, simulateFault ? 'warn' : 'info');
    logTerminal(`====================================================`, 'info');

    try {
      const payload = {
        rom: activeRomData,
        simulate_fault: simulateFault ? 'TRANSFER_DATA' : null,
        battery_voltage: 13.8
      };

      const res = await fetch('/api/ecu/flash', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const result = await res.json();

      if (result.log) {
        result.log.forEach(entry => logTerminal(entry, result.success ? 'success' : 'warn'));
      }

      if (result.success) {
        setFlashProgress(100, 'ECU REFLASH COMPLETED SUCCESSFULLY!');
        logTerminal(`FLASH VERIFIED: Secure Boot RSA-2048 & CRC32 Validated. Engine Ready.`, 'success');
      } else {
        setFlashProgress(100, 'REFLASH ABORTED - AUTOMATIC ROLLBACK RESTORED FACTORY OEM IMAGE');
        logTerminal(`SAFEGUARD TRIGGERED: ${result.error || 'Flashing faulted'}. Rollback completed cleanly.`, 'error');
      }
    } catch (err) {
      logTerminal(`Communication error during flash: ${err.message}`, 'error');
      setFlashProgress(0, 'FLASH FAILED');
    } finally {
      isFlashing = false;
      if (flashBtn) flashBtn.disabled = false;
      if (rollbackTestBtn) rollbackTestBtn.disabled = false;
    }
  }

  function setFlashProgress(pct, statusText) {
    if (flashProgressBar) flashProgressBar.style.width = `${pct}%`;
    if (flashStatusText) flashStatusText.textContent = `${pct}% - ${statusText}`;
  }

  function logTerminal(msg, level = 'info') {
    if (!terminalConsole) return;
    const p = document.createElement('div');
    p.className = `log-line ${level}`;
    p.textContent = msg;
    terminalConsole.appendChild(p);
    terminalConsole.scrollTop = terminalConsole.scrollHeight;
  }

  // 5. 50Hz Live Telematics Streaming Loop
  async function pollLiveTelemetry() {
    try {
      const res = await fetch('/api/telemetry/live');
      if (res.ok) {
        const snap = await res.json();

        // Update gauges & oscilloscope
        gauges.update(snap);
        oscilloscope.addPoint(snap);

        // Update Digital Readout Badges
        const setTxt = (id, val) => {
          const el = document.getElementById(id);
          if (el) el.textContent = val;
        };

        setTxt('live-stat-rpm', Math.round(snap.rpm));
        setTxt('live-stat-boost', `${snap.boost_actual_psi.toFixed(1)} PSI`);
        setTxt('live-stat-afr', snap.afr_actual.toFixed(2));
        setTxt('live-stat-coolant', `${snap.coolant_c.toFixed(0)}°C`);
        setTxt('live-stat-oil', `${snap.oil_c.toFixed(0)}°C`);
        setTxt('live-stat-egt', `${snap.egt_c.toFixed(0)}°C`);

        // Update Safety Monitor Card
        const safetyBadge = document.getElementById('safety-status-badge');
        if (safetyBadge && snap.safety) {
          safetyBadge.className = `m-badge ${snap.safety.status === 'SAFE' ? 'm-badge-success' : (snap.safety.reversion_required ? 'm-badge-danger' : 'm-badge-warning')}`;
          safetyBadge.textContent = snap.safety.status;
        }
      }
    } catch (e) {
      // transient network poll error
    } finally {
      setTimeout(pollLiveTelemetry, 100); // 10Hz browser UI poll rate (backend computes at 50Hz)
    }
  }

  // Throttle Input Slider for Engine Simulator
  const throttleSlider = document.getElementById('sim-throttle-slider');
  if (throttleSlider) {
    throttleSlider.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value);
      const valEl = document.getElementById('sim-throttle-val');
      if (valEl) valEl.textContent = `${val.toFixed(0)}%`;
      fetch('/api/simulator/throttle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ throttle_pct: val })
      }).catch(() => {});
    });
  }

  // 6. DTC Scanner
  const readDtcBtn = document.getElementById('btn-read-dtc');
  const clearDtcBtn = document.getElementById('btn-clear-dtc');
  if (readDtcBtn) {
    readDtcBtn.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/dtc/read');
        const data = await res.json();
        renderDtcList(data.dtcs || []);
      } catch (err) {
        console.error('Failed to read DTCs:', err);
      }
    });
  }
  if (clearDtcBtn) {
    clearDtcBtn.addEventListener('click', async () => {
      try {
        await fetch('/api/dtc/clear', { method: 'POST' });
        renderDtcList([]);
        logTerminal('DTC memory cleared across all control units.', 'success');
      } catch (err) {
        console.error('Failed to clear DTCs:', err);
      }
    });
  }

  function renderDtcList(dtcs) {
    const list = document.getElementById('dtc-results-list');
    if (!list) return;
    if (dtcs.length === 0) {
      list.innerHTML = `<div style="color: var(--accent-green); padding: 0.75rem; font-size: 0.85rem;"><i class="fas fa-check-circle"></i> No Diagnostic Trouble Codes present. All ECU systems normal.</div>`;
      return;
    }
    let html = '';
    dtcs.forEach(d => {
      html += `<div class="dtc-item"><div class="dtc-code">${d.code}</div><div class="dtc-desc">${d.description}</div><span class="m-badge m-badge-warning">${d.status}</span></div>`;
    });
    list.innerHTML = html;
  }

  // 7. AI Datalog Analysis & File Upload
  const datalogUpload = document.getElementById('datalog-file-input');
  if (datalogUpload) {
    datalogUpload.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const text = await file.text();
      try {
        const res = await fetch('/api/datalog/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ csv_content: text })
        });
        const report = await res.json();
        renderDatalogReport(report);
      } catch (err) {
        console.error('Datalog analysis failed:', err);
      }
    });
  }

  function renderDatalogReport(report) {
    const container = document.getElementById('datalog-report-container');
    if (!container || !report.summary) return;
    const s = report.summary;

    let recHtml = '';
    (report.recommendations || []).forEach(r => {
      const colorClass = r.severity === 'CRITICAL' ? 'm-badge-danger' : (r.severity === 'WARNING' ? 'm-badge-warning' : 'm-badge-success');
      recHtml += `<div style="background: var(--bg-carbon); border: 1px solid var(--border-subtle); padding: 0.85rem; border-radius: 6px; margin-bottom: 0.5rem;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.35rem;">
          <strong style="color: #fff;">${r.category}</strong>
          <span class="m-badge ${colorClass}">${r.severity}</span>
        </div>
        <div style="font-size: 0.8rem; color: var(--text-secondary);">${r.message}</div>
        <div style="font-size: 0.78rem; color: var(--accent-cyan); margin-top: 0.25rem;">Action: ${r.action}</div>
      </div>`;
    });

    container.innerHTML = `
      <div class="m-kpi-grid" style="margin-top: 1rem;">
        <div class="m-kpi-card blue"><div class="m-kpi-label">Peak Boost</div><div class="m-kpi-value">${s.peak_boost_psi} <span class="m-kpi-unit">PSI</span></div></div>
        <div class="m-kpi-card yellow"><div class="m-kpi-label">Max Knock Retard</div><div class="m-kpi-value" style="color: ${s.max_knock_retard > 3 ? '#ff4d4d' : 'inherit'};">${s.max_knock_retard}°</div></div>
        <div class="m-kpi-card green"><div class="m-kpi-label">WOT Mean Lambda</div><div class="m-kpi-value">${s.wot_mean_lambda}</div></div>
        <div class="m-kpi-card"><div class="m-kpi-label">Peak EGT</div><div class="m-kpi-value">${s.peak_egt_c}°C</div></div>
      </div>
      <h4 style="margin: 1.25rem 0 0.75rem 0; color: #fff;">AI Calibration Insights & Recommendations</h4>
      ${recHtml}
      <button id="btn-apply-ai-tune" class="btn-m-action" style="margin-top: 0.75rem;"><i class="fas fa-magic"></i> Auto-Apply AI Timing & Boost Optimizations</button>
    `;

    document.getElementById('btn-apply-ai-tune')?.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/ecu/autotune', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ analysis_report: report })
        });
        const tuned = await res.json();
        activeRomData = tuned.rom;
        loadActiveTable();
        updateCustomizationUI();
        logTerminal(`AI Auto-Tune applied! Changes: ${tuned.changelog.join(' | ')}`, 'success');
      } catch (err) {
        logTerminal(`Auto-tune error: ${err.message}`, 'error');
      }
    });
  }

  // 8. Hardware Bridge & mTLS Certificate Tool
  const genCertBtn = document.getElementById('btn-generate-cert');
  if (genCertBtn) {
    genCertBtn.addEventListener('click', async () => {
      const dongleId = document.getElementById('input-dongle-id').value || 'ANG-ENET-PRO-8921';
      const vin = document.getElementById('input-vin').value || 'WBA3R9C50K5A12345';
      try {
        const res = await fetch('/api/security/issue_cert', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ dongle_id: dongleId, vin: vin, role: currentRole })
        });
        const creds = await res.json();
        document.getElementById('cert-pem-display').value = creds.client_certificate_pem;
        logTerminal(`mTLS X.509 Client Certificate successfully issued for Hardware Dongle ${dongleId} (VIN: ${vin}).`, 'success');
      } catch (err) {
        logTerminal(`Failed to issue certificate: ${err.message}`, 'error');
      }
    });
  }

  // Initial Load & Start Polling
  loadCalibrationRom();
  pollLiveTelemetry();
});
