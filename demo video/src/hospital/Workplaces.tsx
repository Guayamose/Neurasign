import React from 'react';
import {C} from './Design';

/** Original vector sets for the wider product story. Local canvas: 600 × 440. */
const Ground = () => <>
  <path d="M0 346H600V440H0Z" fill="#DBDED9"/>
  <path d="M0 371H600M65 440L237 346M560 440L394 346" stroke="#C5CCC8" strokeWidth="2"/>
</>;

export function ConstructionSite({frame}: {frame: number}) {
  const hook = 214 + Math.sin(frame / 39) * 6;
  return <g>
    <rect width="600" height="440" fill="#E8EEF2"/>
    <path d="M16 87Q40 55 73 78Q95 49 131 79Q153 81 159 97H16Z" fill="#F9FBFC"/>
    <path d="M404 61Q424 37 451 59Q477 26 505 64H553V78H404Z" fill="#F9FBFC"/>
    <rect x="320" y="110" width="226" height="236" fill="#D6D9D3"/>
    <path d="M320 110L375 90H581L546 110Z" fill="#EBEAE2"/>
    <path d="M546 110L581 90V326L546 346Z" fill="#B9C3C1"/>
    {[132,199,266].map(y=><g key={y}>
      <rect x="342" y={y} width="70" height="49" fill="#8CA2B4"/>
      <rect x="435" y={y} width="87" height="49" fill="#91A8B8"/>
      <path d={`M346 ${y+4}H404L346 ${y+42}Z M440 ${y+4}H510L440 ${y+43}Z`} fill="#B5CAD5"/>
      <path d={`M314 ${y+56}H550`} stroke="#F7F6F2" strokeWidth="10"/>
    </g>)}
    <Ground/>
    <path d="M145 344V83H169V344" fill="#D0A259"/>
    <path d="M148 84L166 118L148 153L166 188L148 222L166 257L148 291L166 327" stroke="#F1D495" strokeWidth="4" fill="none"/>
    <path d="M148 84L133 43H165L183 84Z" fill="#D0A259"/>
    <path d="M48 83H454V99H48Z" fill="#D0A259"/>
    <path d="M51 87L82 98L114 87L146 98L178 87L210 98L242 87L274 98L306 87L338 98L370 87L402 98L448 87" fill="none" stroke="#F4DCAE" strokeWidth="3"/>
    <path d="M149 47L49 84M163 47L441 84" stroke="#7D8B91" strokeWidth="2"/>
    <rect x="42" y="100" width="60" height="22" rx="3" fill="#7C8B94"/>
    <rect x="161" y="106" width="39" height="38" rx="4" fill={C.navy}/>
    <rect x="169" y="112" width="24" height="22" rx="2" fill="#B5CADA"/>
    <path d={`M282 99V${hook}M299 99V${hook}`} stroke="#73858E" strokeWidth="2"/>
    <g transform={`translate(291 ${hook})`}>
      <rect x="-16" y="-5" width="32" height="17" rx="5" fill={C.blue}/>
      <path d="M0 12V28Q15 41 19 24" fill="none" stroke={C.navy} strokeWidth="5" strokeLinecap="round"/>
    </g>
    <path d="M116 346H197L186 360H108Z" fill="#B5BBB3"/>
    <rect x="107" y="336" width="99" height="13" rx="3" fill="#778992"/>
    <g transform="translate(397 322)">
      <ellipse cx="60" cy="53" rx="94" ry="13" fill="#A7B4BB" opacity=".24"/>
      <rect x="-20" y="17" width="160" height="23" rx="4" fill="#8195A3"/>
      <rect x="-9" y="-4" width="153" height="20" rx="4" fill="#B3C0C7"/>
      <path d="M0 3H134M-10 25H129" stroke="#D7E0E3" strokeWidth="3"/>
    </g>
    <g transform="translate(43 296)">
      <ellipse cx="47" cy="78" rx="63" ry="11" fill="#7D95A7" opacity=".18"/>
      <path d="M3 54Q3 9 43 7Q87 7 89 54Z" fill={C.blue}/>
      <path d="M12 48Q16 18 37 16" fill="none" stroke="#859CFF" strokeWidth="7" strokeLinecap="round"/>
      <path d="M39 11Q43 2 51 11V50H39Z" fill="#6582F4"/>
      <path d="M-3 52H97Q103 54 97 66H-4Q-12 60-3 52Z" fill="#304AB5"/>
    </g>
  </g>;
}

