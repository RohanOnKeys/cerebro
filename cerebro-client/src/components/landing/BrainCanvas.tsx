"use client";

import { useEffect, useRef } from "react";

/**
 * Ported from the approved Cerebro hero design: a folded fibonacci-sphere
 * point cloud, k-nearest-neighbor wired into edges, rotating at a constant
 * mechanical rate. Scrolling the hero out of view sweeps a glow band across
 * the sphere (left to right in normalized x), independent of rotation.
 */

interface Point3D {
  x: number;
  y: number;
  z: number;
  nx: number;
}

const NODE_COUNT = 210;
const GLOW_BAND = 0.22;
const ROTATION_SPEED = 1;

function buildGeometry(): { points: Point3D[]; edges: [number, number][] } {
  const golden = Math.PI * (3 - Math.sqrt(5));
  const points: Point3D[] = [];

  for (let i = 0; i < NODE_COUNT; i++) {
    const yv = 1 - (i / (NODE_COUNT - 1)) * 2;
    const radius = Math.sqrt(Math.max(0, 1 - yv * yv));
    const theta = golden * i;
    let x = Math.cos(theta) * radius;
    let z = Math.sin(theta) * radius;
    let y = yv;
    const fold = Math.sin(theta * 3 + y * 4) * 0.06 + Math.sin(y * 8) * 0.04;
    const r = 1 + fold;
    x *= r;
    y *= r;
    z *= r;
    x *= 1.35;
    y *= 0.95;
    z *= 1.05;
    points.push({ x, y, z, nx: 0 });
  }

  const edges: [number, number][] = [];
  for (let i = 0; i < NODE_COUNT; i++) {
    const dists: [number, number][] = [];
    for (let j = 0; j < NODE_COUNT; j++) {
      if (i === j) continue;
      const dx = points[i]!.x - points[j]!.x;
      const dy = points[i]!.y - points[j]!.y;
      const dz = points[i]!.z - points[j]!.z;
      dists.push([j, dx * dx + dy * dy + dz * dz]);
    }
    dists.sort((a, b) => a[1] - b[1]);
    for (let k = 0; k < 3; k++) {
      const j = dists[k]![0];
      edges.push(j > i ? [i, j] : [j, i]);
    }
  }
  const seen = new Set<string>();
  const dedupedEdges = edges.filter(([a, b]) => {
    const key = `${a}_${b}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  let minX = Infinity;
  let maxX = -Infinity;
  points.forEach((p) => {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
  });
  points.forEach((p) => {
    p.nx = (p.x - minX) / (maxX - minX);
  });

  return { points, edges: dedupedEdges };
}

export function BrainCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const { points, edges } = buildGeometry();
    let w = 0;
    let h = 0;
    let angle = 0;
    let scrollProgress = 0;
    let raf = 0;

    const resize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      const dpr = window.devicePixelRatio || 1;
      w = parent.offsetWidth;
      h = parent.offsetHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const handleScroll = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      const heroH = parent.offsetHeight || window.innerHeight;
      scrollProgress = Math.min(1, Math.max(0, window.scrollY / heroH));
    };

    const draw = () => {
      if (!w) {
        raf = requestAnimationFrame(draw);
        return;
      }
      ctx.clearRect(0, 0, w, h);
      angle += 0.0016 * ROTATION_SPEED;
      const tilt = 0.34;
      const cosA = Math.cos(angle);
      const sinA = Math.sin(angle);
      const cosT = Math.cos(tilt);
      const sinT = Math.sin(tilt);
      const focal = 720;
      const scaleBase = Math.min(w, h) * 0.36;
      const cx = w * 0.64;
      const cy = h * 0.5;
      const wipe = scrollProgress * (1 + GLOW_BAND * 2) - GLOW_BAND;

      const projected = points.map((p) => {
        const x = p.x * cosA + p.z * sinA;
        const z = -p.x * sinA + p.z * cosA;
        const y2 = p.y * cosT - z * sinT;
        const z2 = p.y * sinT + z * cosT;
        const scale = focal / (focal + z2 * scaleBase * 0.6);
        const sx = cx + x * scaleBase * scale;
        const sy = cy + y2 * scaleBase * scale;
        const dist = Math.abs(wipe - p.nx);
        const glow = Math.max(0, 1 - dist / GLOW_BAND);
        const activated = scrollProgress > p.nx ? 0.35 : 0;
        return { sx, sy, litLevel: Math.max(glow, activated) };
      });

      edges.forEach(([i, j]) => {
        const a = projected[i]!;
        const b = projected[j]!;
        const lit = Math.max(a.litLevel, b.litLevel);
        const alpha = 0.14 + lit * 0.6;
        const r = 61 + (168 - 61) * lit;
        const g = 122 + (191 - 122) * lit;
        const bl = 181 + (209 - 181) * lit;
        ctx.strokeStyle = `rgba(${r | 0},${g | 0},${bl | 0},${alpha})`;
        ctx.lineWidth = 1;
        ctx.shadowBlur = lit > 0.4 ? 8 * lit : 0;
        ctx.shadowColor = "rgba(168,191,209,0.8)";
        ctx.beginPath();
        ctx.moveTo(a.sx, a.sy);
        ctx.lineTo(b.sx, b.sy);
        ctx.stroke();
      });

      ctx.shadowBlur = 0;
      projected.forEach((p) => {
        const lit = p.litLevel;
        const rad = 1.3 + lit * 1.7;
        ctx.beginPath();
        ctx.fillStyle = lit > 0.05 ? `rgba(202,217,228,${0.5 + lit * 0.5})` : "rgba(107,147,176,0.55)";
        ctx.shadowBlur = lit > 0.3 ? 10 * lit : 0;
        ctx.shadowColor = "rgba(202,222,236,0.9)";
        ctx.arc(p.sx, p.sy, rad, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.shadowBlur = 0;

      raf = requestAnimationFrame(draw);
    };

    resize();
    handleScroll();
    window.addEventListener("resize", resize);
    window.addEventListener("scroll", handleScroll, { passive: true });
    raf = requestAnimationFrame(draw);

    return () => {
      window.removeEventListener("resize", resize);
      window.removeEventListener("scroll", handleScroll);
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 block h-full w-full"
      aria-hidden="true"
    />
  );
}
