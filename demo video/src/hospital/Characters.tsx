import React from 'react';

/** Original vector cast. Coordinates are local; the composition supplies position. */
export type DoctorKind = 'maya' | 'omar' | 'emma' | 'paramedic' | 'coordinator';
export type DoctorPose = 'idle' | 'walk' | 'push' | 'tablet' | 'wave' | 'ready';
export type DoctorExpression = 'calm' | 'focused' | 'tired';
export type DoctorGaze = 'left' | 'center' | 'right';
export type DoctorProps = {
  kind: DoctorKind;
  frame?: number;
  pose?: DoctorPose;
  expression?: DoctorExpression;
  gaze?: DoctorGaze;
  scale?: number;
  flip?: boolean;
};

type Point = {x: number; y: number};
type Cast = {skin: string; shade: string; blush: string; hair: string; hairLight: string; scrub: string; scrubLight: string; scrubDark: string; phase: number};
const INK = '#14213B';
const COBALT = '#4263EB';
const PAPER = '#F7F6F2';
const cast: Record<DoctorKind, Cast> = {
  maya: {skin: '#C88969', shade: '#A76752', blush: '#B9705C', hair: '#252438', hairLight: '#454055', scrub: '#4263EB', scrubLight: '#6581F5', scrubDark: '#304AB5', phase: 0},
  omar: {skin: '#875A46', shade: '#674031', blush: '#95614F', hair: '#20232C', hairLight: '#373941', scrub: '#243A60', scrubLight: '#405C83', scrubDark: '#172B49', phase: 39},
  emma: {skin: '#F0C4A6', shade: '#D49A7F', blush: '#DC9C85', hair: '#944F3A', hairLight: '#BB7250', scrub: '#387E83', scrubLight: '#599AA0', scrubDark: '#245E67', phase: 78},
  paramedic: {skin: '#D6A078', shade: '#B77C59', blush: '#C18465', hair: '#634637', hairLight: '#89614A', scrub: '#C36B4D', scrubLight: '#DF9270', scrubDark: '#98503D', phase: 117},
  coordinator: {skin: '#B68062', shade: '#925E48', blush: '#A66754', hair: '#444651', hairLight: '#777985', scrub: '#7382A5', scrubLight: '#97A5C4', scrubDark: '#4F6083', phase: 156},
};

const pointAt = (origin: Point, length: number, radians: number): Point => ({x: origin.x + Math.sin(radians) * length, y: origin.y + Math.cos(radians) * length});
const mix = (a: Point, b: Point, t: number): Point => ({x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t});

/** A gently tapered, filled limb, not a stroked stick skeleton. */
function Taper({a, b, widthA, widthB, color}: {a: Point; b: Point; widthA: number; widthB: number; color: string}) {
  const distance = Math.hypot(b.x - a.x, b.y - a.y) || 1;
  const nx = (b.y - a.y) / distance;
  const ny = -(b.x - a.x) / distance;
  return <g fill={color}>
    <path d={`M ${a.x + nx * widthA} ${a.y + ny * widthA} L ${b.x + nx * widthB} ${b.y + ny * widthB} Q ${b.x + (b.x - a.x) * .055} ${b.y + (b.y - a.y) * .055} ${b.x - nx * widthB} ${b.y - ny * widthB} L ${a.x - nx * widthA} ${a.y - ny * widthA} Z`} />
    <ellipse cx={a.x} cy={a.y} rx={widthA} ry={widthA} />
    <ellipse cx={b.x} cy={b.y} rx={widthB} ry={widthB} />
  </g>;
}

type HandPose = 'relaxed' | 'grip' | 'tablet' | 'open';

