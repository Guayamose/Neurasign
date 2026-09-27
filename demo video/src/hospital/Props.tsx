import React from 'react';
import {staticFile} from 'remotion';
import {C,Text,Pill,SignalIcon,Wave,mix,linear,Check} from './Design';

export const Ambulance:React.FC<{frame:number}>=({frame})=><g>
 <ellipse cx="315" cy="250" rx="280" ry="22" fill={C.ink} opacity=".12"/>
 <path d="M10 216V54Q10 26 40 26H351V63H455L532 137V216Z" fill={C.white} stroke={C.ink} strokeWidth="4"/>
 <path d="M368 79H447L500 135H368Z" fill="#B8D1EC"/><path d="M406 80v55" stroke="#93ABC9" strokeWidth="5"/>
 <path d="M12 175H350V195H12Z" fill={C.blue}/><path d="M350 152H532V175H350Z" fill={C.blue}/>
 <rect x="230" y="12" width="112" height="16" rx="7" fill={C.blue}/><rect x="230" y="12" width="45" height="16" rx="7" fill={frame%22<11?'#96B8FF':C.blue}/>
 <path d="M135 74h33v25h25v33h-25v25h-33v-25h-25V99h25Z" fill={C.blue}/>
 <path d="M30 62h51v83H30Z" fill="#EAF0FA"/><path d="M225 62h94v83h-94Z" fill="#EAF0FA"/>
 <path d="M351 65v141M455 143v49M368 151h23" stroke="#A3B2C8" strokeWidth="4"/>
 <rect x="491" y="156" width="31" height="13" rx="4" fill="#F5D59B"/><rect x="1" y="201" width="53" height="20" rx="6" fill={C.ink}/><rect x="495" y="201" width="53" height="20" rx="6" fill={C.ink}/>
 {[109,435].map((x)=><g key={x} transform={`translate(${x} 222)`}><circle r="44" fill={C.ink}/><circle r="24" fill="#D7E0ED"/><g transform={`rotate(${frame*13})`} stroke="#8394AC" strokeWidth="5"><path d="M-18 0H18M0 -18V18"/></g><circle r="7" fill={C.ink}/></g>)}
</g>;

export const Wrist:React.FC<{frame:number;x?:number;y?:number;scale?:number}>=({frame,x=0,y=0,scale=1})=><g transform={`translate(${x} ${y}) scale(${scale})`}>
 <path d="M-100 211Q23 156 108 158L349 199L350 290L104 278L-100 347Z" fill="#C69073"/>
 <path d="M-100 300L111 249L350 266L350 291L111 283L-100 352Z" fill="#AA765E" opacity=".6"/>
 <g fill="#C69073">
  <path d="M395 205C428 197 466 195 496 196C508 195 520 201 519 210C518 220 507 222 496 220L412 229Z"/>
  <path d="M422 222L516 222C528 221 536 228 535 237C534 247 526 250 516 247L424 249Z"/>
  <path d="M425 246L506 250C518 251 525 258 523 267C521 277 512 279 502 276L412 270Z"/>
  <path d="M410 268L478 277C490 279 499 285 496 294C493 303 484 306 473 300L399 290Z"/>
  <path d="M335 200C358 195 382 190 403 198C426 205 439 227 435 254C432 276 415 290 394 296C374 301 350 291 338 287Z"/>
 </g>
 <path d="M340 276C363 284 382 288 399 283L423 271C416 285 406 293 394 297C374 301 350 292 338 287Z" fill="#AA765E" opacity=".32"/>
 <path d="M361 207C369 189 385 178 399 172C409 167 420 170 425 178C430 186 424 192 417 196L394 215C380 226 367 225 361 217Z" fill="#C69073"/>
 <g fill="none" stroke="#9E6954" strokeWidth="2.6" strokeLinecap="round" opacity=".65">
  <path d="M387 206C380 215 378 226 381 236"/>
  <path d="M408 225Q415 234 414 245"/>
  <path d="M463 203Q466 210 463 216M476 228Q479 235 477 242M470 254Q473 261 470 269M452 279Q455 285 452 291"/>
 </g>
 <path d="M104 145Q135 130 179 143L170 301Q137 309 104 293Z" fill={C.ink}/>
 <rect x="89" y="172" width="111" height="103" rx="29" fill="#31415D" transform="rotate(8 140 220)"/>
 <rect x="98" y="179" width="93" height="89" rx="23" fill="#07142D" transform="rotate(8 140 220)"/>
 <g transform="translate(105 180) rotate(8 35 40)"><Text x={38} y={23} size={10} anchor="middle" fill="#CAD7FD">CONNECTED</Text><Wave x={5} y={36} w={65} h={23} frame={frame} color="#8FACFF"/><circle cx="62" cy="69" r="3" fill="#73D5C0"/></g>
