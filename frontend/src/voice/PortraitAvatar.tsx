import { useEffect, useRef, type RefObject } from "react";
import * as THREE from "three";
import type { VoiceState } from "./useVoice";

/** A real person's portrait, with real depth, from a single photograph.
 *
 *  One front-facing photo contains the front of a face and nothing else - no
 *  profile, no ears, no back of the head. A full 3D head built from it would
 *  be two-thirds invention, and invented geometry on a real person's face is
 *  the thing that reads as a bad deepfake.
 *
 *  So this displaces the photo over a face-shaped depth prior and constrains
 *  rotation to a few degrees. Inside that range the parallax is genuine - the
 *  nose leads the cheeks, the cheeks lead the ears - and outside it there is
 *  nothing to show, so it never goes there.
 *
 *  His face is never animated. The consent on file covers his image, not a
 *  mouth that moves; speech drives the light and the aura around him instead.
 */
export function PortraitAvatar({
  src,
  mouth,
  state,
  accent = "#4f46e5",
  className,
}: {
  src: string;
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
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
    camera.position.set(0, 0, 4.2);

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.domElement.style.display = "block";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    mount.appendChild(renderer.domElement);

    const colour = new THREE.Color(accent);
    const group = new THREE.Group();
    scene.add(group);

    const uniforms = {
      uMap: { value: null as THREE.Texture | null },
      uTime: { value: 0 },
      uMouth: { value: 0 },
      uListening: { value: 0 },
      uColour: { value: colour },
      uReady: { value: 0 },
    };

    // --- the portrait -------------------------------------------------------
    // Densely subdivided: the displacement happens per vertex, so the mesh has
    // to be fine enough for the depth to read as a surface rather than facets.
    const geometry = new THREE.PlaneGeometry(2.1, 2.1, 180, 180);
    const material = new THREE.ShaderMaterial({
      uniforms,
      transparent: true,
      vertexShader: `
        uniform float uTime;
        uniform float uMouth;
        uniform float uReady;
        varying vec2 vUv;
        varying float vDepth;
        varying float vEdge;

        void main() {
          vUv = uv;
          vec2 centred = uv - 0.5;

          // A face-shaped depth prior: a dome over the head, taller than it is
          // wide, with the nose region standing proudest. Crude, but it is the
          // shape of the thing, and it is honest about being an approximation.
          float dome = 1.0 - clamp(
            (centred.x * centred.x) / 0.085 + (centred.y * centred.y) / 0.16, 0.0, 1.0);
          dome = sqrt(dome);

          // The centre line carries a little more relief - nose and brow.
          float ridge = exp(-(centred.x * centred.x) / 0.012) * 0.35;

          // Fade the displacement out at the frame so the plane's edge stays
          // flat and the portrait sits in the scene instead of curling off it.
          float edge = smoothstep(0.5, 0.26, length(centred * vec2(1.35, 1.0)));
          vEdge = edge;

          vDepth = (dome + ridge) * edge;
          vec3 displaced = position;
          displaced.z += vDepth * 0.5 * uReady;
          // A slow breath, and a small lift while speaking. The FACE is never
          // deformed - this moves him as a whole, the way a person shifts.
          displaced.z += sin(uTime * 0.8) * 0.012;
          displaced.y += uMouth * 0.006;

          gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
        }`,
      fragmentShader: `
        uniform sampler2D uMap;
        uniform vec3 uColour;
        uniform float uMouth;
        uniform float uListening;
        uniform float uReady;
        varying vec2 vUv;
        varying float vDepth;
        varying float vEdge;

        void main() {
          vec4 texel = texture2D(uMap, vUv);

          // Light him from the accent colour as he speaks: the room reacts,
          // not his face.
          float lift = uMouth * 0.22 + uListening * 0.10;
          vec3 colour = texel.rgb + uColour * lift * (0.35 + vDepth * 0.65);

          // A soft vignette so the rectangle of the photograph does not read
          // as a photograph pasted into the scene.
          float mask = smoothstep(0.52, 0.30, length((vUv - 0.5) * vec2(1.3, 1.0)));
          float alpha = texel.a * mask * uReady;
          if (alpha < 0.01) discard;
          gl_FragColor = vec4(colour, alpha);
        }`,
    });
    const portrait = new THREE.Mesh(geometry, material);
    group.add(portrait);

    // --- the aura: this is what reacts to speech ----------------------------
    const ringUniforms = {
      uTime: { value: 0 },
      uMouth: { value: 0 },
      uColour: { value: colour },
    };
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(1.06, 1.5, 128),
      new THREE.ShaderMaterial({
        uniforms: ringUniforms,
        transparent: true,
        side: THREE.DoubleSide,
        depthWrite: false,
        vertexShader: `
          varying vec2 vUv; varying vec3 vPos;
          void main() { vUv = uv; vPos = position;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
        fragmentShader: `
          uniform float uTime; uniform float uMouth; uniform vec3 uColour;
          varying vec3 vPos;
          void main() {
            float r = length(vPos.xy);
            float angle = atan(vPos.y, vPos.x);
            // Petals that swell with the voice.
            float wave = sin(angle * 9.0 - uTime * 1.6) * 0.5 + 0.5;
            float band = smoothstep(1.5, 1.06, r) * smoothstep(1.02, 1.12, r);
            float glow = band * (0.10 + uMouth * 0.75 * (0.45 + wave * 0.55));
            gl_FragColor = vec4(uColour, glow);
          }`,
      }),
    );
    ring.position.z = -0.25;
    group.add(ring);

    // --- texture ------------------------------------------------------------
    let disposed = false;
    new THREE.TextureLoader().load(
      src,
      (texture) => {
        if (disposed) {
          texture.dispose();
          return;
        }
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
        uniforms.uMap.value = texture;
      },
      undefined,
      () => {
        // A missing photo leaves uReady at 0 and nothing is drawn, which the
        // caller's fallback covers.
      },
    );

    // --- interaction --------------------------------------------------------
    // Parallax follows the pointer, which is what sells the depth - but only a
    // few degrees, because beyond that there is no photograph to show.
    const MAX_TILT = 0.14; // radians, ~8 degrees
    const target = { x: 0, y: 0 };
    const onPointer = (event: PointerEvent) => {
      const rect = mount.getBoundingClientRect();
      target.x = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
      target.y = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
    };
    const onLeave = () => {
      target.x = 0;
      target.y = 0;
    };
    mount.addEventListener("pointermove", onPointer);
    mount.addEventListener("pointerleave", onLeave);

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = mount;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.position.z = 4.2 * Math.max(1, 1.5 / camera.aspect);
      camera.updateProjectionMatrix();
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(mount);

    const clock = new THREE.Clock();
    let frame = 0;
    let listening = 0;
    let ready = 0;
    let tiltX = 0;
    let tiltY = 0;

    const render = () => {
      frame = requestAnimationFrame(render);
      const t = clock.getElapsedTime();
      const level = mouth.current ?? 0;

      listening += ((stateRef.current === "listening" ? 1 : 0) - listening) * 0.08;
      ready += ((uniforms.uMap.value ? 1 : 0) - ready) * 0.06;
      // Ease toward the pointer rather than tracking it exactly - a head turns,
      // it does not snap.
      tiltX += (target.x * MAX_TILT - tiltX) * 0.06;
      tiltY += (target.y * MAX_TILT - tiltY) * 0.06;

      uniforms.uTime.value = t;
      uniforms.uMouth.value = level;
      uniforms.uListening.value = listening;
      uniforms.uReady.value = ready;
      ringUniforms.uTime.value = t;
      ringUniforms.uMouth.value = level;

      // A slow drift so he is never perfectly still, plus the pointer tilt.
      group.rotation.y = tiltX + Math.sin(t * 0.25) * 0.03;
      group.rotation.x = -tiltY * 0.6 + Math.sin(t * 0.19) * 0.02;
      group.scale.setScalar(1 + level * 0.012);

      renderer.render(scene, camera);
    };
    render();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      mount.removeEventListener("pointermove", onPointer);
      mount.removeEventListener("pointerleave", onLeave);
      uniforms.uMap.value?.dispose();
      geometry.dispose();
      material.dispose();
      ring.geometry.dispose();
      (ring.material as THREE.Material).dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [accent, mouth, src]);

  return <div ref={host} className={className} aria-hidden="true" />;
}