/** Wrist anchored at (0,0); four separate fingertips and an opposable thumb. */
function Hand({at, elbow, color, shade, pose = 'relaxed', mirrored = false}: {at: Point; elbow: Point; color: string; shade: string; pose?: HandPose; mirrored?: boolean}) {
  const degrees = -Math.atan2(at.x - elbow.x, at.y - elbow.y) * 180 / Math.PI;
  const gripping = pose === 'grip';
  const open = pose === 'open';
  const fingers = gripping
    ? [{x:-7.6,y:10,end:22},{x:-1.7,y:11,end:25},{x:4.2,y:10,end:24},{x:9.7,y:9,end:20.5}]
    : pose === 'tablet'
      ? [{x:-7.5,y:13,end:28},{x:-1.2,y:15,end:32},{x:5,y:14,end:30},{x:10.8,y:11,end:25}]
      : open
        ? [{x:-10.5,y:13,end:33},{x:-3.3,y:15,end:39},{x:4.3,y:14,end:37},{x:11.6,y:11,end:29.5}]
        : [{x:-8,y:13,end:29},{x:-1.8,y:15,end:34},{x:4.4,y:14,end:32},{x:10.4,y:11,end:26.5}];
  return <g transform={`translate(${at.x} ${at.y}) rotate(${degrees})`}><g transform={mirrored ? 'scale(-1 1)' : undefined}>
    <path d="M-7.7-2 C-7.4 3-10.5 6-11 11 C-12.2 17-8.4 22-3 23 L6 22 C12 21 14 16 12 10 C10.2 5 8.1 2 7.7-2 Z" fill={color}/>
    {fingers.map(({x,y,end},index)=><g key={index}>
      <path d={`M${x-2.65} ${y} Q${x-3.1} ${(y+end)/2} ${x-2.7} ${end-3} Q${x-2.5} ${end+.2} ${x} ${end+.2} Q${x+2.55} ${end+.2} ${x+2.7} ${end-3} L${x+2.65} ${y} Z`} fill={color}/>
      <path d={`M${x-1.5} ${gripping ? end-7 : end-8} Q${x} ${gripping ? end-6 : end-7} ${x+1.5} ${gripping ? end-7 : end-8}`} fill="none" stroke={INK} strokeWidth=".8" opacity=".2" strokeLinecap="round"/>
    </g>)}
    {gripping ? <>
      <path d="M-8 4 C-13 4-17 8-15 12 C-13 17-7 17 1 14 C4 13 4 9 1 9 L-7 11 L-8 4 Z" fill={color}/>
      <path d="M-10 12 Q-5 15 1 12" stroke={shade} strokeWidth="1.1" fill="none" strokeLinecap="round"/>
      <path d="M-7 8 Q-2 6 6 8" stroke={INK} strokeWidth=".9" opacity=".15" fill="none" strokeLinecap="round"/>
    </> : <>
      <path d={open
        ? 'M-8 5 C-12 5-15 8-19 10 C-23 11-23 16-19 17 C-14 18-10 15-6 12 Z'
        : 'M-8 5 C-12 6-13 10-17 15 C-20 19-17 23-14 21 C-10 19-7 15-6 11 Z'} fill={color}/>
      <path d="M-8 10 Q-5 13-4 17" fill="none" stroke={INK} strokeWidth="1" opacity=".18" strokeLinecap="round"/>
      <path d="M-2 8 Q2 7 6 9" fill="none" stroke={shade} strokeWidth="1" opacity=".55" strokeLinecap="round"/>
    </>}
  </g>
  </g>;
}