export function IndustrialOperations({frame}: {frame: number}) {
  const pulse = .55 + Math.sin(frame / 14) * .2;
  const elbow = 10 + Math.sin(frame / 36) * 5;
  return <g>
    <rect width="600" height="440" fill="#ECEFEA"/>
    {[50,183,316,449,582].map(x=><path key={x} d={`M${x} 0V346`} stroke="#D3DBD5" strokeWidth="12"/>)}
    <path d="M0 30H600M0 144H600" stroke="#CCD4D0" strokeWidth="10"/>
    <path d="M22 28L175 144L308 28L441 144L579 28" stroke="#D5DED8" strokeWidth="6" fill="none"/>
    <rect x="370" y="98" width="157" height="239" rx="13" fill="#B5C3C9"/>
    <rect x="385" y="113" width="127" height="140" rx="7" fill="#D5DFE1"/>
    <rect x="402" y="131" width="94" height="66" rx="5" fill={C.navy}/>
    <path d="M415 178H428L436 157L445 173L455 147L467 163H484" stroke="#8AA6FF" strokeWidth="3" fill="none"/>
    <rect x="402" y="213" width="49" height="12" rx="5" fill={C.blue}/>
    <circle cx="482" cy="219" r="6" fill="#559B8A" opacity={pulse}/>
    <path d="M399 278H498M399 290H498M399 302H498" stroke="#8194A1" strokeWidth="4" strokeLinecap="round"/>
    <path d="M529 155H564V316H547" fill="none" stroke="#8095A1" strokeWidth="12" strokeLinejoin="round"/>
    <Ground/>
    <g transform="translate(161 313)">
      <ellipse cx="14" cy="63" rx="103" ry="14" fill="#95A8B3" opacity=".26"/>
      <rect x="-46" y="23" width="121" height="39" rx="7" fill="#536D84"/>
      <path d="M-22 23L-5-31H32L53 23Z" fill={C.blue}/>
      <g transform={`rotate(${elbow})`}>
        <path d="M12-5L-44-125" stroke="#304AB5" strokeWidth="37" strokeLinecap="round"/>
        <path d="M12-5L-44-125" stroke={C.blue} strokeWidth="26" strokeLinecap="round"/>
        <path d="M-44-125L66-172" stroke="#304AB5" strokeWidth="33" strokeLinecap="round"/>
        <path d="M-44-125L66-172" stroke="#6481F4" strokeWidth="24" strokeLinecap="round"/>
        <circle cx="-44" cy="-125" r="20" fill="#C1CCE3"/><circle cx="-44" cy="-125" r="10" fill="#546C99"/>
        <circle cx="66" cy="-172" r="15" fill="#C1CCE3"/>
        <path d="M75-165L104-147" stroke="#4D6682" strokeWidth="14" strokeLinecap="round"/>
        <path d="M101-151L121-147L127-126M103-141L109-123L126-113" stroke={C.navy} strokeWidth="7" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
      </g>
      <circle cx="12" cy="-5" r="21" fill="#A9BED5"/><circle cx="12" cy="-5" r="11" fill="#536D84"/>
    </g>
    <path d="M284 322H567V344H284Z" fill="#405B75"/>
    <rect x="276" y="291" width="298" height="34" rx="15" fill="#9AAFC0"/>
    {[297,327,357,387,417,447,477,507,537,556].map(x=><circle key={x} cx={x} cy="308" r="8" fill="#D6E0E7"/>)}
    <path d="M307 344L291 385M551 344L568 385" stroke="#6F899B" strokeWidth="11"/>
    {[334,461].map((x,i)=><g key={x} transform={`translate(${x+(frame* .25)%18} 257)`}>
      <path d="M0 0H62V32H0Z" fill={i?'#D0AE76':'#D9BD8D'}/>
      <path d="M0 0L14-10H76L62 0Z" fill="#EAD5B0"/>
      <path d="M62 0L76-10V22L62 32Z" fill="#B9955B"/>
      <path d="M29 0V32" stroke="#F1DDAD" strokeWidth="8"/>
    </g>)}
  </g>;
}

