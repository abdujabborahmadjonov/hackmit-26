import { useEffect, useRef, type RefObject } from "react";
import * as THREE from "three";
import type { VoiceState } from "./useVoice";

/** The persona's presence, as an abstract form.
 *
 *  Deliberately not a face. A synthesised likeness of a real educator needs
 *  their permission, and a generic human head would be worse than useless -
 *  it would sit in the uncanny valley while still implying a person. This
 *  reads as an interface that is listening or talking, which is what it is.
 *
 *  The core is an icosahedron displaced in the vertex shader by layered noise.
 *  `mouth` is a ref rather than a prop so speech can drive it every frame
 *  without re-rendering React.
 */
export function Avatar3D({
  mouth,
  state,
  accent = "#4f46e5",
  className,
}: {
  mouth: RefObject<number>;
  state: VoiceState;
  accent?: string;
  className?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    const mount = host.current;
    if (!mount) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    camera.position.set(0, 0, 4.4);

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      return; // No WebGL: the caller's fallback stays on screen.
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    // Without an explicit CSS size the canvas stays at its 300x150 default
    // and the scene is stretched and off-centre.
    renderer.domElement.style.display = "block";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    mount.appendChild(renderer.domElement);

    const colour = new THREE.Color(accent);
    const uniforms = {
      uTime: { value: 0 },
      uMouth: { value: 0 },
      uListening: { value: 0 },
      uColour: { value: colour },
    };

    // --- the core -----------------------------------------------------------
    const geometry = new THREE.IcosahedronGeometry(1, 64);
    const material = new THREE.ShaderMaterial({
      uniforms,
      transparent: true,
      vertexShader: `
        uniform float uTime;
        uniform float uMouth;
        uniform float uListening;
        varying float vDisplace;
        varying vec3 vNormal;

        // Cheap value noise - enough for an organic wobble, no texture needed.
        vec3 hash3(vec3 p) {
          p = vec3(dot(p, vec3(127.1, 311.7, 74.7)),
                   dot(p, vec3(269.5, 183.3, 246.1)),
                   dot(p, vec3(113.5, 271.9, 124.6)));
          return -1.0 + 2.0 * fract(sin(p) * 43758.5453123);
        }
        float noise(vec3 p) {
          vec3 i = floor(p), f = fract(p);
          vec3 u = f * f * (3.0 - 2.0 * f);
          return mix(mix(mix(dot(hash3(i + vec3(0,0,0)), f - vec3(0,0,0)),
                             dot(hash3(i + vec3(1,0,0)), f - vec3(1,0,0)), u.x),
                         mix(dot(hash3(i + vec3(0,1,0)), f - vec3(0,1,0)),
                             dot(hash3(i + vec3(1,1,0)), f - vec3(1,1,0)), u.x), u.y),
                     mix(mix(dot(hash3(i + vec3(0,0,1)), f - vec3(0,0,1)),
                             dot(hash3(i + vec3(1,0,1)), f - vec3(1,0,1)), u.x),
                         mix(dot(hash3(i + vec3(0,1,1)), f - vec3(0,1,1)),
                             dot(hash3(i + vec3(1,1,1)), f - vec3(1,1,1)), u.x), u.y), u.z);
        }

        void main() {
          vNormal = normal;
          // A slow breath at rest; speech rides on top of it.
          float breath = 0.035 * sin(uTime * 0.9);
          float speech = uMouth * 0.34 * noise(normal * 2.6 + uTime * 2.2);
          float attention = uListening * 0.05 * noise(normal * 5.0 + uTime * 3.4);
          vDisplace = breath + speech + attention;
          vec3 displaced = position * (1.0 + vDisplace);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
        }`,
      fragmentShader: `
        uniform vec3 uColour;
        uniform float uMouth;
        varying float vDisplace;
        varying vec3 vNormal;
        void main() {
          // Rim light: bright where the surface turns away from the camera.
          float rim = pow(1.0 - abs(dot(normalize(vNormal), vec3(0.0, 0.0, 1.0))), 2.2);
          vec3 lit = uColour * (0.30 + rim * 1.5 + vDisplace * 2.2 + uMouth * 0.30);
          gl_FragColor = vec4(lit, 0.34 + rim * 0.66);
        }`,
    });
    const core = new THREE.Mesh(geometry, material);
    scene.add(core);

    // --- wireframe shell ----------------------------------------------------
    const shell = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1.42, 2),
      new THREE.MeshBasicMaterial({ color: colour, wireframe: true, transparent: true, opacity: 0.16 }),
    );
    scene.add(shell);

    // --- orbiting ring ------------------------------------------------------
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(1.85, 0.008, 8, 160),
      new THREE.MeshBasicMaterial({ color: colour, transparent: true, opacity: 0.5 }),
    );
    ring.rotation.x = Math.PI * 0.42;
    scene.add(ring);

    // --- resize -------------------------------------------------------------
    const resize = () => {
      const { clientWidth: w, clientHeight: h } = mount;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      // Keep the whole form in frame on a wide, short canvas: widen the
      // view by pulling back when the aspect gets extreme.
      camera.position.z = 4.4 * Math.max(1, 1.7 / camera.aspect);
      camera.updateProjectionMatrix();
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(mount);

    // --- loop ---------------------------------------------------------------
    const clock = new THREE.Clock();
    let frame = 0;
    let listening = 0;

    const render = () => {
      frame = requestAnimationFrame(render);
      const t = clock.getElapsedTime();

      const target = stateRef.current === "listening" ? 1 : 0;
      listening += (target - listening) * 0.08;

      uniforms.uTime.value = t;
      uniforms.uMouth.value = mouth.current ?? 0;
      uniforms.uListening.value = listening;

      core.rotation.y = t * 0.16;
      core.rotation.x = Math.sin(t * 0.22) * 0.12;
      shell.rotation.y = -t * 0.09;
      shell.rotation.z = t * 0.05;
      ring.rotation.z = t * 0.34;
      // Thinking reads as a slow lean-in rather than a spinner.
      const scale = stateRef.current === "thinking" ? 0.94 + Math.sin(t * 3.0) * 0.03 : 1;
      core.scale.setScalar(scale);

      renderer.render(scene, camera);
    };
    render();

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      geometry.dispose();
      material.dispose();
      shell.geometry.dispose();
      (shell.material as THREE.Material).dispose();
      ring.geometry.dispose();
      (ring.material as THREE.Material).dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [accent, mouth]);

  return <div ref={host} className={className} aria-hidden="true" />;
}