function Arm({shoulder, elbow, wrist, palette, band = false, handPose = 'relaxed', back = false}: {shoulder: Point; elbow: Point; wrist: Point; palette: Cast; band?: boolean; handPose?: HandPose; back?: boolean}) {
  const cuff = mix(shoulder, elbow, .53);
  const bandCenter = mix(elbow, wrist, .88);
  const bandDegrees = -Math.atan2(wrist.x - elbow.x, wrist.y - elbow.y) * 180 / Math.PI;
  return <g>
    <Taper a={shoulder} b={elbow} widthA={17} widthB={12} color={back ? palette.shade : palette.skin}/>
    <Taper a={elbow} b={wrist} widthA={12} widthB={9} color={back ? palette.shade : palette.skin}/>
    <Taper a={shoulder} b={cuff} widthA={20} widthB={18} color={back ? palette.scrubDark : palette.scrub}/>
    <path d={`M ${cuff.x - 12} ${cuff.y + 3} Q ${cuff.x} ${cuff.y + 7} ${cuff.x + 12} ${cuff.y + 3}`} fill="none" stroke={palette.scrubLight} strokeWidth="2" opacity=".65"/>
    <Hand at={wrist} elbow={elbow} color={back ? palette.shade : palette.skin} shade={palette.shade} pose={handPose} mirrored={back}/>
    {band && <g transform={`translate(${bandCenter.x} ${bandCenter.y}) rotate(${bandDegrees})`}>
      <rect x="-11" y="-7" width="22" height="14" rx="4" fill={INK}/>
      <rect x="-7" y="-6" width="14" height="12" rx="3" fill="#2B3960"/>
      <path d="M-4 0 H-1 L1-3 L3 3 L5 0" fill="none" stroke="#97AEFF" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </g>}
  </g>;
}

function Leg({hip, phase, walking, front, palette}: {hip: Point; phase: number; walking: boolean; front: boolean; palette: Cast}) {
  const swing = walking ? Math.sin(phase) * .21 : 0;
  const kneeBend = walking ? Math.max(0, -Math.sin(phase)) * .26 : 0;
  const knee = pointAt(hip, 95, swing);
  const ankle = pointAt(knee, 95, swing - kneeBend);
  // Keep the planted shoe on the floor; the opposite foot lifts through swing.
  if (walking) ankle.y = 533 - Math.max(0, -Math.sin(phase)) * 16;
  const base = front ? palette.scrub : palette.scrubDark;
  return <g>
    <Taper a={hip} b={knee} widthA={23} widthB={19} color={base}/>
    <Taper a={knee} b={ankle} widthA={19} widthB={14} color={base}/>
    <path d={`M${hip.x + 9} ${hip.y + 18} Q${knee.x + 10} ${knee.y} ${ankle.x + 7} ${ankle.y - 8}`} fill="none" stroke={front ? palette.scrubLight : palette.scrub} opacity=".5" strokeWidth="2"/>
    <path d={`M${ankle.x - 13} ${ankle.y - 2} H${ankle.x + 12}`} fill="none" stroke={palette.scrubDark} strokeWidth="3"/>
    <g transform={`translate(${ankle.x} ${ankle.y})`}>
      <path d="M-14-1 Q-3 2 11-1 L14 9 Q20 13 27 15 Q31 18 30 24 L-17 24 Q-21 17-19 9 Z" fill={front ? '#ECF0F6' : '#C9D3E3'}/>
      <path d="M-18 21 L30 21 L30 27 Q11 29-19 27 Z" fill={INK}/>
      <path d="M1 9 L10 7 M3 14 L14 12" stroke="#AABAD1" strokeWidth="2" strokeLinecap="round"/>
    </g>
  </g>;
}

function HairBack({kind, palette}: {kind: DoctorKind; palette: Cast}) {
  if (kind === 'maya') return <g>
    <path d="M89 64 Q78 46 87 29 Q89 10 111 7 Q132 5 142 22 Q154 37 145 54 Z" fill={palette.hair}/>
    <path d="M96 25 Q114 14 131 29 M101 15 Q119 14 127 22" fill="none" stroke={palette.hairLight} strokeWidth="4" strokeLinecap="round"/>
    <path d="M81 85 Q70 41 113 31 Q163 21 181 66 L173 132 L88 140 Z" fill={palette.hair}/>
  </g>;
  if (kind === 'emma') return <g>
    <path d="M78 85 Q71 31 125 29 Q176 26 183 76 L186 142 Q174 163 145 166 L80 147 Z" fill={palette.hair}/>
    <path d="M164 62 Q181 101 172 142 M87 91 Q82 130 92 142" fill="none" stroke={palette.hairLight} strokeWidth="5" strokeLinecap="round"/>
  </g>;
  return <path d="M79 88 Q69 44 107 32 Q149 19 174 52 Q185 69 176 105 L169 139 L87 135 Z" fill={palette.hair}/>;
}

