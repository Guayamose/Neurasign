# Original hospital character artwork

The hospital cast is original SVG artwork drawn in `src/hospital/Characters.tsx`. Its shapes use no generated imagery, stock illustration, external fonts, or third-party character assets. The surrounding film composition uses Manrope typography separately. All character shapes remain editable code-native vectors.

## Doctor rig

`Doctor` returns an SVG `<g>` in a **260 × 560** local coordinate system. Place it inside the composition's SVG and position it with a parent group. Resting shoe soles sit at approximately y=560. Walking deliberately lifts the free foot; the animation does not translate the character through the scene.

```tsx
<g transform="translate(420 250)">
  <Doctor kind="maya" frame={frame} pose="push" expression="focused" scale={0.9}/>
</g>
```

Props:

| Prop | Accepted values / default |
| --- | --- |
| `kind` | `maya`, `omar`, `emma`, `paramedic`, `coordinator`; required |
| `frame` | Number, default 0; motion designed for 30 fps |
| `pose` | `idle`, `walk`, `push`, `tablet`, `wave`, `ready`; default `idle` |
| `expression` | `calm`, `focused`, `tired`; default `calm` |
| `gaze` | Optional `left`, `center`, `right`; omitted preserves the original expression-based gaze |
| `scale` | Number, default 1; scales the entire local rig |
| `flip` | Boolean, default false; mirrors within the 260-unit width |

The push pose reaches towards the right; near hand contact is approximately **(253, 280)** and far hand approximately **(232, 274)**. A parent `flip` can reverse the action. The stretcher handle should meet that area. The walk and push cycles are 48 frames, with offset phases per person. Breathing, subtle body lift, sleeve movement, fingers and blinks are deterministic. Every doctor has a visible dark wristband with a cobalt signal mark. The mark is illustrative artwork, not a measurement readout. Gaze directions refer to the unmirrored local artwork: use `gaze="right"` while approaching a patient to the right and `gaze="center"` for a recommendation portrait. Flipping mirrors the gaze too.

Hands now use a wrist-connected palm, a separate opposable thumb and **four individually shaped, rounded fingers**. Relaxed and ready hands extend clearly below the wristband; a wave uses an open spread, pushing uses curled fingers, and tablet fingers rest across the device. The far hand is mirrored anatomically. These are internal hand poses: the public `Doctor` API and all arm/wristband anchors are unchanged.

The refined face construction uses a rounded jaw, a common eye baseline, consistent pupil size and direction, balanced eyebrows, a curved nose and a centered mouth. Focus and tiredness are expressed gently through eyelid opening and small mouth changes rather than sharp eyebrow angles or a heavily tilted face. Coordinator glasses follow the same eye baseline.

Characters are differentiated through anatomy, hair, clothing and facial features:

- **Maya:** medium warm skin, dark high bun, cobalt scrubs and small warm-metal earring.
- **Omar:** dark brown skin, close cropped curls, navy scrubs and subtle beard shading.
- **Emma:** light freckled skin, auburn bob and muted teal scrubs.
- **Paramedic:** warm tan skin, short brown hair and muted terracotta uniform with a pale reflective strip.
- **Coordinator:** medium warm skin, short salt-and-pepper hair, glasses and slate-blue uniform.

All doctors carry a small illustrated ID badge; clinical scrubs include a V collar, pocket seams, pens and comfortable closed shoes. The three doctor leads and coordinator have stethoscopes. No names, job claims or diagnoses are encoded into the drawing itself.

## Patient

`Patient` returns a **550 × 180** local SVG group, head to the left and feet to the right. Props are optional `frame` and `scale`. It includes a pillow, awake face, forehead dressing, hospital wrist ID and a pale blanket. There is no blood, visible injury or distress expression. It does not include the stretcher so the environment owns its geometry and movement.

The patient shares the refined rounded hand construction, with four visible fingers and a thumb resting on the blanket. Both open eyes follow the face's gentle three-quarter perspective, and the nose, mouth and cheek contours are curved.

```tsx
<g transform="translate(680 430)">
  <Patient frame={frame}/>
</g>
```

The visual palette centers on navy `#14213B`, cobalt `#4263EB`, powder blue `#E7EDFF` and warm cream `#F7F6F2`. Skin, fabric shadows and hair use muted supporting tones. Cell shading uses a small number of solid fills instead of gradients or raster textures.

## Refinement review

The revised cast, six poses, face/hand close-ups and patient were rendered independently as vector SVGs and inspected in Chrome at 1920 × 1080. A 640 × 360 cast sheet checks the smaller silhouette. Local review exports are under `review/hospital-revision/`: `cast-refined.png`, `poses-refined.png`, `anatomy-detail.png`, `patient-refined.png` and `cast-small.png`. These are QA artifacts rather than film assets. The main composition can continue using the same positions and scales.
