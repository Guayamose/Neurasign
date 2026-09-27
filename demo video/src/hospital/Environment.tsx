import React, {useId} from 'react';

/** Original flat-vector sets. All positions use a 1920 × 1080 stage. */
const P = {
  cream: '#F7F6F2', paper: '#FFFFFF', navy: '#14213B', cobalt: '#4263EB',
  powder: '#E7EDFF', paleBlue: '#D4DFF2', glass: '#B4C8E2', steel: '#8598AE',
  warm: '#E5DCCB', floor: '#E9E6DF', line: '#D1D3D8', teal: '#76A89D',
  tealDark: '#477A71', ochre: '#D1A258', stone: '#C8C7BF', muted: '#748198',
};

function Cross({x, y, size=32, color=P.cobalt}: {x:number; y:number; size?:number; color?:string}) {
  const t=size/3;
  return <path d={`M${x+t},${y}h${t}v${t}h${t}v${t}h-${t}v${t}h-${t}v-${t}h-${t}v-${t}h${t}z`} fill={color}/>;
}

function Plant({x,y,scale=1,frame=0}: {x:number; y:number; scale?:number; frame?:number}) {
  const sway=Math.sin(frame/65)*0.7;
  return <g transform={`translate(${x} ${y}) scale(${scale})`}>
    <ellipse cx="0" cy="6" rx="51" ry="12" fill={P.navy} opacity=".055"/>
    <g transform={`rotate(${sway} 0 -60)`}>
      <path d="M0-55C-8-123-3-164 9-207M-1-73C-28-123-51-148-68-166M0-94C31-130 46-166 57-192" stroke={P.tealDark} strokeWidth="5" fill="none"/>
      <path d="M6-150C-26-160-33-192-13-216C12-204 21-177 6-150Z" fill={P.teal}/>
      <path d="M9-193C-2-216 9-244 27-249C43-223 32-204 9-193Z" fill={P.tealDark}/>
      <path d="M-25-119C-59-114-84-133-85-159C-48-166-30-148-25-119Z" fill={P.teal}/>
      <path d="M-1-101C-29-121-31-147-16-164C12-151 15-120-1-101Z" fill={P.tealDark}/>
      <path d="M28-136C31-171 50-186 78-181C78-154 57-134 28-136Z" fill={P.teal}/>
      <path d="M51-177C48-204 58-223 78-232C95-207 79-183 51-177Z" fill={P.tealDark}/>
      <path d="M-6-61C14-90 39-100 58-85C43-59 20-54-6-61Z" fill={P.teal}/>
    </g>
    <path d="M-38-66H38L29-3Q0 10-29-3Z" fill={P.warm}/>
    <path d="M-34-59H-22L-16 0L-29-3Z" fill="#D5CCBA"/>
    <ellipse cx="0" cy="-66" rx="38" ry="8" fill="#D2C7B4"/>
    <ellipse cx="0" cy="-68" rx="29" ry="5" fill="#A49B8C"/>
  </g>;
}

function ExteriorTree({x,y,scale=1,frame=0}: {x:number;y:number;scale?:number;frame?:number}) {
  return <g transform={`translate(${x} ${y}) scale(${scale})`}>
    <ellipse cy="10" rx="112" ry="18" fill={P.navy} opacity=".07"/>
    <path d="M-13 0L-8-239H11L17 0Z" fill="#8D8F80"/>
    <path d="M0-125L-60-189M4-154L60-215" stroke="#8D8F80" strokeWidth="10" strokeLinecap="round"/>
    <g transform={`rotate(${Math.sin(frame/80)*.35} 0 -155)`}>
      <path d="M-108-196C-128-234-100-276-65-278C-79-332-22-374 20-346C66-371 112-333 104-289C152-262 129-209 95-195C86-150 16-143-5-166C-39-135-96-150-108-196Z" fill="#9AB7A3"/>
      <path d="M-108-196C-101-174-53-163-23-178C-34-194-37-219-28-237C-66-218-90-230-116-241C-123-223-118-207-108-196Z" fill="#84A78F"/>
      <path d="M20-346C40-340 55-324 57-303C84-315 102-303 104-289C112-333 66-371 20-346Z" fill="#AEC7B3"/>
    </g>
  </g>;
}