function Face({kind, palette, frame, expression, gaze}: {kind: DoctorKind; palette: Cast; frame: number; expression: DoctorExpression; gaze?: DoctorGaze}) {
  const blinkPosition = ((frame + palette.phase) % 137 + 137) % 137;
  const blinking = blinkPosition > 131;
  const tired = expression === 'tired';
  const focused = expression === 'focused';
  const gazeOffset = gaze === 'left' ? -1.8 : gaze === 'center' ? 0 : gaze === 'right' ? 1.8 : focused ? 1.2 : .3;
  return <g>
    <HairBack kind={kind} palette={palette}/>
    <ellipse cx="86" cy="107" rx="8.5" ry="13.5" fill={palette.skin}/>
    <path d="M85 101 C79 102 79 110 84 112" fill="none" stroke={palette.shade} strokeWidth="1.8" strokeLinecap="round"/>
    <ellipse cx="173" cy="107" rx="7.5" ry="12.5" fill={palette.shade}/>
    <path d="M89 79 C89 59 107 48 129 48 C153 48 170 61 172 81 L172 111 C171 134 153 156 131 156 C109 156 90 138 87 115 Z" fill={palette.skin}/>
    <path d="M160 64 C172 81 172 105 168 122 C163 137 153 148 143 152 C155 136 161 119 161 101 Z" fill={palette.shade} opacity=".19"/>
    <ellipse cx="105" cy="123" rx="9" ry="4" fill={palette.blush} opacity=".24"/>
    <ellipse cx="153" cy="123" rx="8" ry="4" fill={palette.blush} opacity=".21"/>
    <g fill="none" stroke={palette.hair} strokeWidth="2.8" strokeLinecap="round">
      <path d={tired ? 'M100 93 Q109 89 119 92' : focused ? 'M100 91 Q109 88 119 91' : 'M100 90 Q109 85.5 119 89'}/>
      <path d={tired ? 'M140 92 Q150 89 159 93' : focused ? 'M140 91 Q150 88 159 91' : 'M140 89 Q150 85.5 159 90'}/>
    </g>
    {blinking ? <g fill="none" stroke={palette.hair} strokeWidth="2" strokeLinecap="round"><path d="M101 103 Q110 107 119 103"/><path d="M141 103 Q150 107 159 103"/></g> : <g>
      <ellipse cx="110" cy="103" rx="8.7" ry={tired ? 3.3 : 4.6} fill={PAPER}/>
      <ellipse cx="150" cy="103" rx="8.3" ry={tired ? 3.3 : 4.6} fill={PAPER}/>
      <ellipse cx={110 + gazeOffset} cy="103" rx="3.25" ry={tired ? 2.9 : 4.05} fill={INK}/>
      <ellipse cx={150 + gazeOffset} cy="103" rx="3.25" ry={tired ? 2.9 : 4.05} fill={INK}/>
      <circle cx={111 + gazeOffset} cy="101.5" r=".95" fill={PAPER}/><circle cx={151 + gazeOffset} cy="101.5" r=".95" fill={PAPER}/>
      <path d={tired ? 'M101.5 102 Q110 97.7 118.5 102 M142 102 Q150 97.7 158 102' : 'M101.5 102 Q110 95.5 118.5 102 M142 102 Q150 95.5 158 102'} fill="none" stroke={palette.hair} strokeWidth="1.35" strokeLinecap="round"/>
    </g>}
    {tired && <g stroke={palette.shade} strokeWidth="1.4" fill="none" opacity=".38" strokeLinecap="round"><path d="M104 112 Q110 114 116 112"/><path d="M144 112 Q150 114 156 112"/></g>}
    <path d="M131 105 C131 111 127 114 130 116 C132 118 136 118 138 116" fill="none" stroke={palette.shade} strokeWidth="1.9" strokeLinecap="round"/>
    <path d={tired ? 'M121 135 Q132 132 143 135' : focused ? 'M121 133 Q132 136.5 143 133' : 'M119 131 Q132 141 145 131'} fill="none" stroke={palette.shade} strokeWidth="2.4" strokeLinecap="round"/>
    {!tired && !focused && <path d="M124 134 Q132 137 140 134" stroke={PAPER} strokeWidth="1.7" strokeLinecap="round" fill="none" opacity=".85"/>}
    {kind === 'emma' && <g fill="#B77655" opacity=".65"><circle cx="102" cy="119" r="1.2"/><circle cx="108" cy="121" r="1.2"/><circle cx="114" cy="118" r="1.1"/><circle cx="146" cy="119" r="1.1"/><circle cx="153" cy="121" r="1.2"/><circle cx="158" cy="118" r="1.1"/></g>}
    {kind === 'maya' && <>
      <path d="M85 92 Q81 49 115 40 Q145 32 165 55 Q141 53 119 72 Q104 83 93 85 L91 116 L84 111 Z" fill={palette.hair}/>
      <path d="M163 54 Q178 67 173 103 L165 97 L158 65 Z" fill={palette.hair}/>
      <path d="M94 63 Q112 43 133 46" stroke={palette.hairLight} strokeWidth="4" strokeLinecap="round" fill="none"/>
      <path d="M83 119 C73 121 76 136 85 134" fill="none" stroke="#F0C788" strokeWidth="2.5"/>
    </>}
    {kind === 'omar' && <>
      <path d="M86 92 L82 72 Q78 46 112 36 Q151 25 170 55 L174 84 L165 84 L160 65 Q124 77 95 69 L93 93 Z" fill={palette.hair}/>
      <g fill={palette.hair}><circle cx="92" cy="56" r="12"/><circle cx="106" cy="45" r="13"/><circle cx="121" cy="42" r="13"/><circle cx="138" cy="44" r="13"/><circle cx="153" cy="49" r="12"/><circle cx="164" cy="62" r="11"/></g>
      <g fill="none" stroke={palette.hairLight} strokeWidth="2.5" strokeLinecap="round"><path d="M96 48 Q102 44 107 48 M114 37 Q121 35 125 40 M137 39 Q144 38 148 43 M152 55 Q160 52 164 60"/></g>
      <path d="M101 130 Q114 146 131 148 Q151 147 163 130 Q157 150 142 154 Q118 161 104 140 Z" fill={palette.hair} opacity=".3"/>
    </>}
    {kind === 'emma' && <>
      <path d="M82 98 Q73 60 100 41 Q119 27 144 34 Q167 39 177 72 Q162 67 149 48 Q143 79 92 88 L92 130 Q77 119 82 98 Z" fill={palette.hair}/>
      <path d="M97 68 Q122 61 136 44" fill="none" stroke={palette.hairLight} strokeWidth="5" strokeLinecap="round"/>
      <path d="M170 88 L176 140 L166 148 L165 116" fill={palette.hair}/>
    </>}
    {kind === 'paramedic' && <>
      <path d="M81 91 L81 65 Q86 40 119 36 Q149 35 167 55 Q144 65 115 59 Q104 78 93 82 L92 106 L85 107 Z" fill={palette.hair}/>
      <path d="M96 53 Q117 41 143 48" fill="none" stroke={palette.hairLight} strokeWidth="5" strokeLinecap="round"/>
    </>}
    {kind === 'coordinator' && <>
      <path d="M85 100 Q69 61 98 40 Q125 23 153 37 Q171 45 177 69 Q154 65 143 49 Q123 72 94 78 L94 103 Z" fill={palette.hair}/>
      <path d="M94 56 Q110 39 127 39 M154 48 L171 77" fill="none" stroke={palette.hairLight} strokeWidth="5" strokeLinecap="round"/>
      <g fill="none" stroke={INK} strokeWidth="1.8"><rect x="96" y="95" width="28" height="20" rx="7"/><rect x="136" y="95" width="28" height="20" rx="7"/><path d="M124 102 Q130 99 136 102 M86 98 L96 102"/></g>
    </>}
  </g>;
}

