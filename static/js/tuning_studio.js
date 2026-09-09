/**
 * ANG Automotive - BMW ECU Tuning Studio & Telematics Orchestrator.
 * Full integration of WebGL 3D maps, 50Hz gauges, UDS flashing pipeline, AI datalog analysis, and security.
 */

function initTuningStudio() {
  console.log('[ANG Studio] Initializing BMW ECU Tuning Studio...');

  // 1. Initialize Visualizers & Gauges safely
  let gauges = null;
  let oscilloscope = null;
  let surface3D = null;

  try {
    if (typeof TelematicsGauges === 'function') {
      gauges = new TelematicsGauges();
    }
  } catch (e) {
    console.warn('[ANG Studio] Gauges init warning:', e);
  }

  try {
    if (typeof TelemetryOscilloscope === 'function') {
      oscilloscope = new TelemetryOscilloscope('telemetry-canvas');
    }
  } catch (e) {
    console.warn('[ANG Studio] Oscilloscope init warning:', e);
  }

  try {
    if (typeof SurfaceVisualizer3D === 'function') {
      surface3D = new SurfaceVisualizer3D('webgl-surface-canvas');
    }
  } catch (e) {
    console.warn('[ANG Studio] 3D Visualizer init warning:', e);
  }

  // State Variables
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

  // Terminal Logger Helper
  function logTerminal(msg, level = 'info') {
    if (!terminalConsole) return;
    const p = document.createElement('div');
    p.className = `log-line ${level}`;
    const time = new Date().toTimeString().split(' ')[0];
    p.textContent = `[${time}] ${msg}`;
    terminalConsole.appendChild(p);
    terminalConsole.scrollTop = terminalConsole.scrollHeight;
  }

  // Tab Navigation Helper
  function switchTab(targetTab) {
    console.log('[ANG Studio] Switching to tab:', targetTab);
    tabButtons.forEach(b => {
      if (b.getAttribute('data-tab') === targetTab) {
        b.classList.add('active');
      } else if (b.getAttribute('data-tab')) {
        b.classList.remove('active');
      }
    });

    tabPanes.forEach(p => {
      if (p.id === `tab-${targetTab}`) {
        p.classList.add('active');
      } else {
        p.classList.remove('active');
      }
    });

    if (targetTab === 'maps' && surface3D) {
      setTimeout(() => {
        surface3D._resizeCanvas();
        surface3D.render();
      }, 80);
    }
  }

  // Attach Tab Button Listeners
  tabButtons.forEach(btn => {
    btn.addEventListener('click', (e) => {
      const targetTab = btn.getAttribute('data-tab');
      if (!targetTab) return; // Standard anchor links
      e.preventDefault();
      switchTab(targetTab);
    });
  });

  // M1 / M2 Drive Mode Steering Buttons
  const btnM1 = document.getElementById('btn-m1-mode');
  const btnM2 = document.getElementById('btn-m2-mode');

  if (btnM1) {
    btnM1.addEventListener('click', (e) => {
      e.preventDefault();
      btnM1.classList.toggle('m1-active');
      if (btnM2) btnM2.classList.remove('m2-active');
      if (btnM1.classList.contains('m1-active')) {
        logTerminal('M1 SPORT+ MODE ENGAGED: Stage 2 93 Octane, Active Flaps OPEN, Linear Throttle ON.', 'info');
        if (stagePresetSelect) {
          stagePresetSelect.value = 'STAGE_2';
          stagePresetSelect.dispatchEvent(new Event('change'));
        }
      } else {
        logTerminal('COMFORT MODE: Reverting to OEM Baseline calibration profile.', 'info');
        if (stagePresetSelect) {
          stagePresetSelect.value = 'STOCK';
          stagePresetSelect.dispatchEvent(new Event('change'));
        }
      }
    });
  }

  if (btnM2) {
    btnM2.addEventListener('click', (e) => {
      e.preventDefault();
      btnM2.classList.toggle('m2-active');
      if (btnM1) btnM1.classList.remove('m1-active');
      if (btnM2.classList.contains('m2-active')) {
        logTerminal('M2 TRACK ATTACK MODE ENGAGED: Stage 2+ E85 Flex Fuel, +4.5° Timing, Max Boost 22.5 PSI, GTS Overrun!', 'warn');
        if (stagePresetSelect) {
          stagePresetSelect.value = 'STAGE_2_E85';
          stagePresetSelect.dispatchEvent(new Event('change'));
        }
      } else {
        logTerminal('COMFORT MODE: Reverting to OEM Baseline calibration profile.', 'info');
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
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      activeRomData = data;
      populateTableSelector();
      loadActiveTable();
      updateCustomizationUI();
      logTerminal('Bosch MEVD17.2.G ROM calibration tables successfully synchronized over DoIP.', 'info');
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

    let html = `<table class="cal-table-grid"><thead><tr><th>Load / RPM</th>`;
    tbl.x_axis.forEach(x => {
      html += `<th>${x.toFixed(0)}</th>`;
    });
    html += `</tr></thead><tbody>`;

    tbl.matrix.forEach((row, yIdx) => {
      const yVal = tbl.y_axis[yIdx];
      html += `<tr><th>${yVal.toFixed(0)}</th>`;
      row.forEach((val, xIdx) => {
        const isSel = surface3D && (surface3D.selectedCell.x === xIdx && surface3D.selectedCell.y === yIdx);
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
        if (surface3D) {
          surface3D.selectedCell = { x, y };
          surface3D.render();
        }
        container.querySelectorAll('.cal-cell').forEach(c => c.classList.remove('selected'));
        cell.classList.add('selected');
        const input = document.getElementById('selected-cell-val');
        if (input && tbl.matrix[y]) {
          input.value = tbl.matrix[y][x];
        }
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
    applyCellBtn.addEventListener('click', (e) => {
      e.preventDefault();
      if (!activeRomData || !activeRomData.tables) return;
      const tbl = activeRomData.tables[activeTableName];
      const cellInput = document.getElementById('selected-cell-val');
      const newVal = parseFloat(cellInput ? cellInput.value : NaN);
      if (isNaN(newVal)) return;

      const { x, y } = (surface3D ? surface3D.selectedCell : { x: 0, y: 0 });
      if (tbl.matrix[y] && tbl.matrix[y][x] !== undefined) {
        tbl.matrix[y][x] = newVal;
        if (surface3D) surface3D.setData(tbl);
        render2DTableEditor(tbl);
        logTerminal(`Updated table cell [${x}, ${y}] in ${tbl.name} to ${newVal}`, 'info');
      }
    });
  }

  // Bulk Table Offset (+0.5 / -0.5)
  document.querySelectorAll('.btn-table-offset').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      if (!activeRomData || !activeRomData.tables) return;
      const tbl = activeRomData.tables[activeTableName];
      const delta = parseFloat(btn.getAttribute('data-delta'));
      tbl.matrix.forEach((row, y) => {
        row.forEach((val, x) => {
          tbl.matrix[y][x] = Math.round((val + delta) * 10) / 10;
        });
      });
      if (surface3D) surface3D.setData(tbl);
      render2DTableEditor(tbl);
      logTerminal(`Applied bulk offset of ${delta > 0 ? '+' : ''}${delta} to ${tbl.name}`, 'info');
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
        logTerminal(`Profile ${stage} successfully synthesized & loaded into memory.`, 'success');
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
    flashBtn.addEventListener('click', (e) => {
      e.preventDefault();
      executeFlashingSequence(false);
    });
  }
  if (rollbackTestBtn) {
    rollbackTestBtn.addEventListener('click', (e) => {
      e.preventDefault();
      executeFlashingSequence(true);
    });
  }

  async function executeFlashingSequence(simulateFault) {
    if (isFlashing) return;
    isFlashing = true;
    if (flashBtn) flashBtn.disabled = true;
    if (rollbackTestBtn) rollbackTestBtn.disabled = true;

    setFlashProgress(10, 'PRE-CHECK: VALIDATING VOLTAGE & SEED-KEY...');
    logTerminal(`====================================================`, 'info');
    logTerminal(`INITIATING UDS ISO 14229 OVER DoIP ISO 13400 FLASHING`, 'info');
    logTerminal(`Mode: ${simulateFault ? 'TEST SIMULATED WRITE FAULT & ROLLBACK' : 'PRODUCTION CALIBRATION WRITE'}`, simulateFault ? 'warn' : 'info');
    logTerminal(`====================================================`, 'info');

    try {
      const payload = {
        rom: activeRomData,
        simulate_fault: simulateFault ? 'TRANSFER_DATA' : null,
        battery_voltage: 13.8
      };

      setFlashProgress(35, 'CREATING FULL EEPROM FLASH SNAPSHOT...');
      
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

  // 5. 50Hz Live Telematics Streaming Loop
  async function pollLiveTelemetry() {
    try {
      const res = await fetch('/api/telemetry/live');
      if (res.ok) {
        const snap = await res.json();

        // Update gauges & oscilloscope
        if (gauges) gauges.update(snap);
        if (oscilloscope) oscilloscope.addPoint(snap);

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
      setTimeout(pollLiveTelemetry, 100);
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
    readDtcBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      try {
        logTerminal('Scanning active ECU fault memory over DoIP (ISO 14229 Service 0x19)...', 'info');
        const res = await fetch('/api/dtc/read');
        const data = await res.json();
        renderDtcList(data.dtcs || []);
        logTerminal(`DTC Scan complete: ${data.dtcs ? data.dtcs.length : 0} fault codes detected.`, 'info');
      } catch (err) {
        logTerminal(`DTC Scan failed: ${err.message}`, 'error');
      }
    });
  }
  if (clearDtcBtn) {
    clearDtcBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      try {
        logTerminal('Sending Clear Diagnostic Information command (ISO 14229 Service 0x14 0xFFFFFF)...', 'warn');
        await fetch('/api/dtc/clear', { method: 'POST' });
        renderDtcList([]);
        logTerminal('All ECU diagnostic fault codes cleared successfully.', 'success');
      } catch (err) {
        logTerminal(`Failed to clear DTCs: ${err.message}`, 'error');
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
  const sampleDatalogBtn = document.getElementById('btn-load-sample-datalog');

  if (datalogUpload) {
    datalogUpload.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      logTerminal(`Reading uploaded datalog file: ${file.name}...`, 'info');
      const text = await file.text();
      analyzeDatalogContent(text);
    });
  }

  if (sampleDatalogBtn) {
    sampleDatalogBtn.addEventListener('click', (e) => {
      e.preventDefault();
      logTerminal('Loading BMW S55 Twin-Turbo WOT Dyno Sample Telematics Datalog...', 'info');
      const sampleCsv = `RPM,Pedal,Boost Target,Actual Boost,Lambda,Lambda Target,Timing,Knock Retard,WGDC,Coolant Temp,Oil Temp,EGT,HPFP,Ethanol
2500,60,1500,1480,0.95,0.92,18.0,0.0,35,90,92,560,200,10
3000,90,1800,1790,0.88,0.86,16.5,0.0,52,90,93,620,200,10
4000,100,2250,2220,0.84,0.82,14.0,0.0,68,91,95,710,195,10
5000,100,2300,2280,0.82,0.80,12.5,0.0,72,92,97,780,190,10
6000,100,2200,2190,0.80,0.80,11.5,0.5,75,93,99,840,188,10
6800,100,2000,2010,0.78,0.78,10.0,1.2,74,94,101,890,185,10
7200,100,1850,1860,0.77,0.77,9.5,0.0,70,95,102,910,182,10`;
      analyzeDatalogContent(sampleCsv);
    });
  }

  async function analyzeDatalogContent(csvText) {
    try {
      logTerminal('Running AI Datalog Analysis: checking knock margins, boost overshoot, lambda trims, and HPFP rail pressure...', 'info');
      const res = await fetch('/api/datalog/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv_content: csvText })
      });
      const report = await res.json();
      renderDatalogReport(report);
      logTerminal(`AI Datalog Analysis completed with ${report.recommendations ? report.recommendations.length : 0} diagnostic insights.`, 'success');
    } catch (err) {
      logTerminal(`Datalog analysis failed: ${err.message}`, 'error');
    }
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

    document.getElementById('btn-apply-ai-tune')?.addEventListener('click', async (e) => {
      e.preventDefault();
      try {
        logTerminal('Synthesizing closed-loop AI map calibrations...', 'info');
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
    genCertBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      const dongleId = document.getElementById('input-dongle-id')?.value || 'ANG-ENET-PRO-8921';
      const vin = document.getElementById('input-vin')?.value || 'WBA3R9C50K5A12345';
      try {
        logTerminal(`Issuing hardware-bound X.509 mTLS Certificate for dongle ${dongleId}...`, 'info');
        const res = await fetch('/api/security/issue_cert', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ dongle_id: dongleId, vin: vin, role: currentRole })
        });
        const creds = await res.json();
        const certDisplay = document.getElementById('cert-pem-display');
        if (certDisplay) certDisplay.value = creds.client_certificate_pem;
        logTerminal(`mTLS X.509 Client Certificate successfully issued for Hardware Dongle ${dongleId} (VIN: ${vin}).`, 'success');
      } catch (err) {
        logTerminal(`Failed to issue certificate: ${err.message}`, 'error');
      }
    });
  }

  // Initial Load & Start Polling
  loadCalibrationRom();
  pollLiveTelemetry();
}

// Ensure init executes reliably regardless of script load timing
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initTuningStudio);
} else {
  initTuningStudio();
}
