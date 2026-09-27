import React from 'react';
import {Easing, interpolate} from 'remotion';

export const C={ink:'#14213B',blue:'#4263EB',brand:'#2854E8',paper:'#F7F6F2',pale:'#E7EDFF',muted:'#69768B',line:'#D7DEEA',white:'#FFFFFF',teal:'#2B807C',amber:'#CC873E',navy:'#0D172C',ice:'#BACAFE'};
export const ease=Easing.bezier(.2,.8,.2,1);
export const mix=(f:number,a:number,b:number,from=0,to=1)=>interpolate(f,[a,b],[from,to],{extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:ease});
export const linear=(f:number,a:number,b:number,from=0,to=1)=>interpolate(f,[a,b],[from,to],{extrapolateLeft:'clamp',extrapolateRight:'clamp'});
export const Text:React.FC<{x:number;y:number;size?:number;weight?:number;fill?:string;anchor?:'start'|'middle'|'end';opacity?:number;spacing?:number;children:React.ReactNode}> = ({x,y,size=30,weight=500,fill=C.ink,anchor='start',opacity=1,spacing,children})=><text x={x} y={y} fontSize={size} fontWeight={weight} fill={fill} textAnchor={anchor} opacity={opacity} letterSpacing={spacing??(size>60?-size*.045:0)} fontFamily="Manrope, Arial, sans-serif">{children}</text>;
export const Enter:React.FC<{frame:number;at?:number;children:React.ReactNode;distance?:number}>=({frame,at=0,children,distance=25})=><g opacity={mix(frame,at,at+17)} transform={`translate(0 ${(1-mix(frame,at,at+24))*distance})`}>{children}</g>;
export const Check:React.FC<{x:number;y:number;size?:number;color?:string;progress?:number}>=({x,y,size=24,color=C.blue,progress=1})=><g transform={`translate(${x} ${y}) scale(${size/24})`}><path d="M3 12 L9 18 L21 5" fill="none" stroke={color} strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" pathLength="1" strokeDasharray="1" strokeDashoffset={1-progress}/></g>;
export const Pulse:React.FC<{x:number;y:number;frame:number;color?:string;r?:number}>=({x,y,frame,color=C.blue,r=16})=>{const p=((frame%45)+45)%45/45;return <g><circle cx={x} cy={y} r={r} fill={color} opacity=".1"/><circle cx={x} cy={y} r={r+28*p} fill="none" stroke={color} strokeWidth="2" opacity={(1-p)*.45}/><circle cx={x} cy={y} r="5" fill={color}/></g>};
export const Pill:React.FC<{x:number;y:number;w:number;label:string;fill?:string;color?:string;size?:number;h?:number}>=({x,y,w,label,fill=C.pale,color=C.blue,size=22,h=44})=><g><rect x={x} y={y} width={w} height={h} rx={h/2} fill={fill}/><Text x={x+w/2} y={y+h*.69} size={size} fill={color} weight={700} anchor="middle">{label}</Text></g>;
export const SignalIcon:React.FC<{x:number;y:number;type?:string;color?:string;scale?:number}>=({x,y,type='hr',color=C.blue,scale=1})=><g transform={`translate(${x} ${y}) scale(${scale})`} stroke={color} strokeWidth="2.8" fill="none" strokeLinecap="round" strokeLinejoin="round">{type==='hr'?<path d="M0 14H7L11 3L17 27L23 11L27 14H35"/>:type==='temp'?<><path d="M14 19V4a5 5 0 0 1 10 0v15a9 9 0 1 1-10 0Z"/><path d="M19 9v17"/></>:type==='eda'?<><path d="M0 6Q8 -1 16 6T32 6M0 17Q8 10 16 17T32 17M0 28Q8 21 16 28T32 28"/></>:type==='move'?<><path d="M17 0v32M1 16h32M17 0l-5 5m5-5 5 5M1 16l5-5m-5 5 5 5M33 16l-5-5m5 5-5 5M17 32l-5-5m5 5 5-5"/></>:<path d="M0 19Q8-2 16 15T33 13M0 29Q8 8 16 25T33 23"/>}</g>;

// Fictional values designed for this concept film; not recorded employee data.
export const PEOPLE=[
 {id:'omar' as const,name:'Dr. Omar Reed',short:'Omar',role:'Trauma physician',hr:104,hrv:24,temp:'33.4',eda:'5.2',stress:68,fatigue:39,workload:88,readiness:42,status:'With another patient',reason:'Already assigned',color:C.ink},
 {id:'emma' as const,name:'Dr. Emma Cruz',short:'Emma',role:'Trauma physician',hr:88,hrv:31,temp:'33.0',eda:'2.6',stress:42,fatigue:73,workload:48,readiness:38,status:'Check-in suggested',reason:'Elevated fatigue estimate',color:C.teal},
 {id:'maya' as const,name:'Dr. Maya Chen',short:'Maya',role:'Trauma physician',hr:74,hrv:58,temp:'32.8',eda:'1.5',stress:24,fatigue:18,workload:29,readiness:86,status:'Available',reason:'Available · Relevant skills',color:C.blue},
];
export type Person=typeof PEOPLE[number];

export const Wave:React.FC<{x:number;y:number;w:number;h?:number;frame:number;color?:string;seed?:number;reveal?:number}> = ({x,y,w,h=70,frame,color=C.blue,seed=0,reveal=1})=>{
 const points=Array.from({length:121},(_,i)=>{const p=i/120;const t=p*5.2-frame/100+seed;const beat=Math.exp(-Math.pow(((t%1)+1)%1-.28,2)/.0012)*.9-Math.exp(-Math.pow(((t%1)+1)%1-.4,2)/.003)*.4;return `${x+p*w},${y+h*.5-(Math.sin(t*6.283)*.11+beat)*h*.7}`;}).join(' ');
 return <g><path d={`M${x} ${y+h*.5}H${x+w}`} stroke={color} opacity=".13"/><polyline points={points} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" opacity={reveal}/></g>;
};