function Uniform({palette, kind}: {palette: Cast; kind: DoctorKind}) {
  return <g>
    <path d="M102 164 Q85 167 74 181 Q71 206 78 235 L78 328 Q86 353 129 356 Q164 356 184 337 L180 225 Q188 199 177 181 Q163 169 148 165 Z" fill={palette.scrub}/>
    <path d="M161 176 Q175 211 171 252 L171 329 Q145 343 115 343 L129 356 Q166 356 184 337 L180 225 Q188 199 177 181 Z" fill={palette.scrubDark} opacity=".62"/>
    <path d="M104 162 L126 185 L149 161 L155 174 L127 204 L99 175 Z" fill={palette.scrubDark}/>
    <path d="M104 163 L126 186 L118 195 L97 176 Z M149 163 L126 186 L135 195 L157 176 Z" fill={palette.scrubLight}/>
    <path d="M85 278 L114 280 L113 310 Q99 315 85 308 Z" fill={palette.scrubDark} opacity=".57"/>
    <path d="M86 281 L112 283" stroke={palette.scrubLight} strokeWidth="2.3" strokeLinecap="round"/>
    <path d="M91 282 L91 270" stroke={PAPER} strokeWidth="3" strokeLinecap="round"/>
    <path d="M98 282 L98 273" stroke="#A9BAFF" strokeWidth="3" strokeLinecap="round"/>
    <path d="M146 236 H169 V259 Q158 264 146 259 Z" fill={palette.scrubDark} opacity=".45"/>
    <path d="M149 238 H165" stroke={palette.scrubLight} strokeWidth="2"/>
    <path d="M91 326 Q124 332 160 325" fill="none" stroke={palette.scrubLight} strokeWidth="2" opacity=".35"/>
    {kind !== 'paramedic' && <g>
      <path d="M105 173 Q95 185 99 211 Q102 234 117 234 Q134 233 139 211 L150 177" fill="none" stroke={INK} strokeWidth="5" strokeLinecap="round"/>
      <path d="M105 173 L101 181 M150 177 L148 185" stroke="#BCC8DE" strokeWidth="5" strokeLinecap="round"/>
      <path d="M116 234 L116 247 Q116 255 127 255 L140 255" stroke={INK} strokeWidth="4" fill="none"/>
      <circle cx="141" cy="254" r="10" fill="#BDCBE0"/><circle cx="141" cy="254" r="6" fill="#E7EDFF"/>
    </g>}
    {kind === 'paramedic' && <>
      <path d="M77 232 H180 V246 H77 Z" fill="#E7EDFF" opacity=".8"/>
      <path d="M77 237 H180" stroke="#E4C773" strokeWidth="3"/>
      <path d="M104 183 V204 M93 193 H115" stroke={PAPER} strokeWidth="6" strokeLinecap="round"/>
    </>}
    <g transform="translate(146 202) rotate(4)">
      <rect x="0" y="0" width="22" height="31" rx="3" fill="#E7EDFF"/>
      <rect x="6" y="-3" width="10" height="6" rx="2" fill={INK}/>
      <circle cx="8" cy="12" r="4" fill={palette.scrubLight}/>
      <path d="M4 20 Q8 14 12 20" fill={palette.scrubLight}/>
      <path d="M15 10 H18 M15 14 H18 M5 25 H17" stroke="#98A9C5" strokeWidth="1.5" strokeLinecap="round"/>
    </g>
  </g>;
}

