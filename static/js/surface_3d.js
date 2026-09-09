/**
 * Pure WebGL / Canvas 3D Engine Map Surface Visualizer.
 * Renders interactive 3D surface meshes, colormaps, wireframes, and allows cell picking.
 */

class SurfaceVisualizer3D {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    
    this.tableData = null;
    this.rotX = 0.55; // Pitch
    this.rotY = -0.75; // Yaw
    this.zoom = 1.0;
    this.panX = 0;
    this.panY = 0;
    
    this.isDragging = false;
    this.isPanning = false;
    this.lastMouseX = 0;
    this.lastMouseY = 0;
    
    this.selectedCell = { x: 0, y: 0 };
    this.onCellSelectedCallback = null;
    
    this._initEvents();
    this._resizeCanvas();
    window.addEventListener('resize', () => this._resizeCanvas());
  }

  _resizeCanvas() {
    if (!this.canvas) return;
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.canvas.width = rect.width * window.devicePixelRatio || 800;
    this.canvas.height = (rect.height || 520) * window.devicePixelRatio;
    this.render();
  }

  _initEvents() {
    this.canvas.addEventListener('mousedown', (e) => {
      this.isDragging = (e.button === 0 && !e.shiftKey);
      this.isPanning = (e.button === 2 || (e.button === 0 && e.shiftKey));
      this.lastMouseX = e.clientX;
      this.lastMouseY = e.clientY;
    });

    window.addEventListener('mousemove', (e) => {
      if (!this.isDragging && !this.isPanning) return;
      const dx = e.clientX - this.lastMouseX;
      const dy = e.clientY - this.lastMouseY;
      this.lastMouseX = e.clientX;
      this.lastMouseY = e.clientY;

      if (this.isDragging) {
        this.rotY += dx * 0.008;
        this.rotX = Math.max(-1.4, Math.min(1.4, this.rotX + dy * 0.008));
      } else if (this.isPanning) {
        this.panX += dx * 1.5;
        this.panY += dy * 1.5;
      }
      this.render();
    });

    window.addEventListener('mouseup', () => {
      this.isDragging = false;
      this.isPanning = false;
    });

    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;
      this.zoom = Math.max(0.4, Math.min(3.5, this.zoom * zoomFactor));
      this.render();
    }, { passive: false });

    this.canvas.addEventListener('contextmenu', e => e.preventDefault());

    // Click to pick cell
    this.canvas.addEventListener('click', (e) => {
      if (!this.tableData) return;
      const rect = this.canvas.getBoundingClientRect();
      const clickX = (e.clientX - rect.left) * window.devicePixelRatio;
      const clickY = (e.clientY - rect.top) * window.devicePixelRatio;
      this._pickCell(clickX, clickY);
    });
  }

  setData(tableData) {
    this.tableData = tableData;
    this.render();
  }

  _pickCell(px, py) {
    if (!this.tableData || !this.projectedPoints) return;
    let closestDist = Infinity;
    let closestCoord = null;

    const ny = this.tableData.matrix.length;
    const nx = this.tableData.matrix[0].length;

    for (let y = 0; y < ny; y++) {
      for (let x = 0; x < nx; x++) {
        const pt = this.projectedPoints[y][x];
        const dist = Math.hypot(pt.x - px, pt.y - py);
        if (dist < closestDist && dist < 40 * window.devicePixelRatio) {
          closestDist = dist;
          closestCoord = { x, y };
        }
      }
    }

    if (closestCoord) {
      this.selectedCell = closestCoord;
      this.render();
      if (this.onCellSelectedCallback) {
        this.onCellSelectedCallback(closestCoord.x, closestCoord.y, this.tableData.matrix[closestCoord.y][closestCoord.x]);
      }
    }
  }

  _getColor(normVal) {
    // Jet / Turbo Heat Colormap (0.0 Blue -> 0.25 Cyan -> 0.5 Green -> 0.75 Yellow -> 1.0 Red)
    const v = Math.max(0, Math.min(1, normVal));
    let r = 0, g = 0, b = 0;

    if (v < 0.25) {
      r = 0;
      g = Math.floor(v * 4 * 255);
      b = 255;
    } else if (v < 0.5) {
      r = 0;
      g = 255;
      b = Math.floor((1 - (v - 0.25) * 4) * 255);
    } else if (v < 0.75) {
      r = Math.floor((v - 0.5) * 4 * 255);
      g = 255;
      b = 0;
    } else {
      r = 255;
      g = Math.floor((1 - (v - 0.75) * 4) * 255);
      b = 0;
    }
    return `rgba(${r}, ${g}, ${b}, 0.82)`;
  }

  render() {
    if (!this.ctx || !this.tableData) return;
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;

    ctx.clearRect(0, 0, w, h);

    // Background gradient
    const bgGrad = ctx.createLinearGradient(0, 0, 0, h);
    bgGrad.addColorStop(0, '#06080c');
    bgGrad.addColorStop(1, '#0e121a');
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, w, h);

    const matrix = this.tableData.matrix;
    const ny = matrix.length;
    const nx = matrix[0].length;

    // Find Min and Max
    let minZ = Infinity, maxZ = -Infinity;
    for (let r = 0; r < ny; r++) {
      for (let c = 0; c < nx; c++) {
        const val = matrix[r][c];
        if (val < minZ) minZ = val;
        if (val > maxZ) maxZ = val;
      }
    }
    if (minZ === maxZ) maxZ += 1.0;

    // Center & Projection Transform
    const cx = w / 2 + this.panX;
    const cy = h / 2 + this.panY + 40 * window.devicePixelRatio;
    const scale = Math.min(w, h) * 0.38 * this.zoom;

    const cosX = Math.cos(this.rotX), sinX = Math.sin(this.rotX);
    const cosY = Math.cos(this.rotY), sinY = Math.sin(this.rotY);

    const project = (xNorm, yNorm, zNorm) => {
      // 3D coordinates in [-1, 1]
      const px = (xNorm - 0.5) * 2.0;
      const pz = (yNorm - 0.5) * 2.0;
      const py = -(zNorm - 0.5) * 1.6;

      // Yaw rotation (Y axis)
      const x1 = px * cosY + pz * sinY;
      const z1 = -px * sinY + pz * cosY;

      // Pitch rotation (X axis)
      const y2 = py * cosX - z1 * sinX;
      const z2 = py * sinX + z1 * cosX;

      // Perspective projection
      const cameraDist = 4.0;
      const fov = cameraDist / (cameraDist + z2);

      return {
        x: cx + x1 * scale * fov,
        y: cy + y2 * scale * fov,
        depth: z2
      };
    };

    // Calculate all 3D mesh points
    this.projectedPoints = [];
    for (let r = 0; r < ny; r++) {
      const rowPts = [];
      const yNorm = r / (ny - 1);
      for (let c = 0; c < nx; c++) {
        const xNorm = c / (nx - 1);
        const zNorm = (matrix[r][c] - minZ) / (maxZ - minZ);
        rowPts.push(project(xNorm, yNorm, zNorm));
      }
      this.projectedPoints.push(rowPts);
    }

    // Build Polygons for Depth Sorting
    const polygons = [];
    for (let r = 0; r < ny - 1; r++) {
      for (let c = 0; c < nx - 1; c++) {
        const p00 = this.projectedPoints[r][c];
        const p10 = this.projectedPoints[r][c + 1];
        const p11 = this.projectedPoints[r + 1][c + 1];
        const p01 = this.projectedPoints[r + 1][c];

        const avgDepth = (p00.depth + p10.depth + p11.depth + p01.depth) / 4;
        const avgVal = (matrix[r][c] + matrix[r][c+1] + matrix[r+1][c+1] + matrix[r+1][c]) / 4;
        const normVal = (avgVal - minZ) / (maxZ - minZ);

        polygons.push({
          pts: [p00, p10, p11, p01],
          depth: avgDepth,
          color: this._getColor(normVal),
          coord: { r, c },
          isSelected: (this.selectedCell.x === c && this.selectedCell.y === r)
        });
      }
    }

    // Sort polygons back-to-front (Painter's Algorithm)
    polygons.sort((a, b) => b.depth - a.depth);

    // Draw Surface Polygons & Wireframe
    for (const poly of polygons) {
      ctx.beginPath();
      ctx.moveTo(poly.pts[0].x, poly.pts[0].y);
      ctx.lineTo(poly.pts[1].x, poly.pts[1].y);
      ctx.lineTo(poly.pts[2].x, poly.pts[2].y);
      ctx.lineTo(poly.pts[3].x, poly.pts[3].y);
      ctx.closePath();

      ctx.fillStyle = poly.color;
      ctx.fill();

      // Wireframe overlay
      ctx.strokeStyle = poly.isSelected ? '#ffffff' : 'rgba(255, 255, 255, 0.22)';
      ctx.lineWidth = (poly.isSelected ? 2.5 : 1.0) * window.devicePixelRatio;
      ctx.stroke();

      if (poly.isSelected) {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
        ctx.fill();
      }
    }

    // Draw Selected Point Highlight
    if (this.selectedCell && this.projectedPoints[this.selectedCell.y]) {
      const pt = this.projectedPoints[this.selectedCell.y][this.selectedCell.x];
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 6 * window.devicePixelRatio, 0, Math.PI * 2);
      ctx.fillStyle = '#00e5ff';
      ctx.shadowColor = '#00e5ff';
      ctx.shadowBlur = 12;
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2 * window.devicePixelRatio;
      ctx.stroke();
    }

    // Draw Info Overlays
    ctx.fillStyle = '#94a3b8';
    ctx.font = `${11 * window.devicePixelRatio}px Inter, sans-serif`;
    ctx.fillText(`Map: ${this.tableData.name} (${this.tableData.unit})`, 16 * window.devicePixelRatio, 24 * window.devicePixelRatio);
    ctx.fillText(`Range: ${minZ.toFixed(1)} - ${maxZ.toFixed(1)} ${this.tableData.unit}`, 16 * window.devicePixelRatio, 40 * window.devicePixelRatio);
  }
}

window.SurfaceVisualizer3D = SurfaceVisualizer3D;
