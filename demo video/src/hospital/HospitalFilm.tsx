import React from 'react';
import {AbsoluteFill,Audio,Sequence,staticFile,useCurrentFrame} from 'remotion';
import '@fontsource/manrope/400.css';
import '@fontsource/manrope/500.css';
import '@fontsource/manrope/600.css';
import '@fontsource/manrope/700.css';
import '@fontsource/manrope/800.css';
import {Doctor,Patient} from './Characters';
import {HospitalExterior,HospitalInterior,Stretcher} from './Environment';
import {ConstructionSite,IndustrialOperations,ControlRoom} from './Workplaces';
import {C,Text,Enter,Pill,Check,Pulse,SignalIcon,PEOPLE,Wave,mix,linear} from './Design';
import {Ambulance,Wrist,Phone,FlowLine,Cursor,RingScore} from './Props';

const Stage:React.FC<{children:React.ReactNode;dark?:boolean}>=({children,dark=false})=><AbsoluteFill style={{background:dark?C.navy:C.paper}}><svg viewBox="0 0 1920 1080" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" style={{fontFamily:'Manrope, Arial, sans-serif',overflow:'hidden'}}>{children}</svg></AbsoluteFill>;
const Header:React.FC<{dark?:boolean;chapter?:string;context?:string}>=({dark=false,chapter,context='Hospital example · Simulated signals'})=><g>
 <image href={staticFile(`brand/neurasign-${dark?'dark':'light'}.svg`)} x="62" y="34" width="233" height="74"/>
 <Text x={1845} y={77} size={21} fill={dark?'#A9B9D5':C.muted} anchor="end">{context}</Text>
 {chapter&&<Text x={78} y={145} size={19} spacing={2} weight={700} fill={dark?C.ice:C.blue}>{chapter}</Text>}
</g>;
const Eyebrow:React.FC<{children:React.ReactNode;dark?:boolean}>=({children,dark=false})=><Text x={80} y={200} size={22} fill={dark?C.ice:C.blue} weight={800} spacing={2}>{children}</Text>;

const Establish:React.FC=()=>{
 const f=useCurrentFrame();const zoom=mix(f,65,150,1,1.055);const ax=mix(f,0,115,-700,650);
 return <Stage><g transform={`translate(${960-960*zoom} ${600-600*zoom}) scale(${zoom})`}><rect width="1920" height="1080" fill="#EDF1F5"/><g transform="translate(0 76) scale(1 .93)"><HospitalExterior frame={f}/></g><g transform={`translate(${ax} 753) scale(.79)`}><Ambulance frame={f}/></g></g><Header/>
 <Enter frame={f} at={7}><Text x={80} y={184} size={80} weight={800}>Every second</Text><Text x={80} y={274} size={80} weight={800} fill={C.blue}>matters.</Text></Enter>
 <Enter frame={f} at={32}><Pill x={80} y={324} w={207} label="HOSPITAL / 09:41" size={18} h={39} fill={C.white}/></Enter>
 <g opacity={mix(f,101,117)}><path d="M80 1011H260" stroke={C.blue} strokeWidth="3"/><Text x={280} y={1020} size={26} fill={C.ink}>A team. A patient. A moment to act.</Text></g>
 </Stage>;
};

const Arrival:React.FC=()=>{
 const f=useCurrentFrame();const x=mix(f,0,114,-700,375);const stride=f<114?f+9:123;const s=.87;
 return <Stage><HospitalInterior frame={f} doorOpen={mix(f,0,30)} variant="arrival"/>
 <Header/><Enter frame={f} at={5}><Text x={80} y={210} size={70} weight={800}>One patient. <tspan fill={C.blue}>Three responders.</tspan></Text></Enter>
 <g transform="translate(1230 410) scale(.82)"><Doctor kind="omar" gaze="left" frame={f+20} expression="focused" pose="tablet"/></g>
 <g transform="translate(1450 411) scale(.82)"><Doctor kind="emma" gaze="left" frame={f+44} expression="tired"/></g>
 <g transform="translate(1635 413) scale(.82)"><Doctor kind="maya" gaze="left" frame={f} expression="focused" pose={f>124?'ready':'idle'}/></g>
 <g transform={`translate(${x-185} 350) scale(.99)`}><Doctor kind="paramedic" gaze="right" frame={stride} pose="push" expression="focused"/></g>
 <g transform={`translate(${x} 640) scale(${s})`}><Stretcher frame={stride}><g transform="translate(82 -146) scale(.99)"><Patient frame={f}/></g></Stretcher></g>
 <Enter frame={f} at={115}><Pill x={1200} y={953} w={607} label="Trauma team requested" fill={C.blue} color={C.white} size={28} h={64}/></Enter>
 </Stage>;
};