function FacadeWindow({x,y,w=100,h=108}: {x:number;y:number;w?:number;h?:number}) {
  return <g>
    <rect x={x} y={y} width={w} height={h} rx="5" fill={P.navy} opacity=".08"/>
    <rect x={x+5} y={y+5} width={w-10} height={h-10} rx="3" fill={P.glass}/>
    <path d={`M${x+5} ${y+h-5}L${x+w*.67} ${y+5}H${x+w-5}V${y+25}L${x+w*.49} ${y+h-5}Z`} fill="#D2DFEE" opacity=".6"/>
    <path d={`M${x+w/2} ${y+4}V${y+h-3}M${x+3} ${y+h*.64}H${x+w-3}`} stroke={P.cream} strokeWidth="5"/>
    <rect x={x-3} y={y+h-1} width={w+6} height="7" rx="2" fill="#CECFC9"/>
  </g>;
}

export function HospitalExterior({frame}: {frame:number}) {
  const cloudDrift=(frame*.13)%55;
  return <g>
    <rect width="1920" height="1080" fill="#EEF1F4"/>
    <path d="M0 440C209 390 284 439 478 411S809 396 1013 430S1472 374 1920 422V794H0Z" fill="#E0E7E8"/>
    <g fill="#FFFFFF" opacity=".88" transform={`translate(${cloudDrift} 0)`}>
      <path d="M143 195C150 173 166 162 190 166C198 130 248 122 268 157C301 145 326 165 329 190H361Q382 190 382 207H135Q134 195 143 195Z"/>
      <path d="M1295 151C1307 129 1337 124 1358 135C1379 98 1435 103 1447 137C1480 128 1504 146 1509 165H1544Q1558 165 1560 178H1278Q1277 159 1295 151Z"/>
    </g>
    <path d="M0 768H1920V874H0Z" fill="#D7DED2"/>
    <rect x="489" y="289" width="1230" height="528" rx="14" fill="#DADBD5"/>
    <path d="M446 323Q446 272 497 272H1712Q1743 272 1743 303V819H446Z" fill={P.cream}/>
    <path d="M1710 291L1794 349V819H1743V303Q1743 284 1724 280Z" fill="#D8DDD8"/>
    <rect x="446" y="503" width="1297" height="16" fill="#D7DCD7"/>
    <rect x="446" y="693" width="1297" height="12" fill="#D7DCD7"/>
    <rect x="487" y="319" width="239" height="366" rx="13" fill={P.navy}/>
    <rect x="503" y="335" width="207" height="336" rx="5" fill={P.glass}/>
    <path d="M503 566L700 335H710V401L503 641Z" fill="#D0DFEF" opacity=".65"/>
    <path d="M607 335V672M503 449H710M503 561H710" stroke={P.cream} strokeWidth="8"/>
    <g>
      {[0,1,2,3,4,5].map(i=><FacadeWindow key={i} x={781+i*145} y={341} w={107} h={126}/>)}
      {[0,1,2,3].map(i=><FacadeWindow key={i} x={781+i*145} y={549} w={107} h={107}/>)}
    </g>
    <rect x="361" y="226" width="124" height="593" rx="19" fill="#D3DDF0"/>
    <rect x="352" y="218" width="111" height="601" rx="17" fill={P.paper}/>
    <rect x="374" y="261" width="66" height="78" rx="14" fill={P.powder}/>
    <Cross x={389} y={281} size={36}/>
    <rect x="381" y="369" width="51" height="318" rx="25" fill={P.glass}/>
    <path d="M381 451H432M381 531H432M381 611H432" stroke={P.cream} strokeWidth="8"/>
    <rect x="738" y="269" width="993" height="33" rx="5" fill={P.paper}/>
    <text x="792" y="291" fill={P.navy} fontFamily="Arial, Helvetica, sans-serif" fontSize="17" fontWeight="700" letterSpacing="5">GENERAL HOSPITAL</text>
    <rect x="1240" y="607" width="431" height="212" fill={P.navy}/>
    <rect x="1254" y="620" width="198" height="199" fill={P.glass}/>
    <rect x="1458" y="620" width="199" height="199" fill={P.glass}/>
    <path d="M1274 631L1428 631L1274 813ZM1475 636L1637 636L1475 813Z" fill="#D7E3EF" opacity=".44"/>
    <path d="M1455 620V819M1248 733H1666" stroke={P.paper} strokeWidth="7"/>
    <rect x="1382" y="707" width="23" height="4" rx="2" fill={P.navy}/>
    <rect x="1511" y="707" width="23" height="4" rx="2" fill={P.navy}/>
    <path d="M1132 554Q1132 521 1165 521H1741Q1774 521 1792 546L1835 606H1152Q1132 606 1132 584Z" fill={P.cobalt}/>
    <path d="M1152 606H1835L1818 625H1162Z" fill="#2F4CCE"/>
    <rect x="1170" y="615" width="15" height="204" rx="4" fill={P.steel}/>
    <rect x="1759" y="615" width="15" height="204" rx="4" fill={P.steel}/>
    <Cross x={1201} y={549} size={31} color={P.paper}/>
    <text x="1270" y="581" fill={P.paper} fontFamily="Arial, Helvetica, sans-serif" fontWeight="700" fontSize="44" letterSpacing="4">EMERGENCY</text>
    <path d="M276 819H1837L1902 865H208Z" fill="#D1D4D1"/>
    <path d="M208 865H1902V880H208Z" fill="#C1C7C5"/>
    <path d="M0 882H1920V1080H0Z" fill="#B7C1CB"/>
    <path d="M0 886H1920" stroke="#EBEFEF" strokeWidth="8"/>
    <path d="M1100 913H1570M40 997H321M433 997H714M826 997H1107M1219 997H1500M1612 997H1893" stroke="#EDF0EC" strokeWidth="10" strokeLinecap="round"/>
    <path d="M1168 882H1305L1474 1080H1247Z" fill="#CED4DA" opacity=".5"/>
    <rect x="1875" y="738" width="10" height="116" rx="4" fill={P.steel}/>
    <rect x="1844" y="684" width="72" height="86" rx="9" fill={P.paper}/>
    <text x="1880" y="734" textAnchor="middle" fill={P.cobalt} fontFamily="Arial" fontSize="38" fontWeight="700">P</text>
    <ExteriorTree x={167} y={846} scale={1.18} frame={frame}/>
    <ExteriorTree x={1843} y={838} scale={.79} frame={frame+29}/>
    <path d="M0 867C108 834 172 864 232 866L281 889H0Z" fill="#96B29A"/>
    <path d="M1644 850Q1670 818 1713 850Q1741 813 1774 845Q1823 818 1853 854H1920V880H1629Z" fill="#97B4A5"/>
    <g fill={P.ochre}>
      <rect x="1126" y="783" width="12" height="58" rx="5"/>
      <rect x="1796" y="783" width="12" height="58" rx="5"/>
    </g>
  </g>;
}

