/**
 * High-Speed 50Hz Multi-Channel Telemetry Oscilloscope.
 * Renders smooth rolling real-time traces for RPM, Boost, AFR, Timing, and Knock Retard.
 */

class TelemetryOscilloscope {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    
    this.maxPoints = 200; // 4 seconds at 50Hz
    this.history = {
      rpm: [],
      boost_target: [],
      boost_actual: [],
      afr_actual: [],
      timing_avg: [],
      knock_max: [],
      wgdc: []
    };

    this.activeChannels = {
      boost: true,
      rpm: true,
      afr: true,
      knock: true
    };

    this.isPaused = false;
    this._resizeCanvas();
    window.addEventListener('resize', () => this._resizeCanvas());
  }

  _resizeCanvas() {
    if (!this.canvas) return;
    const parent = this.canvas.parentElement;
    const rect = parent ? parent.getBoundingClientRect() : { width: 800, height: 260 };
    const dpr = window.devicePixelRatio || 1;
    const w = (rect.width > 20) ? rect.width : 800;
    const h = (rect.height > 20) ? rect.height : 260;
    this.canvas.width = w * dpr;
    this.canvas.height = h * dpr;
    this.render();
  }

  addPoint(snap) {
    if (this.isPaused || !snap) return;

    const push = (arr, val) => {
      arr.push(val);
      if (arr.length > this.maxPoints) arr.shift();
    };

    push(this.history.rpm, snap.rpm || 0);
    push(this.history.boost_target, snap.boost_target_psi || 0);
    push(this.history.boost_actual, snap.boost_actual_psi || 0);
    push(this.history.afr_actual, snap.afr_actual || 14.7);
    push(this.history.wgdc, snap.wgdc || 0);

    const timingAvg = snap.ignition_timing ? (snap.ignition_timing.reduce((a, b) => a + b, 0) / snap.ignition_timing.length) : 15.0;
    push(this.history.timing_avg, timingAvg);

    const maxKnock = snap.knock_retard ? Math.max(...snap.knock_retard) : 0.0;
    push(this.history.knock_max, maxKnock);

    this.render();
  }

  render() {
    if (!this.ctx || !this.canvas) return;
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;
    if (w <= 0 || h <= 0) return;
    const dpr = window.devicePixelRatio || 1;

    ctx.clearRect(0, 0, w, h);

    // Grid Background
    ctx.fillStyle = '#0a0d14';
    ctx.fillRect(0, 0, w, h);

    // Grid Lines
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1 * dpr;
    for (let y = 0; y <= 4; y++) {
      const gy = (h / 4) * y;
      ctx.beginPath();
      ctx.moveTo(0, gy);
      ctx.lineTo(w, gy);
      ctx.stroke();
    }
    for (let x = 0; x <= 8; x++) {
      const gx = (w / 8) * x;
      ctx.beginPath();
      ctx.moveTo(gx, 0);
      ctx.lineTo(gx, h);
      ctx.stroke();
    }

    const n = this.history.boost_actual.length;
    if (n < 2) return;

    const getX = (idx) => (idx / (this.maxPoints - 1)) * w;

    // 1. Boost Target & Actual (-5 PSI to +30 PSI -> [h, 0])
    if (this.activeChannels.boost) {
      // Boost Target (Dashed Blue)
      ctx.beginPath();
      ctx.setLineDash([4 * dpr, 4 * dpr]);
      for (let i = 0; i < n; i++) {
        const val = this.history.boost_target[i];
        const norm = Math.max(0, Math.min(1, (val + 5) / 35));
        const py = h - norm * (h - 20 * dpr) - 10 * dpr;
        if (i === 0) ctx.moveTo(getX(i), py);
        else ctx.lineTo(getX(i), py);
      }
      ctx.strokeStyle = 'rgba(0, 229, 255, 0.5)';
      ctx.lineWidth = 1.5 * dpr;
      ctx.stroke();
      ctx.setLineDash([]);

      // Boost Actual (Solid Bright Cyan)
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const val = this.history.boost_actual[i];
        const norm = Math.max(0, Math.min(1, (val + 5) / 35));
        const py = h - norm * (h - 20 * dpr) - 10 * dpr;
        if (i === 0) ctx.moveTo(getX(i), py);
        else ctx.lineTo(getX(i), py);
      }
      ctx.strokeStyle = '#00e5ff';
      ctx.lineWidth = 2.5 * dpr;
      ctx.shadowColor = '#00e5ff';
      ctx.shadowBlur = 6;
      ctx.stroke();
      ctx.shadowBlur = 0;
    }

    // 2. Engine RPM (0 to 8000 RPM)
    if (this.activeChannels.rpm) {
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const val = this.history.rpm[i];
        const norm = Math.max(0, Math.min(1, val / 8000));
        const py = h - norm * (h - 20 * dpr) - 10 * dpr;
        if (i === 0) ctx.moveTo(getX(i), py);
        else ctx.lineTo(getX(i), py);
      }
      ctx.strokeStyle = '#ffd600';
      ctx.lineWidth = 2.0 * dpr;
      ctx.stroke();
    }

    // 3. AFR / Lambda (10.0 to 18.0 AFR)
    if (this.activeChannels.afr) {
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const val = this.history.afr_actual[i];
        const norm = Math.max(0, Math.min(1, (val - 10) / 8));
        const py = h - norm * (h - 20 * dpr) - 10 * dpr;
        if (i === 0) ctx.moveTo(getX(i), py);
        else ctx.lineTo(getX(i), py);
      }
      ctx.strokeStyle = '#00e676';
      ctx.lineWidth = 2.0 * dpr;
      ctx.stroke();
    }

    // 4. Knock Retard Spike (0.0 to 6.0 deg)
    if (this.activeChannels.knock) {
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const val = this.history.knock_max[i];
        const norm = Math.max(0, Math.min(1, val / 6.0));
        const py = h - norm * (h - 20 * dpr) - 10 * dpr;
        if (i === 0) ctx.moveTo(getX(i), py);
        else ctx.lineTo(getX(i), py);
      }
      ctx.strokeStyle = '#e60000';
      ctx.lineWidth = 2.5 * dpr;
      ctx.shadowColor = '#e60000';
      ctx.shadowBlur = 8;
      ctx.stroke();
      ctx.shadowBlur = 0;
    }
  }
}

window.TelemetryOscilloscope = TelemetryOscilloscope;