export function Doctor({kind, frame = 0, pose = 'idle', expression = 'calm', gaze, scale = 1, flip = false}: DoctorProps) {
  const palette = cast[kind];
  const walking = pose === 'walk' || pose === 'push';
  const cycle = (frame + palette.phase) / 48 * Math.PI * 2;
  const breath = Math.sin((frame + palette.phase) / 21) * 1.1;
  const bob = walking ? -Math.abs(Math.sin(cycle)) * 2.3 : breath;
  let backElbow: Point = {x: 78, y: 265};
  let backWrist: Point = {x: 85, y: 331};
  let frontElbow: Point = {x: 186, y: 263};
  let frontWrist: Point = {x: 178, y: 330};
  if (pose === 'walk') {
    const armSwing = Math.sin(cycle) * .24;
    backElbow = pointAt({x: 84, y: 198}, 68, -armSwing);
    backWrist = pointAt(backElbow, 64, -armSwing - .1);
    frontElbow = pointAt({x: 177, y: 198}, 68, armSwing);
    frontWrist = pointAt(frontElbow, 64, armSwing - .12);
  } else if (pose === 'push') {
    backElbow = {x: 123, y: 258}; backWrist = {x: 216, y: 271};
    frontElbow = {x: 191, y: 268}; frontWrist = {x: 232, y: 276};
  } else if (pose === 'tablet') {
    backElbow = {x: 81, y: 269}; backWrist = {x: 143, y: 292};
    frontElbow = {x: 192, y: 268}; frontWrist = {x: 168, y: 300};
  } else if (pose === 'wave') {
    frontElbow = {x: 208, y: 172}; frontWrist = {x: 221 + Math.sin(frame / 8) * 5, y: 110};
  } else if (pose === 'ready') {
    frontElbow = {x: 199, y: 257}; frontWrist = {x: 170, y: 315};
    backElbow = {x: 68, y: 260}; backWrist = {x: 95, y: 311};
  }
  const headTilt = expression === 'tired' ? 1.5 : pose === 'tablet' ? 1.5 : 0;
  const handPose: HandPose = pose === 'push' ? 'grip' : pose === 'tablet' ? 'tablet' : 'relaxed';
  return <g transform={`scale(${scale})${flip ? ' translate(260 0) scale(-1 1)' : ''}`}>
    <Leg hip={{x: 112, y: 343}} phase={cycle + Math.PI} walking={walking} front={false} palette={palette}/>
    <Leg hip={{x: 154, y: 343}} phase={cycle} walking={walking} front palette={palette}/>
    <g transform={`translate(0 ${bob})`}>
      <Arm shoulder={{x: 84, y: 198}} elbow={backElbow} wrist={backWrist} palette={palette} handPose={handPose} back/>
      <path d="M110 141 L110 166 Q124 187 147 166 L146 138 Z" fill={palette.skin}/>
      <path d="M110 145 Q126 161 146 145 L146 158 Q128 172 111 158 Z" fill={palette.shade} opacity=".53"/>
      <Uniform palette={palette} kind={kind}/>
      <g transform={`rotate(${headTilt} 129 164)`}><Face kind={kind} palette={palette} frame={frame} expression={expression} gaze={gaze}/></g>
      {pose === 'tablet' && <g transform="translate(125 257) rotate(-8)">
        <rect x="0" y="0" width="63" height="83" rx="7" fill={INK}/>
        <rect x="5" y="7" width="53" height="67" rx="3" fill="#D9E3FA"/>
        <rect x="12" y="16" width="37" height="6" rx="3" fill={COBALT}/>
        <path d="M12 38 H20 L24 30 L29 48 L35 38 H50" stroke={COBALT} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" fill="none"/>
        <path d="M13 58 H39 M13 64 H29" stroke="#91A2C6" strokeWidth="2.5" strokeLinecap="round"/>
        <circle cx="31.5" cy="78" r="1.8" fill="#8D9EBC"/>
      </g>}
      <Arm shoulder={{x: 177, y: 198}} elbow={frontElbow} wrist={frontWrist} palette={palette} band handPose={pose === 'wave' ? 'open' : handPose}/>
    </g>
  </g>;
}

