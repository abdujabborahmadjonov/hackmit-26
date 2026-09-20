import { useEffect, useRef, useState, type RefObject } from "react";
import * as THREE from "three";
import { FBXLoader } from "three/examples/jsm/loaders/FBXLoader.js";
import type { VoiceState } from "./useVoice";

/** A rigged human avatar, driven by the voice.
 *
 *  The model carries the ARKit blendshape set, so the mouth is shaped rather
 *  than hinged: `jawOpen` follows the audio level and `mouthFunnel` rounds the
 *  lips as it opens, which is what stops a talking head looking like a nutcracker.
 *  With hosted speech that level is the real waveform, so it moves on the
 *  sounds themselves.
 *
 *  It is a stock avatar and not a likeness of anybody, which is what lets it
 *  move at all - animating a real person's face needs their agreement, and the
 *  consent on file here covers a still photograph.
 */

/** Blendshapes are addressed by name, which differs in case between exporters. */
function findMorph(mesh: THREE.Mesh, name: string): number | undefined {
  const dict = mesh.morphTargetDictionary;
  if (!dict) return undefined;
  if (name in dict) return dict[name];
  const lower = name.toLowerCase();
  for (const key of Object.keys(dict)) {
    if (key.toLowerCase() === lower || key.toLowerCase().endsWith("." + lower)) return dict[key];
  }
  return undefined;
}