function WaitingChair({x,y,color=P.cobalt}: {x:number;y:number;color?:string}) {
  return <g transform={`translate(${x} ${y})`}>
    <ellipse cx="41" cy="17" rx="69" ry="10" fill={P.navy} opacity=".035"/>
    <path d="M6-44L-1 11M81-44L94 11" stroke={P.steel} strokeWidth="7" strokeLinecap="round"/>
    <path d="M-13-53H89" stroke={P.navy} strokeWidth="7" strokeLinecap="round"/>
    <rect x="-10" y="-151" width="102" height="104" rx="26" fill={color}/>
    <path d="M-10-80Q42-68 92-82V-55Q43-43-10-55Z" fill={P.navy} opacity=".07"/>
    <rect x="-18" y="-57" width="118" height="23" rx="10" fill={color}/>
    <path d="M-24-57V-79H-9M106-57V-79H91" stroke={P.navy} strokeWidth="6" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
  </g>;
}

function WallClock({x,y,frame}: {x:number;y:number;frame:number}) {
  return <g transform={`translate(${x} ${y})`}>
    <circle r="32" fill={P.paper} stroke={P.line} strokeWidth="3"/>
    {[0,1,2,3].map(i=><path key={i} d="M0-22V-26" stroke={P.steel} strokeWidth="2" transform={`rotate(${i*90})`}/>)}
    <path d="M0 0L-12-8M0 0L3-20" stroke={P.navy} strokeWidth="3" fill="none" strokeLinecap="round"/>
    <path d="M0 4V-24" stroke={P.cobalt} strokeWidth="1.5" transform={`rotate(${frame*.2+90})`}/>
    <circle r="3" fill={P.navy}/>
  </g>;
}