/** Patient: 550 × 180 local space, head left, feet right; no stretcher included. */
export function Patient({frame = 0, scale = 1}: {frame?: number; scale?: number}) {
  const breathe = Math.sin(frame / 24) * 1.3;
  return <g transform={`scale(${scale})`}>
    <path d="M19 119 Q14 89 39 79 L111 81 Q132 86 134 116 L120 144 L36 147 Z" fill="#FFFFFF"/>
    <path d="M28 133 Q79 145 123 128 L119 146 L35 150 Z" fill="#DEE5F0"/>
    <path d="M120 92 L151 97 L159 125 L119 133 Z" fill="#D9A482"/>
    <g transform="translate(6 1)">
      <path d="M58 73 C59 54 77 47 94 51 C116 55 128 74 128 95 L126 109 C122 125 107 133 91 131 C72 129 58 115 54 96 Z" fill="#E4B594"/>
      <path d="M118 75 C128 89 126 109 117 119 Q109 128 101 129 Q119 112 118 94 Z" fill="#C99575" opacity=".23"/>
      <path d="M58 76 Q43 62 55 44 Q65 26 92 34 Q113 34 123 55 L126 69 Q111 59 96 59 Q76 62 64 77 Z" fill="#4E4140"/>
      <path d="M52 67 Q88 51 120 62 L124 77 Q88 64 56 81 Z" fill="#F8FAFC"/>
      <path d="M58 70 Q86 58 119 67 M60 76 Q88 64 120 72" stroke="#DCE4EE" strokeWidth="1.5" fill="none"/>
      <ellipse cx="62" cy="98" rx="7" ry="10" fill="#E4B594"/>
      <path d="M62 93 Q57 94 61 102" stroke="#C28E70" strokeWidth="1.4" strokeLinecap="round" fill="none"/>
      <path d="M81 85 Q87 82 94 85 M106 85 Q112 82 117 86" stroke="#5E4841" strokeWidth="2" strokeLinecap="round" fill="none"/>
      <ellipse cx="88" cy="94" rx="6.5" ry="3.7" fill={PAPER}/>
      <ellipse cx="112" cy="94" rx="5.6" ry="3.7" fill={PAPER}/>
      <ellipse cx="89" cy="94" rx="2.7" ry="3.3" fill={INK}/>
      <ellipse cx="113" cy="94" rx="2.7" ry="3.3" fill={INK}/>
      <circle cx="89.8" cy="93" r=".7" fill={PAPER}/><circle cx="113.8" cy="93" r=".7" fill={PAPER}/>
      <path d="M82 93 Q88 88 94 93 M107 93 Q112 88 117 93" stroke="#5E4841" strokeWidth="1" strokeLinecap="round" fill="none"/>
      <path d="M102 94 C102 99 101 102 103 104 Q106 106 109 104 M93 116 Q103 121 112 116" stroke="#BA8165" strokeWidth="1.8" strokeLinecap="round" fill="none"/>
    </g>
    <g transform={`translate(0 ${breathe})`}>
      <path d="M141 99 Q160 71 199 82 L267 101 Q285 123 302 136 L181 146 L138 130 Z" fill="#ADC4E9"/>
      <path d="M192 98 Q234 95 261 107 Q276 118 290 133" stroke="#83A5D9" strokeWidth="3" fill="none"/>
      <path d="M228 105 Q302 96 365 111 L464 127 Q494 125 512 139 L524 158 L159 159 Q159 126 184 115 Z" fill="#E7EDFF"/>
      <path d="M242 128 Q319 109 381 127 L473 145 Q496 140 518 152 L524 165 L161 165 L159 155 Q228 153 242 128 Z" fill="#C6D4F2"/>
      <path d="M269 115 Q264 133 255 143 M335 119 Q321 135 323 152 M410 131 Q398 147 405 156" stroke="#AFBFE3" strokeWidth="3" strokeLinecap="round" fill="none"/>
      <path d="M520 142 Q537 141 543 154 L544 164 L519 164 Z" fill="#EDF1F8"/>
      <path d="M521 162 H546" stroke="#B2C0D6" strokeWidth="4" strokeLinecap="round"/>
      <path d="M173 115 Q190 119 210 129 L207 144 Q184 140 165 132 Z" fill="#E4B594"/>
      <g transform="translate(207 136) scale(.8)"><Hand at={{x:0,y:0}} elbow={{x:-27,y:-10}} color="#E4B594" shade="#BF8868" pose="relaxed"/></g>
      <path d="M191 128 L186 139" stroke="#FFFFFF" strokeWidth="7"/>
    </g>
  </g>;
}
