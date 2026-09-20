import { useEffect, useRef, type RefObject } from "react";
import * as THREE from "three";
import type { VoiceState } from "./useVoice";

/** A rigged character that talks, looks and gestures.
 *
 *  Deliberately nobody. It has a jaw that opens, eyes that blink and track,
 *  and hands that move while it speaks - all the things a likeness would need
 *  permission for, on a figure that is not a likeness of anyone. Stylised on
 *  purpose: an attempt at a real face would land in the uncanny valley, and an
 *  attempt at a *specific* real face would need that person's agreement to be
 *  animated at all.
 *
 *  The jaw is driven by `mouth`, which with hosted speech is the real audio
 *  waveform - so it opens on the sounds rather than on a timer.
 */
export function CharacterAvatar({
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
    const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 100);
    // Centred on the figure's mid-point, not on the origin: the hands hang
    // well below it and were being cropped off the bottom of the frame.
    camera.position.set(0, -0.6, 5.4);

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

    // --- light ---------------------------------------------------------------
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 1.5);
    key.position.set(2.5, 3.5, 4);
    scene.add(key);
    const rim = new THREE.PointLight(colour, 28, 14);
    rim.position.set(-2.6, 1.4, -2.2);
    scene.add(rim);
    // Lifts the underside so the jaw reads when it opens.
    const fill = new THREE.PointLight(colour.clone().offsetHSL(0, 0, 0.18), 8, 10);
    fill.position.set(0, -1.6, 2.4);
    scene.add(fill);

    // --- materials -----------------------------------------------------------
    const skin = new THREE.MeshStandardMaterial({
      color: 0xd9dcf2,
      roughness: 0.55,
      metalness: 0.08,
    });
    const cloth = new THREE.MeshStandardMaterial({
      color: colour.clone().multiplyScalar(0.55),
      roughness: 0.85,
      metalness: 0.02,
    });
    const dark = new THREE.MeshStandardMaterial({ color: 0x1b1d2b, roughness: 0.35 });
    const gloss = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      roughness: 0.1,
      metalness: 0.0,
    });

    const figure = new THREE.Group();
    figure.position.y = -0.3;
    figure.scale.setScalar(0.92);
    scene.add(figure);

    // --- torso ---------------------------------------------------------------
    const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.52, 0.7, 8, 24), cloth);
    torso.position.y = -0.55;
    figure.add(torso);

    const collar = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.26, 0.22, 20), skin);
    collar.position.y = 0.05;
    figure.add(collar);

    // --- head ----------------------------------------------------------------
    // A pivot at the neck so the head turns from the right place.
    const neck = new THREE.Group();
    neck.position.y = 0.12;
    figure.add(neck);

    const head = new THREE.Group();
    neck.add(head);

    const cranium = new THREE.Mesh(new THREE.SphereGeometry(0.5, 40, 32), skin);
    cranium.scale.set(0.94, 1.06, 0.92);
    cranium.position.y = 0.38;
    head.add(cranium);

    // Upper jaw stays with the skull; the lower one is its own pivot so the
    // mouth opens at the hinge rather than sliding down the face.
    const jawPivot = new THREE.Group();
    jawPivot.position.set(0, 0.34, -0.06);
    head.add(jawPivot);

    const jaw = new THREE.Mesh(new THREE.SphereGeometry(0.44, 32, 24), skin);
    jaw.scale.set(0.88, 0.62, 0.86);
    jaw.position.set(0, -0.2, 0.05);
    jawPivot.add(jaw);

    const mouthCavity = new THREE.Mesh(
      new THREE.SphereGeometry(0.17, 24, 16, 0, Math.PI * 2, 0, Math.PI / 2),
      new THREE.MeshStandardMaterial({ color: 0x2a1220, roughness: 0.9 }),
    );
    mouthCavity.rotation.x = Math.PI;
    mouthCavity.position.set(0, -0.02, 0.4);
    jawPivot.add(mouthCavity);

    // --- eyes ----------------------------------------------------------------
    const eyes: { group: THREE.Group; ball: THREE.Mesh; lid: THREE.Mesh }[] = [];
    for (const side of [-1, 1]) {
      const group = new THREE.Group();
      group.position.set(side * 0.19, 0.44, 0.37);
      head.add(group);

      const ball = new THREE.Mesh(new THREE.SphereGeometry(0.085, 24, 20), gloss);
      group.add(ball);

      const iris = new THREE.Mesh(new THREE.SphereGeometry(0.045, 20, 16), dark);
      iris.position.z = 0.055;
      ball.add(iris);

      const glint = new THREE.Mesh(new THREE.SphereGeometry(0.014, 10, 8), gloss);
      glint.position.set(0.02, 0.02, 0.04);
      iris.add(glint);

      // A lid that scales down over the eye, rather than a sphere that shrinks.
      const lid = new THREE.Mesh(new THREE.SphereGeometry(0.092, 24, 20), skin);
      lid.scale.y = 0.02;
      lid.position.y = 0.085;
      group.add(lid);

      const brow = new THREE.Mesh(new THREE.BoxGeometry(0.17, 0.028, 0.05), dark);
      brow.position.set(side * 0.19, 0.58, 0.4);
      brow.rotation.z = side * -0.06;
      head.add(brow);

      eyes.push({ group, ball, lid });
    }

    // --- arms ----------------------------------------------------------------
    const arms: { shoulder: THREE.Group; elbow: THREE.Group }[] = [];
    for (const side of [-1, 1]) {
      const shoulder = new THREE.Group();
      shoulder.position.set(side * 0.52, -0.2, 0);
      figure.add(shoulder);

      const upper = new THREE.Mesh(new THREE.CapsuleGeometry(0.115, 0.42, 6, 16), cloth);
      upper.position.y = -0.28;
      shoulder.add(upper);

      const elbow = new THREE.Group();
      elbow.position.y = -0.55;
      shoulder.add(elbow);

      const fore = new THREE.Mesh(new THREE.CapsuleGeometry(0.098, 0.38, 6, 16), skin);
      fore.position.y = -0.25;
      elbow.add(fore);

      const hand = new THREE.Mesh(new THREE.SphereGeometry(0.13, 20, 16), skin);
      hand.scale.set(1, 1.18, 0.62);
      hand.position.y = -0.52;
      elbow.add(hand);

      // Arms hang, slightly out from the body.
      shoulder.rotation.z = side * 0.18;
      arms.push({ shoulder, elbow });
    }

    // --- resize --------------------------------------------------------------
    const resize = () => {
      const { clientWidth: w, clientHeight: h } = mount;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.position.z = 5.4 * Math.max(1, 1.6 / camera.aspect);
      camera.updateProjectionMatrix();
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(mount);

    // --- gaze ----------------------------------------------------------------
    const pointer = { x: 0, y: 0 };
    const onPointer = (event: PointerEvent) => {
      const rect = mount.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
      pointer.y = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
    };
    const onLeave = () => {
      pointer.x = 0;
      pointer.y = 0;
    };
    mount.addEventListener("pointermove", onPointer);
    mount.addEventListener("pointerleave", onLeave);

    // --- animation -----------------------------------------------------------
    const clock = new THREE.Clock();
    let frame = 0;

    let jawOpen = 0;
    let blink = 0;
    let nextBlink = 1.5;
    let saccade = { x: 0, y: 0 };
    let nextSaccade = 1;
    let gestureUntil = 0;
    let gestureSeed = 0;
    let listening = 0;
    let thinking = 0;

    const render = () => {
      frame = requestAnimationFrame(render);
      const t = clock.getElapsedTime();
      const level = mouth.current ?? 0;
      const speaking = stateRef.current === "speaking";

      listening += ((stateRef.current === "listening" ? 1 : 0) - listening) * 0.08;
      thinking += ((stateRef.current === "thinking" ? 1 : 0) - thinking) * 0.06;

      // --- mouth: the jaw follows the audio, softened so it is not chattery ---
      jawOpen += (level - jawOpen) * (level > jawOpen ? 0.55 : 0.18);
      jawPivot.rotation.x = jawOpen * 0.34;
      mouthCavity.scale.y = 0.4 + jawOpen * 1.6;

      // --- blinking ----------------------------------------------------------
      if (t > nextBlink) {
        blink = 1;
        // Blink more often while listening: it reads as attention.
        nextBlink = t + 1.6 + Math.random() * (listening > 0.5 ? 2.4 : 4.2);
      }
      blink = Math.max(0, blink - 0.16);
      const lidDrop = Math.sin(Math.min(1, blink) * Math.PI);

      // --- gaze --------------------------------------------------------------
      if (t > nextSaccade) {
        // Look away while thinking, at the viewer otherwise.
        const range = thinking > 0.4 ? 0.5 : 0.16;
        saccade = { x: (Math.random() - 0.5) * range, y: (Math.random() - 0.5) * range * 0.6 };
        nextSaccade = t + 0.7 + Math.random() * 2.2;
      }
      const lookX = pointer.x * 0.28 + saccade.x - thinking * 0.25;
      const lookY = -pointer.y * 0.18 + saccade.y + thinking * 0.22;

      for (const eye of eyes) {
        eye.ball.rotation.y = lookX * 0.9;
        eye.ball.rotation.x = -lookY * 0.9;
        eye.lid.scale.y = 0.02 + lidDrop * 1.02;
        eye.lid.position.y = 0.085 - lidDrop * 0.085;
      }

      // --- head --------------------------------------------------------------
      neck.rotation.y = lookX * 0.42 + Math.sin(t * 0.31) * 0.04;
      neck.rotation.x = lookY * 0.22 + Math.sin(t * 0.23) * 0.02 - thinking * 0.06;
      // A small nod on syllables, and a lean in while listening.
      neck.rotation.z = Math.sin(t * 0.4) * 0.02 + listening * 0.05;
      neck.position.z = listening * 0.08;
      head.position.y = jawOpen * 0.012;

      // --- hands -------------------------------------------------------------
      // Beat gestures: short bursts while speaking, not constant waving.
      if (speaking && t > gestureUntil && Math.random() < 0.02) {
        gestureUntil = t + 0.9 + Math.random() * 1.4;
        gestureSeed = Math.random() * 10;
      }
      const gesturing = speaking && t < gestureUntil ? 1 : 0;

      arms.forEach(({ shoulder, elbow }, index) => {
        const side = index === 0 ? -1 : 1;
        const phase = t * 2.4 + gestureSeed + index * 1.7;
        const swing = gesturing * (0.32 + Math.sin(phase) * 0.22) * (0.6 + level * 0.8);

        const restZ = side * 0.18;
        const restX = 0;
        shoulder.rotation.z += (restZ + side * swing * 0.9 - shoulder.rotation.z) * 0.12;
        shoulder.rotation.x += (restX - swing * 1.15 - shoulder.rotation.x) * 0.12;
        elbow.rotation.x += (-0.25 - swing * 1.5 - elbow.rotation.x) * 0.12;
        // Breathing shows in the shoulders when the arms are still.
        shoulder.position.y = -0.2 + Math.sin(t * 0.9) * 0.012;
      });

      // --- breath ------------------------------------------------------------
      torso.scale.set(1 + Math.sin(t * 0.9) * 0.012, 1, 1 + Math.sin(t * 0.9) * 0.012);
      figure.position.y = -0.3 + Math.sin(t * 0.9) * 0.012;
      rim.intensity = 28 + level * 26;

      renderer.render(scene, camera);
    };
    render();

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      mount.removeEventListener("pointermove", onPointer);
      mount.removeEventListener("pointerleave", onLeave);
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          const material = object.material as THREE.Material | THREE.Material[];
          if (Array.isArray(material)) material.forEach((m) => m.dispose());
          else material.dispose();
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [accent, mouth]);

  return <div ref={host} className={className} aria-hidden="true" />;
}