function Reception() {
  return <g>
    <rect x="1290" y="300" width="443" height="73" rx="11" fill={P.powder}/>
    <Cross x={1313} y={323} size={26}/>
    <text x="1360" y="346" fill={P.navy} fontSize="23" letterSpacing="1.2" fontFamily="Arial, Helvetica, sans-serif" fontWeight="700">NURSES’ STATION</text>
    <rect x="1372" y="430" width="231" height="145" rx="10" fill={P.navy}/>
    <rect x="1381" y="439" width="213" height="124" rx="5" fill={P.powder}/>
    <rect x="1396" y="453" width="37" height="10" rx="3" fill={P.cobalt}/>
    <rect x="1441" y="455" width="76" height="6" rx="3" fill="#A5B7D7"/>
    <rect x="1396" y="478" width="65" height="66" rx="6" fill={P.paper}/>
    <path d="M1406 521L1415 511L1422 516L1431 499L1440 508L1450 499" fill="none" stroke={P.tealDark} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
    <rect x="1472" y="478" width="106" height="18" rx="4" fill={P.paper}/>
    <rect x="1472" y="503" width="106" height="18" rx="4" fill={P.paper}/>
    <rect x="1472" y="528" width="106" height="15" rx="4" fill={P.paper}/>
    <circle cx="1482" cy="487" r="4" fill={P.teal}/>
    <circle cx="1482" cy="512" r="4" fill={P.cobalt}/>
    <rect x="1494" y="484" width="55" height="5" rx="2" fill={P.paleBlue}/>
    <rect x="1494" y="509" width="69" height="5" rx="2" fill={P.paleBlue}/>
    <rect x="1474" y="575" width="27" height="44" rx="4" fill={P.steel}/>
    <path d="M1444 619H1531" stroke={P.navy} strokeWidth="10" strokeLinecap="round"/>
    <rect x="1670" y="570" width="56" height="47" rx="7" fill={P.paper}/>
    <path d="M1680 570V528M1690 570V535M1703 570V526" stroke={P.cobalt} strokeWidth="5" strokeLinecap="round"/>
    <path d="M1226 621Q1226 610 1237 610H1796Q1814 610 1814 628V794H1226Z" fill={P.warm}/>
    <path d="M1235 649H1786V775H1235Z" fill="#DDD2BE"/>
    <path d="M1265 649V775M1308 649V775M1351 649V775M1394 649V775M1437 649V775M1480 649V775M1523 649V775M1566 649V775M1609 649V775M1652 649V775M1695 649V775M1738 649V775" stroke="#D2C5AF" strokeWidth="3"/>
    <rect x="1204" y="606" width="625" height="18" rx="8" fill={P.paper}/>
    <path d="M1243 794H1794" stroke={P.navy} strokeWidth="9" opacity=".08"/>
  </g>;
}