export function ControlRoom({frame}: {frame: number}) {
  return <g>
    <rect width="600" height="440" fill="#DDE5EB"/>
    <path d="M0 0H600V47H0Z" fill="#C7D3DF"/>
    <path d="M69 24H267M335 24H531" stroke="#FAFCFF" strokeWidth="6" strokeLinecap="round"/>
    <rect x="29" y="68" width="542" height="209" rx="13" fill="#7990A9"/>
    {[0,1,2].map(i=><g key={i} transform={`translate(${44+i*175} 83)`}>
      <rect width="161" height="179" rx="5" fill={C.navy}/>
      <path d="M10 18H77" stroke="#627DA6" strokeWidth="4"/>
      {i===0?<>
        <circle cx="81" cy="91" r="55" stroke="#3D5C88" fill="none"/><circle cx="81" cy="91" r="34" stroke="#3D5C88" fill="none"/>
        <path d="M25 91H137M81 37V146" stroke="#3D5C88"/>
        <path d="M81 91L124 60" stroke="#82A4FF" strokeWidth="2" transform={`rotate(${frame*.7} 81 91)`}/>
        <circle cx="53" cy="82" r="4" fill="#B7C9FF"/><circle cx="100" cy="116" r="4" fill="#809EFF"/>
      </>:i===1?<>
        <path d="M15 60H146M15 95H146M15 130H146" stroke="#3D5C88"/>
        <path d="M17 117L40 99L62 103L87 76L112 84L145 49" fill="none" stroke="#809FFF" strokeWidth="4" strokeLinejoin="round"/>
        <path d="M17 139L40 131L62 138L87 117L112 125L145 107" fill="none" stroke="#69AFAD" strokeWidth="3"/>
      </>:<>
        {[47,81,115].map((y,j)=><g key={y}><rect x="16" y={y} width="128" height="23" rx="4" fill="#263D61"/><circle cx="29" cy={y+11} r="4" fill={j===1?'#CBB081':'#82B7AD'}/><path d={`M44 ${y+11}H${118-j*9}`} stroke="#9FB5D4" strokeWidth="3"/></g>)}
      </>}
      <path d="M15 160H76" stroke="#4E709C" strokeWidth="3"/>
    </g>)}
    <Ground/>
    <path d="M68 293H532L579 338H22Z" fill="#A1B4C8"/>
    <path d="M22 338H579V358H22Z" fill="#708BA4"/>
    <path d="M56 358H79V410H56M523 358H546V410H523" fill="#627C96"/>
    {[130,355].map(x=><g key={x}>
      <path d={`M${x} 273H${x+109}L${x+120} 322H${x-9}Z`} fill={C.navy}/>
      <path d={`M${x+9} 281H${x+100}L${x+106} 309H${x+4}Z`} fill="#4263A0"/>
      <path d={`M${x+18} 292H${x+76}M${x+17} 300H${x+56}`} stroke="#A7BFFF" strokeWidth="3"/>
    </g>)}
    {[185,419].map(x=><g key={x}>
      <ellipse cx={x} cy="421" rx="54" ry="10" fill="#879AAF" opacity=".22"/>
      <path d={`M${x} 379V417M${x-35} 421L${x} 410L${x+35} 421`} fill="none" stroke="#597188" strokeWidth="6" strokeLinecap="round"/>
      <rect x={x-36} y="319" width="72" height="63" rx="18" fill="#304A70"/>
      <path d={`M${x-25} 329Q${x} 321 ${x+25} 329V365H${x-25}Z`} fill="#45658E"/>
      <path d={`M${x-37} 379H${x+37}`} stroke="#304A70" strokeWidth="13" strokeLinecap="round"/>
    </g>)}
  </g>;
}