const DoctorSignals:React.FC=()=>{
 const f=useCurrentFrame();const centers=[340,960,1580];
 return <Stage><Header chapter="01 / THE PEOPLE BEHIND THE SIGNALS"/>
 <Enter frame={f}><Text x={80} y={251} size={74} weight={800}>One team. Different signals.</Text></Enter>
 {PEOPLE.map((p,i)=>{const cx=centers[i];const show=mix(f,i*8,i*8+22);const bob=Math.sin(f/28+i)*3;return <g key={p.id} opacity={show} transform={`translate(0 ${(1-show)*50})`}>
 <circle cx={cx} cy={573} r={219} fill={i===2?'#DCE5FF':i===1?'#E0ECE8':'#E9E9E4'}/>
 <path d={`M${cx-219} 579A219 219 0 0 1 ${cx+219} 579`} stroke={p.color} strokeWidth="2" fill="none" opacity=".15"/>
 <g transform={`translate(${cx-128} ${355+bob}) scale(.99)`}><Doctor kind={p.id} frame={f+i*29} pose={p.id==='omar'?'tablet':'idle'} expression={p.id==='emma'?'tired':'focused'}/></g>
 <g opacity={mix(f,22+i*6,40+i*6)}><path d={`M${cx+47} 673V707Q${cx+47} 721 ${cx+70} 721V742`} fill="none" stroke={p.color} strokeWidth="2" strokeDasharray="4 5" opacity=".6"/><Pulse x={cx+47} y={673} frame={f+i*13} color={p.color} r={12}/></g><rect x={cx-254} y="732" width="508" height="285" rx="25" fill={C.white} stroke={C.line} strokeWidth="1.4"/>
 <Text x={cx-224} y={778} size={32} weight={800}>{p.name}</Text><Text x={cx-224} y={811} size={20} fill={C.muted}>Trauma physician · Wearable connected</Text>
 <Wave x={cx-224} y={830} w={444} h={49} frame={f*(1+i*.16)} seed={i*.3} color={p.color}/>
 <Enter frame={f} at={30+i*5}><SignalIcon x={cx-224} y={901} color={p.color} scale={.74}/><Text x={cx-183} y={926} size={40} weight={800}>{p.hr}<tspan fontSize="18" fontWeight="500" fill={C.muted}> bpm</tspan></Text></Enter>
 <Enter frame={f} at={72+i*5}><Text x={cx+40} y={926} size={40} weight={800}>{p.hrv}<tspan fontSize="18" fontWeight="500" fill={C.muted}> ms HRV</tspan></Text></Enter>
 <Enter frame={f} at={112+i*5}><Text x={cx-224} y={977} size={19} fill={C.muted}>Movement</Text>{Array.from({length:17},(_,n)=><rect key={n} x={cx-93+n*18} y={965-(Math.sin(n*1.7+f/14+i)+1)*6} width="9" height={11+(Math.sin(n*1.7+f/14+i)+1)*6} rx="3" fill={p.color} opacity=".65"/>)}</Enter>
 </g>})}
 </Stage>;
};