export function HospitalInterior({frame,doorOpen=0,variant='arrival'}: {frame:number;doorOpen?:number;variant?:'arrival'|'team'|'station'}) {
  const doorId=`entry-${useId().replace(/:/g,'')}`;
  const open=Math.max(0,Math.min(1,doorOpen));
  return <g>
    <defs><clipPath id={doorId}><rect x="48" y="286" width="426" height="492" rx="5"/></clipPath></defs>
    <rect width="1920" height="1080" fill={P.cream}/>
    <path d="M0 0H1920V227H0Z" fill="#FCFCF8"/>
    <path d="M0 228H1920V246H0Z" fill="#EAECE6"/>
    <path d="M0 254H1920" stroke="#FFFFFF" strokeWidth="5"/>
    <rect x="31" y="116" width="416" height="11" rx="5" fill="#E5E8E8"/>
    <rect x="1418" y="116" width="420" height="11" rx="5" fill="#E5E8E8"/>
    <rect x="47" y="117" width="386" height="5" rx="3" fill="#FFFFFF"/>
    <rect x="1432" y="117" width="391" height="5" rx="3" fill="#FFFFFF"/>
    <path d="M0 749H1920V1080H0Z" fill={P.floor}/>
    <path d="M0 749H1920V763H0Z" fill="#D6DBD6"/>
    <path d="M670 750L336 1080M1130 750L1463 1080M0 945H1920" stroke="#DADAD3" strokeWidth="2"/>
    <path d="M452 833H1105Q1159 833 1190 858L1355 992" fill="none" stroke={P.powder} strokeWidth="23"/>
    <path d="M452 833H1105Q1159 833 1190 858L1355 992" fill="none" stroke={P.cobalt} strokeWidth="3" opacity=".22"/>
    <path d="M1270 925L1285 949L1257 939" fill={P.cobalt} opacity=".23"/>
    <g>
      <path d="M516 252H754V749H516Z" fill="#DCE3E4"/>
      <path d="M543 278L626 348V671L543 735Z" fill="#EEF1ED"/>
      <path d="M725 278L648 348V671L725 735Z" fill="#C9D6D8"/>
      <path d="M543 278H725L648 348H626Z" fill="#E7ECE8"/>
      <path d="M543 735L626 671H648L725 735Z" fill="#D2DDD8"/>
      <rect x="626" y="348" width="22" height="323" fill="#B9CED1"/>
      <path d="M543 510L626 538M648 538L725 510" stroke={P.paper} strokeWidth="7"/>
      <rect x="626" y="413" width="22" height="170" fill="#AAC0CC"/>
      <rect x="517" y="253" width="27" height="497" fill={P.paper}/>
      <rect x="726" y="253" width="27" height="497" fill={P.paper}/>
      <path d="M520 253H753" stroke={P.paper} strokeWidth="18"/>
    </g>
    <g>
      <rect x="25" y="260" width="473" height="526" rx="11" fill={P.steel}/>
      <rect x="38" y="271" width="446" height="507" rx="6" fill={P.navy}/>
      <g clipPath={`url(#${doorId})`}>
        <rect x="48" y="286" width="426" height="492" fill="#DAE5E9"/>
        <path d="M48 610Q128 572 218 608Q325 558 474 610V778H48Z" fill="#B7D1C8"/>
        <path d="M48 725H474V778H48Z" fill="#CCD6DA"/>
        <g transform={`translate(${-open*204} 0)`}>
          <rect x="48" y="286" width="211" height="492" fill={P.glass}/>
          <path d="M50 546L207 288H249L48 633Z" fill="#DAE5EF" opacity=".5"/>
          <rect x="48" y="544" width="211" height="77" fill={P.paper} opacity=".7"/>
          <rect x="48" y="755" width="211" height="23" fill={P.steel}/>
          <path d="M257 286V779" stroke={P.paper} strokeWidth="6"/>
          <path d="M235 649V697" stroke={P.navy} strokeWidth="5" strokeLinecap="round"/>
          <Cross x={173} y={566} size={32} color={P.cobalt}/>
        </g>
        <g transform={`translate(${open*204} 0)`}>
          <rect x="264" y="286" width="210" height="492" fill={P.glass}/>
          <path d="M266 560L423 288H463L264 644Z" fill="#DAE5EF" opacity=".5"/>
          <rect x="264" y="544" width="210" height="77" fill={P.paper} opacity=".7"/>
          <rect x="264" y="755" width="210" height="23" fill={P.steel}/>
          <path d="M265 286V779" stroke={P.paper} strokeWidth="6"/>
          <path d="M287 649V697" stroke={P.navy} strokeWidth="5" strokeLinecap="round"/>
          <Cross x={316} y={566} size={32} color={P.cobalt}/>
        </g>
      </g>
      <rect x="97" y="243" width="329" height="52" rx="8" fill={P.cobalt}/>
      <text x="261" y="278" textAnchor="middle" fill={P.paper} fontSize="26" fontFamily="Arial, Helvetica, sans-serif" fontWeight="700" letterSpacing="3">EMERGENCY</text>
      <path d="M48 786H474" stroke={P.navy} strokeWidth="6" opacity=".3"/>
    </g>
    <g>
      <rect x="811" y="321" width="266" height="429" rx="7" fill="#D1DAD7"/>
      <rect x="824" y="333" width="240" height="417" rx="4" fill={P.paper}/>
      <rect x="838" y="348" width="214" height="384" rx="3" fill="#E1E7DF"/>
      <rect x="876" y="382" width="138" height="161" rx="28" fill={P.steel}/>
      <rect x="883" y="389" width="124" height="146" rx="23" fill={P.paleBlue}/>
      <path d="M888 505L973 391H1007L899 535H888Z" fill={P.paper} opacity=".25"/>
      <rect x="834" y="585" width="223" height="29" rx="6" fill="#B8C9C1"/>
      <path d="M1009 621H1031" stroke={P.navy} strokeWidth="5" strokeLinecap="round"/>
      <rect x="880" y="292" width="133" height="41" rx="7" fill={P.powder}/>
      <text x="946" y="320" textAnchor="middle" fill={P.navy} fontFamily="Arial, Helvetica, sans-serif" fontSize="20" fontWeight="700" letterSpacing="1.5">BAY 02</text>
      <rect x="1096" y="427" width="46" height="69" rx="6" fill={P.paper} stroke={P.line} strokeWidth="2"/>
      <rect x="1106" y="436" width="26" height="28" rx="3" fill={P.powder}/>
      <path d="M1111 480H1127" stroke={P.steel} strokeWidth="3" strokeLinecap="round"/>
      <path d="M1115 490C1110 499 1110 503 1118 503C1126 503 1125 499 1121 490" fill={P.cobalt}/>
    </g>
    <path d="M1148 267V746" stroke="#E0E3DB" strokeWidth="3"/>
    <WallClock x={1178} y={320} frame={frame}/>
    {variant==='station' ? <Reception/> : <g>
      <rect x="1274" y="337" width="405" height="158" rx="5" fill={P.paper} stroke="#E1DDD3" strokeWidth="7"/>
      <path d="M1281 459L1365 389L1445 445L1501 411L1671 487H1281Z" fill={P.paleBlue}/>
      <path d="M1281 486L1407 431L1499 467L1586 411L1671 454V489H1281Z" fill="#AFC8BE"/>
      <circle cx="1578" cy="376" r="20" fill={P.ochre}/>
      <WaitingChair x={1288} y={741} color={P.cobalt}/>
      <WaitingChair x={1440} y={741} color="#88A6CB"/>
      <WaitingChair x={1592} y={741} color={variant==='team'?P.teal:'#88A6CB'}/>
      <path d="M1236 756H1728" stroke={P.navy} strokeWidth="8" opacity=".05" strokeLinecap="round"/>
      <Plant x={1800} y={751} scale={.94} frame={frame}/>
    </g>}
    <Plant x={775} y={756} scale={.62} frame={frame+30}/>
    <path d="M115 947Q588 901 1102 947" stroke={P.paper} strokeWidth="2" opacity=".32" fill="none"/>
  </g>;
}