</g>;

export const Phone:React.FC<{frame:number;confirmed?:boolean}>=({frame,confirmed=false})=><g>
 <rect x="9" y="14" width="254" height="490" rx="43" fill={C.ink} opacity=".1"/>
 <rect width="254" height="490" rx="43" fill={C.ink}/><rect x="11" y="11" width="232" height="468" rx="34" fill={C.white}/>
 <rect x="81" y="18" width="92" height="22" rx="11" fill={C.ink}/><Text x={29} y={69} size={13} weight={800}>09:41</Text>
 <image href={staticFile('brand/neurasign-light.svg')} x="24" y="89" width="158" height="51"/>
 <Text x={26} y={176} size={24} weight={800}>Maya Chen</Text>
 <Pill x={24} y={193} w={148} label={confirmed?'New assignment':'Connected'} size={14} h={32} fill={C.pale}/>
 {confirmed?<g><rect x="23" y="246" width="208" height="126" rx="16" fill={C.pale}/><Check x={38} y={266} size={23}/><Text x={38} y={316} size={20} weight={800}>Trauma bay 02</Text><Text x={38} y={344} size={14} fill={C.muted}>Coordinator confirmed</Text></g>:<g><Wave x={25} y={250} w={198} h={61} frame={frame}/><Text x={26} y={350} size={40} weight={800}>74</Text><Text x={89} y={350} size={16} fill={C.muted}>bpm</Text><Text x={26} y={390} size={16} fill={C.muted}>5 available signal streams</Text><Text x={26} y={417} size={14} fill={C.muted}>Secure team connection</Text></g>}
 <rect x="85" y="457" width="84" height="5" rx="3" fill="#C2CBDA"/>
</g>;

export const FlowLine:React.FC<{x1:number;x2:number;y:number;frame:number;at?:number;color?:string}>=({x1,x2,y,frame,at=0,color=C.blue})=>{
 const p=mix(frame,at,at+24);const length=x2-x1;
 return <g opacity={p}><path d={`M${x1} ${y}H${x2}`} stroke={color} strokeWidth="3" opacity=".25"/><path d={`M${x2-11} ${y-8}L${x2} ${y}L${x2-11} ${y+8}`} fill="none" stroke={color} strokeWidth="3"/>{[0,1,2].map(i=><circle key={i} cx={x1+(((frame-at)/64+i/3)%1+1)%1*length} cy={y} r="5" fill={color}/>)}</g>;
};

export const Cursor:React.FC<{x:number;y:number;click?:number}>=({x,y,click=0})=><g transform={`translate(${x} ${y})`}>
 {click>0&&<circle r={12+click*35} fill="none" stroke={C.blue} strokeWidth="3" opacity={1-click}/>}
 <path d="M0 0L0 37L10 28L20 46L29 41L19 23L33 23Z" fill={C.white} stroke={C.ink} strokeWidth="2.5" strokeLinejoin="round"/>
</g>;

export const RingScore:React.FC<{x:number;y:number;value:number;label:string;frame:number;at:number;color?:string}>=({x,y,value,label,frame,at,color=C.blue})=><g>
 <circle cx={x} cy={y} r="52" fill="none" stroke="#E6EBF3" strokeWidth="9"/>
 <circle cx={x} cy={y} r="52" fill="none" stroke={color} strokeWidth="9" strokeLinecap="round" strokeDasharray={`${326.7*value/100*mix(frame,at,at+32)} 326.7`} transform={`rotate(-90 ${x} ${y})`}/>
 <Text x={x} y={y+12} size={34} anchor="middle" weight={800}>{Math.round(value*mix(frame,at,at+32))}</Text><Text x={x} y={y+88} size={19} anchor="middle" fill={C.muted}>{label}</Text>
</g>;