export function RiggedAvatar({
  src,
  mouth,
  state,
  accent = "#4f46e5",
  className,
  onFailed,
}: {
  src: string;
  mouth: RefObject<number>;
  state: VoiceState;
  accent?: string;
  className?: string;
  /** Called when the model cannot load, so the caller can fall back. */
  onFailed?: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const stateRef = useRef(state);
  stateRef.current = state;
  const [progress, setProgress] = useState(0);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const mount = host.current;
    if (!mount) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(26, 1, 0.1, 200);

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      onFailed?.();
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.style.display = "block";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    mount.appendChild(renderer.domElement);

    const colour = new THREE.Color(accent);
    scene.add(new THREE.AmbientLight(0xffffff, 1.1));
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(1.6, 2.4, 3.2);
    scene.add(key);
    const rim = new THREE.PointLight(colour, 26, 12);
    rim.position.set(-2.2, 1.6, -1.6);
    scene.add(rim);
    const fill = new THREE.PointLight(0xffffff, 6, 10);
    fill.position.set(-1.4, 0.6, 2.4);
    scene.add(fill);

    const root = new THREE.Group();
    scene.add(root);

    // Filled in once the model arrives.
    const morphs: { mesh: THREE.Mesh; index: number }[] = [];
    const morphSets: Record<string, { mesh: THREE.Mesh; index: number }[]> = {};
    const collect = (names: string[], into: string) => {
      morphSets[into] = [];
      for (const { mesh } of morphs) {
        for (const name of names) {
          const index = findMorph(mesh, name);
          if (index !== undefined) morphSets[into].push({ mesh, index });
        }
      }
    };
    let head: THREE.Object3D | null = null;
    let neck: THREE.Object3D | null = null;
    let spine: THREE.Object3D | null = null;
    const arms: { bone: THREE.Object3D; rest: THREE.Euler; side: number }[] = [];
    const bones: Record<string, THREE.Object3D> = {};

    let disposed = false;
    let frame = 0;
    // Vertical offset of the framing target, set once the head is located.
    let framedAt = 0;

    new FBXLoader().load(
      src,
      (model) => {
        if (disposed) return;

        model.traverse((child) => {
          if (child instanceof THREE.Mesh) {
            child.frustumCulled = false;
            if (child.morphTargetDictionary) morphs.push({ mesh: child, index: -1 });
            const material = child.material as THREE.Material | THREE.Material[];
            const fix = (m: THREE.Material) => {
              const std = m as THREE.MeshStandardMaterial;
              if (std.map) std.map.colorSpace = THREE.SRGBColorSpace;
              std.side = THREE.FrontSide;
            };
            Array.isArray(material) ? material.forEach(fix) : fix(material);
          }
          const name = child.name.toLowerCase();
          const isBone = (child as THREE.Bone).isBone;
          if (isBone && !head && name.endsWith("head")) head = child;
          if (isBone && !neck && name.endsWith("neck")) neck = child;
          if (isBone && !spine && /spine2?$/.test(name)) spine = child;
          // Matches LeftArm / RightArm / LeftForeArm / RightForeArm, with or
          // without a mixamorig: prefix.
          const limb = /(left|right)(fore)?arm$/.exec(name);
          if (limb) {
            // FBX carries a wrapper node and a bone under the same name here.
            // The deeper one is what the skin is actually bound to - posing
            // the outer wrapper moves nothing, which cost me a few rounds.
            bones[`${limb[1]}${limb[2] ? "fore" : ""}arm`] = child;
          }
        });

        // The model ships in its bind pose - a T - because there is no idle
        // animation in the file. Put the arms down before anything is drawn,
        // otherwise it greets every visitor like a scarecrow.
        const pose = (key: string, x: number, y: number, z: number) => {
          const bone = bones[key];
          if (!bone) return;
          bone.rotation.set(bone.rotation.x + x, bone.rotation.y + y, bone.rotation.z + z);
        };
        // Upper arms down along the body; forearms left at their bind
        // rotation, which is already straight - bending them here folded the
        // hands together in front of the chest.
        // Attempted, but this rig does not respond to it: the node the skin
        // is bound to is not the one these names resolve to, and reverse-
        // engineering that is not worth it when the arms are out of frame.
        // The real fix is an idle/talking animation clip for this skeleton
        // (Mixamo publishes them free), which would also let the shot open out.
        pose("leftarm", 0, 0, 1.38);
        pose("rightarm", 0, 0, -1.38);

        for (const side of ["left", "right"] as const) {
          const bone = bones[`${side}arm`];
          if (bone) {
            arms.push({ bone, rest: bone.rotation.clone(), side: side === "left" ? -1 : 1 });
          }
        }

        // Mouth and eyes, by ARKit name.
        collect(["jawOpen"], "jawOpen");
        collect(["mouthFunnel"], "funnel");
        collect(["mouthClose"], "close");
        collect(["mouthSmileLeft", "mouthSmileRight"], "smile");
        collect(["eyeBlinkLeft", "eyeBlinkRight"], "blink");
        collect(["browInnerUp"], "browUp");
        collect(["eyeLookInLeft", "eyeLookOutRight"], "lookRight");
        collect(["eyeLookOutLeft", "eyeLookInRight"], "lookLeft");
        collect(["eyeLookUpLeft", "eyeLookUpRight"], "lookUp");
        collect(["eyeLookDownLeft", "eyeLookDownRight"], "lookDown");

        // FBX units are usually centimetres; normalise on the bounding box so
        // the framing does not depend on how the model was exported.
        const box = new THREE.Box3().setFromObject(model);
        const size = new THREE.Vector3();
        box.getSize(size);
        const scale = 1.7 / (size.y || 1);
        model.scale.setScalar(scale);
        root.add(model);

        // Frame it like a video call: head and shoulders, centred on the head
        // bone. This is a conversation, and the face is where it happens - the
        // jaw, the blinking and the gaze are all up here. It also sidesteps
        // posing a full body that ships in a T-pose with no idle animation.
        model.updateWorldMatrix(true, true);
        const focus = new THREE.Vector3();
        if (head) (head as THREE.Object3D).getWorldPosition(focus);
        else focus.set(0, size.y * scale * 0.4, 0);
        model.position.y -= focus.y;
        // Head and shoulders, like a video call. Two reasons, and the second
        // is the honest one: the face is where this conversation happens - the
        // jaw, the blinking and the gaze are all here and all readable at this
        // size - and the model ships in a T-pose with no idle animation, so a
        // wider shot means posing an arm chain by guessing at the rig's bind
        // orientations. An idle/talking clip (Mixamo publishes them free for
        // this skeleton) would let us open the shot out properly.
        framedAt = 0.04;

        setReady(true);
        resize();
      },
      (event) => {
        if (event.total) setProgress(Math.round((event.loaded / event.total) * 100));
      },
      () => {
        if (!disposed) onFailed?.();
      },
    );

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = mount;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      // Close enough that the head fills the frame, pulled back on a wide
      // canvas so the shoulders do not crop.
      camera.position.set(0, framedAt, 0.52 * Math.max(1, 1.7 / camera.aspect));
      camera.lookAt(0, framedAt, 0);
      camera.updateProjectionMatrix();
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(mount);

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

    const set = (name: string, value: number) => {
      for (const { mesh, index } of morphSets[name] ?? []) {
        if (mesh.morphTargetInfluences) mesh.morphTargetInfluences[index] = value;
      }
    };

    const clock = new THREE.Clock();
    let jaw = 0;
    let blink = 0;
    let nextBlink = 1.4;
    let listening = 0;
    let thinking = 0;
    let gestureUntil = 0;
    let seed = 0;

    const render = () => {
      frame = requestAnimationFrame(render);
      const t = clock.getElapsedTime();
      const level = mouth.current ?? 0;
      const speaking = stateRef.current === "speaking";

      listening += ((stateRef.current === "listening" ? 1 : 0) - listening) * 0.08;
      thinking += ((stateRef.current === "thinking" ? 1 : 0) - thinking) * 0.06;

      // --- mouth: shaped, not hinged -----------------------------------------
      jaw += (level - jaw) * (level > jaw ? 0.5 : 0.2);
      set("jawOpen", Math.min(1, jaw * 0.85));
      // Lips round as the jaw drops, which is what keeps it from looking like
      // a hinge opening and closing.
      set("funnel", Math.min(0.55, jaw * 0.5));
      set("close", Math.max(0, 0.12 - jaw * 0.3));
      set("smile", 0.12 + listening * 0.16 + (speaking ? 0.05 : 0));

      // --- eyes ---------------------------------------------------------------
      if (t > nextBlink) {
        blink = 1;
        nextBlink = t + 1.5 + Math.random() * (listening > 0.5 ? 2.2 : 4.0);
      }
      blink = Math.max(0, blink - 0.15);
      set("blink", Math.sin(Math.min(1, blink) * Math.PI));
      set("browUp", thinking * 0.35 + level * 0.12);

      const gazeX = pointer.x * 0.6 - thinking * 0.4;
      const gazeY = -pointer.y * 0.4 + thinking * 0.35;
      set("lookRight", Math.max(0, gazeX));
      set("lookLeft", Math.max(0, -gazeX));
      set("lookUp", Math.max(0, gazeY));
      set("lookDown", Math.max(0, -gazeY));

      // --- head and body ------------------------------------------------------
      if (head) {
        head.rotation.y = pointer.x * 0.2 + Math.sin(t * 0.3) * 0.02;
        head.rotation.x = -pointer.y * 0.1 + Math.sin(t * 0.24) * 0.015 - thinking * 0.05;
      }
      if (neck) {
        neck.rotation.y = pointer.x * 0.12;
        neck.rotation.z = listening * 0.05;
      }
      if (spine) spine.rotation.x = Math.sin(t * 0.9) * 0.008 + listening * 0.02;

      // --- hands: beat gestures in bursts -------------------------------------
      if (speaking && t > gestureUntil && Math.random() < 0.02) {
        gestureUntil = t + 0.9 + Math.random() * 1.3;
        seed = Math.random() * 10;
      }
      const gesturing = speaking && t < gestureUntil ? 1 : 0;
      for (const { bone, rest, side } of arms) {
        const swing = gesturing * (0.22 + Math.sin(t * 2.6 + seed) * 0.16) * (0.5 + level);
        bone.rotation.z += (rest.z + side * swing - bone.rotation.z) * 0.1;
        bone.rotation.x += (rest.x - swing * 0.5 - bone.rotation.x) * 0.1;
      }

      root.position.y = Math.sin(t * 0.9) * 0.006;
      rim.intensity = 26 + level * 24;

      renderer.render(scene, camera);
    };
    render();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      mount.removeEventListener("pointermove", onPointer);
      mount.removeEventListener("pointerleave", onLeave);
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          const material = object.material as THREE.Material | THREE.Material[];
          const drop = (m: THREE.Material) => {
            const std = m as THREE.MeshStandardMaterial;
            std.map?.dispose();
            std.normalMap?.dispose();
            std.roughnessMap?.dispose();
            m.dispose();
          };
          Array.isArray(material) ? material.forEach(drop) : drop(material);
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [accent, mouth, src, onFailed]);

  return (
    <div className={"relative " + (className ?? "")}>
      <div ref={host} className="h-full w-full" aria-hidden="true" />
      {!ready && (
        <div className="absolute inset-0 grid place-items-center">
          <p className="text-xs text-white/45">
            {progress > 0 ? `Loading the avatar… ${progress}%` : "Loading the avatar…"}
          </p>
        </div>
      )}
    </div>
  );
}