const SignalsToContext:React.FC=()=>{
 const f=useCurrentFrame();const context=mix(f,112,136);const intro=1-mix(f,107,130);
 return <Stage dark><Header dark chapter="02 / FROM SIGNALS TO CONTEXT"/>
 <Enter frame={f}><Text x={80} y={245} size={74} fill={C.white} weight={800}>{f<128?'Connected, in one place.':'Understand the team’s condition.'}</Text></Enter>
 <g opacity={intro} transform={`translate(0 ${-context*40})`}>
 <g transform="translate(210 323) scale(.95)"><Wrist frame={f}/></g>
 <FlowLine x1={740} x2={800} y={559} frame={f} at={17} color="#8BA6FF"/>
 <g transform="translate(865 316) scale(.9)"><Phone frame={f}/></g>
 <FlowLine x1={1140} x2={1300} y={559} frame={f} at={39} color="#8BA6FF"/>
 <Enter frame={f} at={46}><rect x="1360" y="416" width="380" height="285" rx="34" fill="#1D2E50" stroke="#3C547E" strokeWidth="2"/><image href={staticFile('brand/neurasign-dark.svg')} x="1404" y="472" width="294" height="94"/><Text x={1550} y={623} size={27} anchor="middle" fill={C.ice}>Team intelligence</Text></Enter>
 <Text x={410} y={860} size={29} anchor="middle" fill={C.white} weight={700}>Wearable</Text><Text x={978} y={860} size={29} anchor="middle" fill={C.white} weight={700}>Phone</Text><Text x={1550} y={860} size={29} anchor="middle" fill={C.white} weight={700}>NEURASIGN</Text>
 <Enter frame={f} at={62}><Text x={960} y={959} size={24} anchor="middle" fill="#9EAFCC">Heart rate · Heart rate variability · Skin conductance · Temperature · Movement</Text></Enter>
 </g>
 <g opacity={context} transform={`translate(0 ${(1-context)*30})`}>
 {[{label:'Stress',sub:'Estimated activation',value:24,type:'hr'},{label:'Fatigue',sub:'Estimated tiredness',value:18,type:'hrv'},{label:'Workload',sub:'Estimated demand',value:29,type:'eda'},{label:'Readiness',sub:'Estimated capacity',value:86,type:'move'}].map((m,i)=>{const xx=82+i*451;const p=mix(f,129+i*8,160+i*8);return <g key={m.label} opacity={p} transform={`translate(0 ${(1-p)*32})`}><rect x={xx} y="397" width="415" height="440" rx="28" fill={i===3?C.blue:'#1A2944'} stroke={i===3?'#809AFF':'#344765'} strokeWidth="1.5"/><SignalIcon x={xx+35} y={438} type={m.type} color={i===3?C.white:'#A3B9FF'} scale={1.3}/><Text x={xx+35} y={548} size={38} fill={C.white} weight={700}>{m.label}</Text><Text x={xx+35} y={645} size={82} fill={C.white} weight={800}>{Math.round(m.value*p)}<tspan fontSize="25" fontWeight="500" fill="#AABCDB"> / 100</tspan></Text><rect x={xx+36} y="690" width="344" height="8" rx="4" fill="#8798BA" opacity=".3"/><rect x={xx+36} y="690" width={344*m.value/100*p} height="8" rx="4" fill={i===3?C.white:'#8BA6FF'}/><Text x={xx+35} y={761} size={21} fill={i===3?'#E2E9FF':'#AABCDB'}>{m.sub}</Text></g>})}
 <Text x={960} y={907} size={25} anchor="middle" fill={C.ice}>Maya’s illustrative estimates</Text><Text x={960} y={955} size={22} anchor="middle" fill="#9EAFCC">Lower stress, fatigue and workload · Higher readiness</Text>
 </g>
 </Stage>;
};