function Wheel({x,y,frame}: {x:number;y:number;frame:number}) {
  const rotation=frame*7;
  return <g transform={`translate(${x} ${y})`}>
    <path d="M-8-51H17V-22Q17-12 8-8H-9" fill="none" stroke={P.steel} strokeWidth="9" strokeLinejoin="round"/>
    <circle r="28" fill={P.navy}/>
    <circle r="20" fill="#DCE2E7"/>
    <g transform={`rotate(${rotation})`} stroke={P.steel} strokeWidth="4">
      <path d="M0-15V15M-15 0H15M-11-11L11 11M11-11L-11 11"/>
    </g>
    <circle r="7" fill={P.navy}/>
    <path d="M-24-27H13" stroke={P.navy} strokeWidth="7" strokeLinecap="round"/>
  </g>;
}

/** Local extent x=0..700, y=-153..305; mattress top=20, wheel contact=305. */
export function Stretcher({frame, children}: {frame:number; children?:React.ReactNode}) {
  const bagSwing=Math.sin(frame/17)*1.1;
  return <g>
    <ellipse cx="350" cy="310" rx="302" ry="13" fill={P.navy} opacity=".09"/>
    <path d="M143 198V255M574 198V255" stroke="#687D97" strokeWidth="16" strokeLinecap="round"/>
    <Wheel x={142} y={277} frame={frame}/>
    <Wheel x={566} y={277} frame={frame}/>
    <path d="M175 264H603" stroke={P.steel} strokeWidth="13" strokeLinecap="round"/>
    <path d="M185 264L243 102M555 264L491 102" stroke={P.steel} strokeWidth="18" strokeLinecap="round"/>
    <path d="M202 252L509 111M548 254L247 111" stroke={P.navy} strokeWidth="11" strokeLinecap="round"/>
    <circle cx="377" cy="183" r="13" fill={P.paper} stroke={P.steel} strokeWidth="6"/>
    <path d="M280 172L279 220H467" stroke="#A9B5C1" strokeWidth="10" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
    <rect x="306" y="205" width="164" height="34" rx="8" fill="#DCE3E9"/>
    <rect x="316" y="210" width="144" height="22" rx="5" fill={P.paper}/>
    <path d="M97 64H621V117H112Q88 117 88 94Z" fill={P.steel}/>
    <path d="M104 88H616V114H112Q91 114 89 99Z" fill="#71859A"/>
    <rect x="97" y="56" width="518" height="29" rx="12" fill={P.paper}/>
    <path d="M92 23Q92 10 109 10H615Q637 10 637 29V49Q637 65 620 65H107Q89 65 89 47Z" fill={P.powder}/>
    <path d="M92 42H635V50Q635 65 620 65H107Q92 65 92 51Z" fill="#C7D4EE"/>
    <rect x="101" y="13" width="117" height="32" rx="14" fill={P.paper}/>
    <path d="M219 13H598Q615 13 620 27L636 41H237Z" fill="#DAE4F5"/>
    <path d="M77 20V-2Q77-18 92-18H160" fill="none" stroke={P.navy} strokeWidth="9" strokeLinecap="round"/>
    <path d="M633 22V-2Q633-18 648-18H680" fill="none" stroke={P.navy} strokeWidth="9" strokeLinecap="round"/>
    {children}
    <path d="M176 85V15Q176 3 190 3H548Q562 3 562 16V84" fill="none" stroke={P.steel} strokeWidth="9" strokeLinecap="round"/>
    <path d="M187 15H551" stroke={P.paper} strokeWidth="3" strokeLinecap="round" opacity=".8"/>
    <path d="M202 15V78M267 15V78M333 15V78M399 15V78M465 15V78M535 15V78" stroke={P.steel} strokeWidth="6" strokeLinecap="round"/>
    <rect x="162" y="76" width="416" height="31" rx="9" fill={P.paper}/>
    <rect x="319" y="81" width="117" height="21" rx="7" fill={P.cobalt}/>
    <rect x="177" y="84" width="69" height="7" rx="3" fill="#D8E0E9"/>
    <circle cx="553" cy="91" r="6" fill={P.ochre}/>
    <path d="M619 84V-128Q619-141 606-141H584M619-128Q619-141 632-141H653" stroke={P.steel} strokeWidth="7" fill="none" strokeLinecap="round"/>
    <path d="M584-141V-132M653-141V-132" stroke={P.steel} strokeWidth="5" strokeLinecap="round"/>
    <g transform={`rotate(${bagSwing} 582 -137)`}>
      <path d="M583-137V-123" stroke={P.steel} strokeWidth="3"/>
      <path d="M566-121Q567-127 575-127H590Q597-127 599-120L603-75Q603-69 595-68H570Q562-69 562-76Z" fill={P.paper} stroke="#ACC2D4" strokeWidth="2"/>
      <path d="M565-97H600L602-75Q602-71 595-70H570Q564-70 564-76Z" fill="#BFD9E8"/>
      <path d="M572-115H589M572-110H584" stroke="#A0B6C7" strokeWidth="2" strokeLinecap="round"/>
      <path d="M583-69V-53Q583-35 559-24L525-5" fill="none" stroke="#9CB4CC" strokeWidth="2"/>
      <rect x="579" y="-59" width="8" height="14" rx="3" fill={P.paper} stroke="#A7BDCC" strokeWidth="1"/>
    </g>
  </g>;
}
