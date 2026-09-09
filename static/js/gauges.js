/**
 * High-Performance Low-Latency Canvas Telematics Gauges - BMW M-Performance Edition.
 * Analog Dials & Digital Indicators for Engine RPM, Boost (PSI/bar), AFR/Lambda,
 * Ignition Timing, Multi-Cylinder Knock Retard, WGDC, M Dynamic Shift Lights, and Live Power (HP/Nm).
 */

class TelematicsGauges {
  constructor() {
    this.rpmCanvas = document.getElementById('gauge-rpm');
    this.boostCanvas = document.getElementById('gauge-boost');
    this.afrCanvas = document.getElementById('gauge-afr');
    this.timingCanvas = document.getElementById('gauge-timing-knock');

    this.rpmCtx = this.rpmCanvas ? this.rpmCanvas.getContext('2d') : null;
    this.boostCtx = this.boostCanvas ? this.boostCanvas.getContext('2d') : null;
    this.afrCtx = this.afrCanvas ? this.afrCanvas.getContext('2d') : null;
    this.timingCtx = this.timingCanvas ? this.timingCanvas.getContext('2d') : null;

    // Smooth value interpolation
    this.curRpm = 750;
    this.curBoost = 0.0;
    this.curAfr = 14.7;
    this.curLambda = 1.0;
    this.peakBoost = 0.0;

    this.curTiming = [15.0, 15.0, 15.0, 15.0, 15.0, 15.0];
    this.curKnock = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0];