const TeamContext:React.FC=()=>{
 const f=useCurrentFrame();return <Stage><Header chapter="03 / SAME SKILLS. DIFFERENT CURRENT CONTEXT."/><Enter frame={f}><Text x={80} y={244} size={74} weight={800}>Who has capacity right now?</Text></Enter>
 {PEOPLE.map((p,i)=>{const x=80+i*610;const highlight=i===2;const active=f>i*47;return <g key={p.id}>
 <rect x={x} y="310" width="570" height="677" rx="30" fill={C.white} stroke={highlight&&f>102?C.blue:C.line} strokeWidth={highlight&&f>102?4:1.5}/>
 <circle cx={x+113} cy={430} r="77" fill={highlight?C.pale:'#F0F1ED'}/><clipPath id={`portrait-${p.id}`}><circle cx={x+113} cy={430} r="77"/></clipPath><g clipPath={`url(#portrait-${p.id})`}><g transform={`translate(${x+21} 366) scale(.72)`}><Doctor kind={p.id} frame={f} expression={p.id==='emma'?'tired':'calm'}/></g></g>
 <Text x={x+217} y={414} size={32} weight={800}>{p.short}</Text><Text x={x+217} y={452} size={21} fill={C.muted}>Trauma qualified</Text><Check x={x+458} y={433} size={22} color={C.muted}/>
 <Enter frame={f} at={i*38+12}><Pill x={x+32} y={532} w={505} label={p.status} fill={highlight?C.pale:'#F1F2F4'} color={highlight?C.blue:C.ink} size={25} h={57}/></Enter>
 {[['Stress',p.stress],['Fatigue',p.fatigue],['Workload',p.workload],['Readiness',p.readiness]].map(([label,val],j)=><g key={String(label)} opacity={mix(f,i*15+10,i*15+25)}><Text x={x+33} y={646+j*73} size={24} fill={C.muted}>{label}</Text><rect x={x+215} y={632+j*73} width="243" height="9" rx="4.5" fill="#E7ECF4"/><rect x={x+215} y={632+j*73} width={243*Number(val)/100*mix(f,15+i*15,60+i*15)} height="9" rx="4.5" fill={highlight?C.blue:((i===0&&j===2)||(i===1&&j===1))?C.amber:'#96A5BE'}/><Text x={x+524} y={646+j*73} size={24} anchor="end" weight={800}>{val}</Text></g>)}
 <g opacity={active?1:.35}><Text x={x+32} y={945} size={21} fill={highlight?C.blue:C.muted} weight={700}>{p.reason}</Text></g>
 </g>})}<Text x={960} y={1041} size={20} anchor="middle" fill={C.muted}>Illustrative estimates / 100 · Context for a human decision</Text></Stage>;
};

