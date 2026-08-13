"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

/**
 * Techno-cerebral hero graphic: a neural-network topology rendered as flat,
 * matte line-and-node geometry, slowly rotating in 3D. Deliberately built
 * without bloom/glow postprocessing (the brief rules it out) — depth is
 * suggested instead with plain scene fog, which fades distant nodes toward
 * the background color. Motion is a constant, slow rotation with no easing
 * curve, so it reads as mechanical rather than dreamy.
 */

const NODE_COUNT = 46;
const CONNECT_RADIUS = 1.55;
const SPHERE_RADIUS = 3.2;

// Accent ramp from the brand spec, lightest to darkest, used only on the
// 3D structure's edges and nodes.
const EDGE_COLOR = "#3d7ab5";
const NODE_COLOR = "#a8bfd1";
const NODE_COLOR_DIM = "#6b93b0";

/** Evenly distribute N points on a sphere (golden-angle spiral). */
function fibonacciSphere(count: number, radius: number): THREE.Vector3[] {
  const points: THREE.Vector3[] = [];
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i += 1) {
    const y = 1 - (i / (count - 1)) * 2;
    const radiusAtY = Math.sqrt(1 - y * y);
    const theta = goldenAngle * i;
    const x = Math.cos(theta) * radiusAtY;
    const z = Math.sin(theta) * radiusAtY;
    points.push(new THREE.Vector3(x * radius, y * radius, z * radius));
  }
  return points;
}

function buildEdgeGeometry(points: THREE.Vector3[]): THREE.BufferGeometry {
  const positions: number[] = [];
  for (let i = 0; i < points.length; i += 1) {
    for (let j = i + 1; j < points.length; j += 1) {
      const a = points[i]!;
      const b = points[j]!;
      if (a.distanceTo(b) <= CONNECT_RADIUS) {
        positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
      }
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return geometry;
}

function Network() {
  const groupRef = useRef<THREE.Group>(null);
  const points = useMemo(() => fibonacciSphere(NODE_COUNT, SPHERE_RADIUS), []);
  const edgeGeometry = useMemo(() => buildEdgeGeometry(points), [points]);

  useFrame((_, delta) => {
    if (!groupRef.current) return;
    // Constant, mechanical rotation — no easing, no bounce.
    groupRef.current.rotation.y += delta * 0.12;
    groupRef.current.rotation.x = Math.sin(Date.now() * 0.00006) * 0.15;
  });

  return (
    <group ref={groupRef}>
      <lineSegments geometry={edgeGeometry}>
        <lineBasicMaterial color={EDGE_COLOR} transparent opacity={0.55} />
      </lineSegments>
      {points.map((point, index) => (
        <mesh key={index} position={point}>
          <sphereGeometry args={[index % 5 === 0 ? 0.05 : 0.03, 12, 12]} />
          <meshBasicMaterial color={index % 5 === 0 ? NODE_COLOR : NODE_COLOR_DIM} />
        </mesh>
      ))}
    </group>
  );
}

export function NeuralNetwork3D() {
  return (
    <Canvas
      dpr={[1, 2]}
      camera={{ position: [0, 0, 7.5], fov: 45 }}
      gl={{ antialias: true, alpha: true }}
      aria-hidden="true"
    >
      {/* Fog approximates depth of field without bloom/glow postprocessing:
          nodes further from camera fade toward the page background. */}
      <fog attach="fog" args={["#1c1e22", 6, 11]} />
      <Network />
    </Canvas>
  );
}