    this._initCanvasSizes();
    window.addEventListener('resize', () => this._initCanvasSizes());
  }

  _initCanvasSizes() {
    const resize = (c) => {
      if (!c) return;
      const rect = c.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      c.width = (rect.width || 260) * dpr;
      c.height = (rect.height || 260) * dpr;
    };
    resize(this.rpmCanvas);
    resize(this.boostCanvas);
    resize(this.afrCanvas);
    resize(this.timingCanvas);
  }

  update(snap) {
    if (!snap) return;
    this.curRpm += (snap.rpm - this.curRpm) * 0.35;
    this.curBoost += (snap.boost_actual_psi - this.curBoost) * 0.35;
    if (this.curBoost > this.peakBoost) this.peakBoost = this.curBoost;
    this.curAfr += (snap.afr_actual - this.curAfr) * 0.35;
    this.curLambda += (snap.lambda_actual - this.curLambda) * 0.35;

    if (snap.ignition_timing) this.curTiming = snap.ignition_timing;
    if (snap.knock_retard) this.curKnock = snap.knock_retard;

    // Update M Shift Lights
    this._updateShiftLights(this.curRpm);

    // Update Live HP / Torque
    this._updateDynoMetrics(snap);

    this.render();
  }

  _updateShiftLights(rpm) {
    const leds = document.querySelectorAll('.shift-led');
    if (!leds || leds.length === 0) return;

    // 10 LEDs: 0-3 Green (5000-6000), 4-7 Yellow (6000-7000), 8-9 Red (>7000)
    const thresholdStart = 4800;
    const thresholdMax = 7400;
    const norm = Math.max(0, Math.min(1, (rpm - thresholdStart) / (thresholdMax - thresholdStart)));
    const activeCount = Math.floor(norm * leds.length);

    leds.forEach((led, idx) => {
      if (idx < activeCount) {
        led.classList.add('active');
      } else {
        led.classList.remove('active');
      }
    });
  }

  _updateDynoMetrics(snap) {
    // Calculate estimated flywheel horsepower & torque (Nm)
    const th = snap.pedal_pct || 0;
    const boostPsi = Math.max(0, snap.boost_actual_psi || 0);
    const rpm = snap.rpm || 750;

    let estTorqueNm = 120.0;
    if (th > 10.0) {
      estTorqueNm = 200.0 + (th / 100.0) * 280.0 + (boostPsi * 14.5);
      if (rpm > 6200) estTorqueNm -= (rpm - 6200) * 0.08;
    }
    const estHp = Math.max(15.0, (rpm * estTorqueNm) / 7127.0);

    const hpEl = document.getElementById('live-dyno-hp');
    const tqEl = document.getElementById('live-dyno-tq');
    if (hpEl) hpEl.textContent = `${Math.round(estHp)} HP`;
    if (tqEl) tqEl.textContent = `${Math.round(estTorqueNm)} Nm`;
  }

  render() {
    this._renderRpmGauge();
    this._renderBoostGauge();
    this._renderAfrGauge();
    this._renderTimingKnockGauge();
  }

  _renderRpmGauge() {
    if (!this.rpmCtx || !this.rpmCanvas) return;
    const ctx = this.rpmCtx;
    const w = this.rpmCanvas.width, h = this.rpmCanvas.height;
    const cx = w / 2, cy = h / 2, r = Math.min(w, h) * 0.42;

    ctx.clearRect(0, 0, w, h);

    // Bezel
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fillStyle = '#0b0f16';
    ctx.fill();
    ctx.strokeStyle = '#21293a';
    ctx.lineWidth = 4 * window.devicePixelRatio;
    ctx.stroke();

    // Scale Track (0 to 8000 RPM)
    const startAngle = Math.PI * 0.75;
    const endAngle = Math.PI * 2.25;

    // Normal zone (0 - 6800) - BMW M Blue
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.85, startAngle, startAngle + (endAngle - startAngle) * (6800 / 8000));
    ctx.strokeStyle = '#0066b1';
    ctx.lineWidth = 6 * window.devicePixelRatio;
    ctx.stroke();

    // Redline zone (6800 - 8000) - BMW M Red
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.85, startAngle + (endAngle - startAngle) * (6800 / 8000), endAngle);
    ctx.strokeStyle = '#e60000';
    ctx.lineWidth = 8 * window.devicePixelRatio;
    ctx.shadowColor = '#e60000';
    ctx.shadowBlur = 8;
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Ticks & Numbers
    for (let rpm = 0; rpm <= 8000; rpm += 1000) {
      const angle = startAngle + (endAngle - startAngle) * (rpm / 8000);
      const isRed = rpm >= 7000;
      const tLen = (rpm % 2000 === 0) ? 14 : 8;

      const x1 = cx + Math.cos(angle) * (r * 0.85);
      const y1 = cy + Math.sin(angle) * (r * 0.85);
      const x2 = cx + Math.cos(angle) * (r * 0.85 - tLen * window.devicePixelRatio);
      const y2 = cy + Math.sin(angle) * (r * 0.85 - tLen * window.devicePixelRatio);

      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.strokeStyle = isRed ? '#e60000' : '#94a3b8';
      ctx.lineWidth = 2 * window.devicePixelRatio;
      ctx.stroke();

      if (rpm % 1000 === 0) {
        const tx = cx + Math.cos(angle) * (r * 0.65);
        const ty = cy + Math.sin(angle) * (r * 0.65);
        ctx.fillStyle = isRed ? '#ff4d4d' : '#f8fafc';
        ctx.font = `bold ${11 * window.devicePixelRatio}px Inter, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText((rpm / 1000).toString(), tx, ty);
      }
    }

    // M Logo in Gauge Center
    ctx.fillStyle = '#64748b';
    ctx.font = `italic 900 ${12 * window.devicePixelRatio}px Inter, sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText('///M POWER', cx, cy - r * 0.28);

    // Needle
    const needleAngle = startAngle + (endAngle - startAngle) * (Math.min(8000, Math.max(0, this.curRpm)) / 8000);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(needleAngle) * (r * 0.82), cy + Math.sin(needleAngle) * (r * 0.82));
    ctx.strokeStyle = '#e60000';
    ctx.lineWidth = 3.5 * window.devicePixelRatio;
    ctx.shadowColor = '#e60000';
    ctx.shadowBlur = 12;
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Center Cap
    ctx.beginPath();
    ctx.arc(cx, cy, 8 * window.devicePixelRatio, 0, Math.PI * 2);
    ctx.fillStyle = '#f8fafc';
    ctx.fill();

    // Digital Readout
    ctx.fillStyle = '#fff';
    ctx.font = `bold ${20 * window.devicePixelRatio}px var(--font-mono), monospace`;
    ctx.textAlign = 'center';
    ctx.fillText(Math.round(this.curRpm).toString(), cx, cy + r * 0.42);
    ctx.font = `${9 * window.devicePixelRatio}px Inter, sans-serif`;
    ctx.fillStyle = '#94a3b8';
    ctx.fillText('ENGINE RPM', cx, cy + r * 0.58);
  }

  _renderBoostGauge() {
    if (!this.boostCtx || !this.boostCanvas) return;
    const ctx = this.boostCtx;
    const w = this.boostCanvas.width, h = this.boostCanvas.height;
    const cx = w / 2, cy = h / 2, r = Math.min(w, h) * 0.42;

    ctx.clearRect(0, 0, w, h);

    // Bezel
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fillStyle = '#0b0f16';
    ctx.fill();
    ctx.strokeStyle = '#21293a';
    ctx.lineWidth = 4 * window.devicePixelRatio;
    ctx.stroke();

    const startAngle = Math.PI * 0.75;
    const endAngle = Math.PI * 2.25;

    // Track (-15 PSI to +35 PSI)
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.85, startAngle, endAngle);
    ctx.strokeStyle = '#1a2232';
    ctx.lineWidth = 6 * window.devicePixelRatio;
    ctx.stroke();

    // Active Boost Glow Track
    const boostNorm = Math.min(1.0, Math.max(0.0, (this.curBoost + 15) / 50));
    const activeEnd = startAngle + (endAngle - startAngle) * boostNorm;

    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.85, startAngle, activeEnd);
    ctx.strokeStyle = this.curBoost > 22 ? '#e60000' : (this.curBoost > 15 ? '#ffd600' : '#00e5ff');
    ctx.lineWidth = 6 * window.devicePixelRatio;
    ctx.shadowColor = ctx.strokeStyle;
    ctx.shadowBlur = 10;
    ctx.stroke();
    ctx.shadowBlur = 0;

    // M TwinPower Turbo Label
    ctx.fillStyle = '#00e5ff';
    ctx.font = `italic 800 ${10 * window.devicePixelRatio}px Inter, sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText('TWINPOWER TURBO', cx, cy - r * 0.28);

    // Needle
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(activeEnd) * (r * 0.82), cy + Math.sin(activeEnd) * (r * 0.82));
    ctx.strokeStyle = '#00e5ff';
    ctx.lineWidth = 3 * window.devicePixelRatio;
    ctx.stroke();

    // Peak Hold Marker
    const peakNorm = Math.min(1.0, Math.max(0.0, (this.peakBoost + 15) / 50));
    const peakAngle = startAngle + (endAngle - startAngle) * peakNorm;
    ctx.beginPath();
    ctx.arc(cx + Math.cos(peakAngle) * (r * 0.85), cy + Math.sin(peakAngle) * (r * 0.85), 4 * window.devicePixelRatio, 0, Math.PI * 2);
    ctx.fillStyle = '#ffd600';
    ctx.fill();

    // Digital Readout
    ctx.fillStyle = '#fff';
    ctx.font = `bold ${21 * window.devicePixelRatio}px var(--font-mono), monospace`;
    ctx.textAlign = 'center';
    ctx.fillText(`${this.curBoost >= 0 ? '+' : ''}${this.curBoost.toFixed(1)}`, cx, cy + r * 0.35);
    ctx.font = `${9 * window.devicePixelRatio}px Inter, sans-serif`;
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(`PSI BOOST (PEAK ${this.peakBoost.toFixed(1)})`, cx, cy + r * 0.55);
  }

  _renderAfrGauge() {
    if (!this.afrCtx || !this.afrCanvas) return;
    const ctx = this.afrCtx;
    const w = this.afrCanvas.width, h = this.afrCanvas.height;
    const cx = w / 2, cy = h / 2, r = Math.min(w, h) * 0.42;

    ctx.clearRect(0, 0, w, h);

    // Bezel
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fillStyle = '#0b0f16';
    ctx.fill();
    ctx.strokeStyle = '#21293a';
    ctx.lineWidth = 4 * window.devicePixelRatio;
    ctx.stroke();

    const startAngle = Math.PI * 0.75;
    const endAngle = Math.PI * 2.25;

    // Colormap track (Rich blue -> Stoch green -> Lean red)
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.85, startAngle, startAngle + (endAngle - startAngle) * 0.4);
    ctx.strokeStyle = '#0066b1';
    ctx.lineWidth = 6 * window.devicePixelRatio;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.85, startAngle + (endAngle - startAngle) * 0.4, startAngle + (endAngle - startAngle) * 0.7);
    ctx.strokeStyle = '#00e676';
    ctx.lineWidth = 6 * window.devicePixelRatio;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.85, startAngle + (endAngle - startAngle) * 0.7, endAngle);
    ctx.strokeStyle = '#e60000';
    ctx.lineWidth = 6 * window.devicePixelRatio;
    ctx.stroke();

    // Needle (10 to 19 AFR)
    const afrNorm = Math.min(1.0, Math.max(0.0, (this.curAfr - 10.0) / 9.0));
    const needleAngle = startAngle + (endAngle - startAngle) * afrNorm;

    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(needleAngle) * (r * 0.82), cy + Math.sin(needleAngle) * (r * 0.82));
    ctx.strokeStyle = '#00e676';
    ctx.lineWidth = 3 * window.devicePixelRatio;
    ctx.stroke();

    // Readout
    ctx.fillStyle = '#fff';
    ctx.font = `bold ${20 * window.devicePixelRatio}px var(--font-mono), monospace`;
    ctx.textAlign = 'center';
    ctx.fillText(this.curAfr.toFixed(2), cx, cy + r * 0.35);
    ctx.font = `${9 * window.devicePixelRatio}px Inter, sans-serif`;
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(`AIR-FUEL RATIO (λ ${this.curLambda.toFixed(3)})`, cx, cy + r * 0.55);
  }

  _renderTimingKnockGauge() {
    if (!this.timingCtx || !this.timingCanvas) return;
    const ctx = this.timingCtx;
    const w = this.timingCanvas.width, h = this.timingCanvas.height;

    ctx.clearRect(0, 0, w, h);

    // Title
    ctx.fillStyle = '#94a3b8';
    ctx.font = `bold ${10 * window.devicePixelRatio}px Inter, sans-serif`;
    ctx.textAlign = 'left';
    ctx.fillText('6-CYL TIMING ADVANCE (°BTDC) & KNOCK RETARD', 12 * window.devicePixelRatio, 18 * window.devicePixelRatio);

    const barW = (w - 40 * window.devicePixelRatio) / 6;
    const baseY = h * 0.55;

    for (let c = 0; c < 6; c++) {
      const x = 20 * window.devicePixelRatio + c * barW;
      const tVal = this.curTiming[c] || 0;
      const kVal = this.curKnock[c] || 0;

      // Timing Advance Cyan Bar (Upper)
      const tHeight = Math.min(60, Math.max(0, tVal * 2.5)) * window.devicePixelRatio;
      ctx.fillStyle = '#00e5ff';
      ctx.fillRect(x + 4, baseY - tHeight, barW - 8, tHeight);

      // Knock Retard Red Bar (Lower)
      const kHeight = Math.min(45, kVal * 12) * window.devicePixelRatio;
      ctx.fillStyle = kVal > 3.0 ? '#e60000' : (kVal > 1.0 ? '#ffd600' : '#1e293b');
      ctx.fillRect(x + 4, baseY + 2, barW - 8, Math.max(4, kHeight));

      // Labels
      ctx.fillStyle = '#fff';
      ctx.font = `${9 * window.devicePixelRatio}px var(--font-mono), monospace`;
      ctx.textAlign = 'center';
      ctx.fillText(`${tVal.toFixed(0)}°`, x + barW / 2, baseY - tHeight - 4);

      if (kVal > 0) {
        ctx.fillStyle = '#ff4d4d';
        ctx.fillText(`-${kVal.toFixed(1)}°`, x + barW / 2, baseY + kHeight + 12);
      }

      ctx.fillStyle = '#64748b';
      ctx.fillText(`C${c+1}`, x + barW / 2, h - 8 * window.devicePixelRatio);
    }
  }
}

window.TelematicsGauges = TelematicsGauges;