const Evaluation:React.FC=()=>{
 const f=useCurrentFrame();const selected=mix(f,126,153);return <Stage dark><Header dark chapter="04 / INCIDENT RECEIVED"/>
 <Enter frame={f}><rect x="80" y="182" width="1760" height="157" rx="26" fill="#1D2E4C" stroke="#52658A" strokeWidth="1.5"/><Pulse x={125} y={256} frame={f} color="#E2B575" r={17}/><Text x={163} y={236} size={20} fill="#B5C4DE" weight={700}>HOSPITAL INCIDENT FEED</Text><Text x={162} y={294} size={39} fill={C.white} weight={800}>Patient arrival · Trauma bay 02</Text><Pill x={1562} y={229} w={232} label="Doctor requested" fill="#394968" color={C.white} size={20} h={48}/></Enter>
 <Enter frame={f} at={19}><Text x={83} y={425} size={48} fill={C.white} weight={700}>Find the strongest available match.</Text></Enter>
 <Enter frame={f} at={29}><Text x={117} y={506} size={20} fill="#9FB0CD">TEAM MEMBER</Text><Text x={669} y={506} size={20} fill="#9FB0CD">RELEVANT SKILLS</Text><Text x={1032} y={506} size={20} fill="#9FB0CD">AVAILABILITY</Text><Text x={1463} y={506} size={20} fill="#9FB0CD">CURRENT CONTEXT</Text></Enter>
 {PEOPLE.map((p,i)=>{const y=531+i*129;const picked=i===2;return <Enter key={p.id} frame={f} at={35+i*13}>
 <rect x="80" y={y} width="1760" height="112" rx="18" fill={picked&&f>126?'#203D85':'#16253F'} stroke={picked&&f>126?'#799CFF':'#30425F'} strokeWidth={picked&&f>126?2:1}/>
 <circle cx={130} cy={y+56} r="24" fill={p.color}/><Text x={130} y={y+65} size={22} anchor="middle" fill={C.white} weight={700}>{p.short[0]}</Text><Text x={178} y={y+67} size={30} fill={C.white} weight={700}>{p.name}</Text>
 <g opacity={mix(f,50+i*8,68+i*8)}><Check x={676} y={y+43} size={24} color="#96ACE6"/><Text x={716} y={y+65} size={24} fill="#D2DEF5">Trauma trained</Text></g>
 <g opacity={mix(f,86+i*7,103+i*7)}><Text x={1032} y={y+65} size={24} fill={i===0?'#E6BA83':'#D2DEF5'}>{i===0?'Already assigned':'Available'}</Text></g>
 <g opacity={mix(f,110+i*5,128+i*5)}><Text x={1463} y={y+65} size={24} fill={picked?C.white:i===1?'#E6BA83':'#AFC0DD'}>{i===0?'High workload':i===1?'Fatigue check-in':'Ready to support'}</Text></g>
 </Enter>})}
 <Enter frame={f} at={155}><Check x={95} y={987} color="#A7C1FF" size={29}/><Text x={143} y={1010} size={28} fill={C.ice} weight={600}>Recommendation prepared for coordinator review</Text></Enter>
 <g opacity={1-selected}><rect x="80" y={520+((f*4)%390)} width="1760" height="2" fill="#ABC3FF" opacity=".2"/></g>
 </Stage>;
};

const Recommendation:React.FC=()=>{
 const f=useCurrentFrame();return <Stage><Header chapter="05 / A RECOMMENDATION YOU CAN UNDERSTAND"/>
 <circle cx="457" cy="622" r="290" fill={C.pale}/><circle cx="457" cy="622" r={312+Math.sin(f/24)*4} fill="none" stroke="#CEDAFF" strokeWidth="2"/><circle cx="457" cy="622" r="353" fill="none" stroke="#E4E9F3" strokeWidth="1.5"/>
 <g transform={`translate(303 ${343-mix(f,0,25,20,0)}) scale(1.17)`}><Doctor kind="maya" gaze="center" frame={f} pose="ready" expression="focused"/></g>
 <Enter frame={f} at={12}><Pill x={289} y={952} w={335} label="RECOMMENDED MATCH" size={20} fill={C.blue} color={C.white} h={53}/></Enter>
 <Enter frame={f}><Text x={850} y={305} size={29} fill={C.blue} weight={800}>READY TO RESPOND</Text><Text x={850} y={393} size={76} weight={800}>Dr. Maya Chen</Text><Text x={850} y={445} size={29} fill={C.muted}>Trauma physician</Text></Enter>
 {[['Relevant training','Trauma response skills'],['Available now','No active assignment'],['Supportive current indicators','Lower fatigue · Higher readiness']].map(([a,b],i)=><Enter key={a} frame={f} at={24+i*30}><circle cx="876" cy={542+i*128} r="25" fill={C.pale}/><Check x={864} y={529+i*128} size={25} progress={mix(f,30+i*30,48+i*30)}/><Text x={924} y={549+i*128} size={31} weight={700}>{a}</Text><Text x={924} y={587+i*128} size={23} fill={C.muted}>{b}</Text></Enter>)}
 <Enter frame={f} at={128}><rect x="850" y="922" width="988" height="79" rx="16" fill="#EBEFF6"/><Text x={881} y={971} size={27} weight={700}>Final decision: the coordinator</Text><Check x={1778} y={945} size={29}/></Enter>
 </Stage>;
};

const Response:React.FC=()=>{
 const f=useCurrentFrame();const moving=mix(f,83,155);const exit=mix(f,152,170);const patientX=1230;
 return <Stage><HospitalInterior frame={f} doorOpen={0} variant="station"/>
 <Header/>
 <g opacity={1-exit}>
 <g transform="translate(167 452) scale(.84)"><Doctor kind="coordinator" frame={f} pose="tablet" expression="focused"/></g>
 <g transform={`translate(${616+moving*548} ${378+moving*15}) scale(.94)`}><Doctor kind="maya" gaze="right" frame={f>83?f-83:f} pose={f>83&&f<155?'walk':'ready'} expression="focused"/></g>
 <g transform={`translate(${patientX} 698) scale(.73)`}><Stretcher frame={0}><g transform="translate(82 -146) scale(.99)"><Patient frame={f}/></g></Stretcher></g>
 </g>
 <g opacity={1-mix(f,84,101)}>
 <Enter frame={f}><rect x="520" y="179" width="880" height="193" rx="25" fill={C.white} stroke={C.line} strokeWidth="2"/><Text x={555} y={238} size={32} weight={800}>Maya Chen → Trauma bay 02</Text><rect x="555" y="274" width="813" height="65" rx="12" fill={f>31?C.teal:C.blue}/>{f>31&&<Check x={733} y={293} color={C.white} size={26}/>}<Text x={970} y={315} size={27} fill={C.white} anchor="middle" weight={800}>{f>31?'Assignment confirmed':'Confirm recommendation'}</Text></Enter>
 <g opacity={1-mix(f,46,58)}><Cursor x={mix(f,9,28,1455,1247)} y={mix(f,9,28,445,312)} click={f>31?linear(f,31,48):0}/></g>
 </g>
 <g opacity={mix(f,47,62)*(1-mix(f,88,108))} transform={`translate(${1330+mix(f,47,62,70,0)} 370) scale(.83)`}><Phone frame={f} confirmed/></g>
 <g opacity={mix(f,102,122)}><Text x={80} y={207} size={65} weight={800}>Decision confirmed. <tspan fill={C.blue}>Help is on the way.</tspan></Text></g>
 <g opacity={exit}><rect x="0" y="0" width="1920" height="1080" fill={C.pale}/><g transform="translate(1230 695) scale(.79)"><Stretcher frame={0}><g transform="translate(82 -146) scale(.99)"><Patient frame={f}/></g></Stretcher></g><g transform="translate(946 320) scale(1.1)"><Doctor kind="maya" gaze="right" frame={f} pose="ready" expression="calm"/></g><Text x={80} y={412} size={79} weight={800}>Support your people.</Text><Text x={80} y={511} size={79} weight={800} fill={C.blue}>When it matters.</Text></g>
 </Stage>;
};

const BeyondHospitals:React.FC=()=>{
 const f=useCurrentFrame();const expand=mix(f,133,153);
 const places=[
  {name:'Construction sites',art:ConstructionSite},
  {name:'Industrial operations',art:IndustrialOperations},
  {name:'Control rooms',art:ControlRoom},
 ];
 return <Stage><Header chapter="06 / BEYOND THE HOSPITAL" context="One platform · Many workplaces"/>
  <g opacity={1-expand} transform={`translate(0 ${-expand*28})`}>
   <Enter frame={f} at={3}><Text x={80} y={376} size={79} weight={800}>Hospital care.</Text><Text x={80} y={475} size={79} weight={800} fill={C.blue}>One example.</Text></Enter>
   <Enter frame={f} at={21}><Text x={84} y={577} size={30} fill={C.muted}>A much wider purpose.</Text></Enter>
   <clipPath id="hospital-example-window"><rect x="952" y="279" width="885" height="606" rx="35"/></clipPath>
   <g clipPath="url(#hospital-example-window)"><rect x="952" y="279" width="885" height="606" fill="#E8EEF2"/><g transform="translate(865 286) scale(.58)"><HospitalExterior frame={f}/></g></g>
   <rect x="952" y="279" width="885" height="606" rx="35" stroke="#D8DFE5" strokeWidth="2" fill="none"/>
   <Enter frame={f} at={38}><Pill x={1159} y={919} w={470} label="The scenario you just watched" size={23} h={58} fill={C.pale} color={C.blue}/></Enter>
  </g>
  <g opacity={expand} transform={`translate(0 ${(1-expand)*24})`}>
   <Text x={80} y={254} size={73} weight={800}>For demanding workplaces.</Text>
   <Text x={83} y={327} size={38} weight={600} fill={C.blue}>Where the stakes are real.</Text>
   {places.map(({name,art:Art},i)=>{const x=80+i*610;const p=mix(f,139+i*8,164+i*8);return <g key={name} opacity={p} transform={`translate(0 ${(1-p)*24})`}>
    <clipPath id={`workplace-window-${i}`}><rect x={x} y="405" width="570" height="432" rx="24"/></clipPath>
    <g clipPath={`url(#workplace-window-${i})`}><g transform={`translate(${x-11} 405) scale(.99)`}><Art frame={Math.max(0,f-143)+i*17}/></g></g>
    <rect x={x} y="405" width="570" height="432" rx="24" stroke="#D4DEE4" strokeWidth="2" fill="none"/>
    <Text x={x+285} y={903} anchor="middle" size={32} weight={700}>{name}</Text>
   </g>})}
   <Enter frame={f} at={223}><path d="M847 971H1073" stroke={C.blue} strokeWidth="3" strokeLinecap="round"/><Text x={960} y={1030} size={27} anchor="middle" fill={C.muted}>One platform. Different workplaces.</Text></Enter>
  </g>
 </Stage>;
};

const Closing:React.FC=()=>{
 const f=useCurrentFrame();const p=mix(f,0,23);return <Stage dark>
 <g opacity=".13" stroke="#789AFF" fill="none"><circle cx="960" cy="474" r={300+f*.3}/><circle cx="960" cy="474" r={429+f*.3}/><circle cx="960" cy="474" r={560+f*.3}/></g>
 <g opacity={p} transform={`translate(0 ${(1-p)*29})`}><image href={staticFile('brand/neurasign-dark.svg')} x="568" y="271" width="784" height="250"/>
 <Text x={960} y={617} size={62} fill={C.white} weight={600} anchor="middle">Understand your team.</Text><Text x={960} y={702} size={62} fill={C.ice} weight={600} anchor="middle">Respond with confidence.</Text></g>
 <Enter frame={f} at={34}><path d="M919 801H1001" stroke="#7090FF" strokeWidth="4" strokeLinecap="round"/><Text x={960} y={945} size={25} fill="#9FAFCE" anchor="middle">Wearables → Phone → Team intelligence</Text><Text x={960} y={1004} size={19} fill="#7C8EAE" anchor="middle">Illustrative scenario · Simulated signals · Human-confirmed recommendation</Text></Enter>
 </Stage>;
};

/** The hospital story is an explicitly simulated concept, not a recording of the application. */
export const HospitalFilm:React.FC<{audio?:boolean}>=({audio=true})=>{
 return <AbsoluteFill style={{background:C.paper}}>
 {audio&&<Audio src={staticFile('audio/hospital-mix-76s.wav')}/>}
 <Sequence from={0} durationInFrames={150}><Establish/></Sequence>
 <Sequence from={150} durationInFrames={180}><Arrival/></Sequence>
 <Sequence from={330} durationInFrames={210}><DoctorSignals/></Sequence>
 <Sequence from={540} durationInFrames={240}><SignalsToContext/></Sequence>
 <Sequence from={780} durationInFrames={210}><TeamContext/></Sequence>
 <Sequence from={990} durationInFrames={240}><Evaluation/></Sequence>
 <Sequence from={1230} durationInFrames={240}><Recommendation/></Sequence>
 <Sequence from={1470} durationInFrames={210}><Response/></Sequence>
 <Sequence from={1680} durationInFrames={450}><BeyondHospitals/></Sequence>
 <Sequence from={2130} durationInFrames={150}><Closing/></Sequence>
 </AbsoluteFill>;
};
