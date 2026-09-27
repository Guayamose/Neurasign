import React from 'react';
import {
  AbsoluteFill, Audio, Easing, Img, OffthreadVideo, Sequence,
  interpolate, staticFile, useCurrentFrame,
} from 'remotion';

const INK = '#0D1321';
const PAPER = '#F5F7FC';
const COBALT = '#6C8BFF';
const MUTED = '#B0BCD0';
const ease = Easing.bezier(0.22, 1, 0.36, 1);
const tween = (frame: number, start: number, end: number, from=0, to=1) =>
  interpolate(frame, [start, end], [from, to], {extrapolateLeft:'clamp', extrapolateRight:'clamp', easing:ease});

/** All motion is editorial; the captured values and signal paths remain unchanged. */
const Reveal: React.FC<{children:React.ReactNode; at?:number; size?:number; weight?:number; color?:string}> = ({children,at=0,size=110,weight=400,color=PAPER}) => {
  const frame=useCurrentFrame();
  const p=tween(frame,at,at+22);
  return <div style={{overflow:'hidden',paddingBottom:10,marginBottom:-10}}>
    <div style={{fontSize:size,fontWeight:weight,lineHeight:1.05,letterSpacing:-size*0.055,color,transform:`translateY(${(1-p)*110}%)`,opacity:tween(frame,at,at+10)}}>{children}</div>
  </div>;
};

const Brand: React.FC<{width?:number; style?:React.CSSProperties}> = ({width=270,style}) =>
  <Img src={staticFile('brand/neurasign-dark.svg')} style={{width,height:'auto',...style}} />;

const Source: React.FC<{light?:boolean}> = ({light=false}) => <div style={{display:'flex',alignItems:'center',gap:11,color:light?'#DBE2EE':MUTED,fontSize:21,fontWeight:400,letterSpacing:0.15}}>
  <span style={{width:7,height:7,borderRadius:'50%',background:COBALT}} />Recorded demo · UNIVERSE
</div>;

const Opening: React.FC = () => {
  const f=useCurrentFrame();
  return <AbsoluteFill>
    <OffthreadVideo src={staticFile('footage/typing-edit.mp4')} muted style={{width:'100%',height:'100%',objectFit:'cover',transform:`scale(${interpolate(f,[0,105],[1.035,1.005])})`}} />
    <AbsoluteFill style={{background:'linear-gradient(90deg,rgba(7,12,20,.48),rgba(7,12,20,.13) 65%,transparent),linear-gradient(0deg,rgba(7,12,20,.5),transparent 40%)'}} />
    <Brand width={272} style={{position:'absolute',left:92,top:54,opacity:tween(f,3,17)}} />
    <div style={{position:'absolute',left:92,top:220}}>
      <Reveal at={9} size={124}>Every team</Reveal>
      <Reveal at={18} size={124}>has a pulse.</Reveal>
    </div>
    <div style={{position:'absolute',left:96,bottom:83,display:'flex',alignItems:'center',gap:18,opacity:tween(f,30,47)}}>
      <div style={{height:3,width:44,background:COBALT}} />
      <span style={{fontSize:25,color:'#F5F7FC',letterSpacing:.1}}>Physiological signals. Human context.</span>
    </div>
  </AbsoluteFill>;
};

const Wrist: React.FC = () => {
  const f=useCurrentFrame();
  return <AbsoluteFill>
    <OffthreadVideo src={staticFile('footage/wrist-edit.mp4')} muted style={{width:'100%',height:'100%',objectFit:'cover'}} />
    <AbsoluteFill style={{background:'linear-gradient(0deg,rgba(6,10,17,.74),transparent 52%)'}} />
    <div style={{position:'absolute',left:96,bottom:88}}>
      <Reveal at={0} size={85}>Make it visible.</Reveal>
    </div>
    <div style={{position:'absolute',right:96,bottom:107,display:'flex',alignItems:'center',gap:14,fontSize:23,color:PAPER,opacity:tween(f,7,18)}}>
      <span>Wearable</span><span style={{color:COBALT}}>→</span><span>Phone</span><span style={{color:COBALT}}>→</span><span>Team</span>
    </div>
  </AbsoluteFill>;
};

const ProductBackdrop: React.FC = () => <AbsoluteFill style={{background:INK}}>
  <div style={{position:'absolute',top:-390,right:-120,width:1260,height:1500,background:'radial-gradient(ellipse,rgba(40,84,232,.11) 0%,rgba(40,84,232,.025) 48%,transparent 70%)'}} />
  <div style={{position:'absolute',left:96,right:96,top:136,height:1,background:'#283448'}} />
</AbsoluteFill>;

const Screen:React.FC<{src:string; width:number; height:number; left:number; top:number; imageTop?:number; imageWidth?:number; angle?:number; progress:number}> = ({src,width,height,left,top,imageTop=0,imageWidth=width,angle=0,progress}) =>
  <div style={{position:'absolute',left,top,width,height,transform:`perspective(2300px) translateY(${(1-progress)*65}px) rotateY(${angle+(1-progress)*6}deg) rotateX(${(1-progress)*1.5}deg)`,transformOrigin:'center',opacity:progress,borderRadius:15,background:INK,padding:0,border:'1px solid #526078',boxShadow:'0 22px 65px rgba(0,0,0,.42)',overflow:'hidden'}}>
    <Img src={staticFile(src)} style={{position:'absolute',left:0,top:imageTop,width:imageWidth,maxWidth:'none',height:'auto'}} />
  </div>;

const Team: React.FC = () => {
  const f=useCurrentFrame();
  const p=tween(f,0,25);
  return <AbsoluteFill>
    <ProductBackdrop />
    <Brand width={272} style={{position:'absolute',left:92,top:37}} />
    <div style={{position:'absolute',right:96,top:73}}><Source /></div>
    <div style={{position:'absolute',left:96,top:250,width:465}}>
      <div style={{fontSize:22,letterSpacing:2.4,color:COBALT,marginBottom:30,opacity:tween(f,4,18)}}>01 / TEAM VIEW</div>
      <Reveal at={3} size={101}>Your team.</Reveal>
      <Reveal at={9} size={101}>One view.</Reveal>
      <div style={{color:MUTED,fontSize:27,lineHeight:1.5,marginTop:37,opacity:tween(f,18,32)}}>Find a person.<br/>Explore the context.</div>
    </div>
    <Screen src="capture/manager-overview-panel@2x.png" left={625} top={220} width={1200} height={662} imageWidth={1200} imageTop={0} progress={p} angle={-2+tween(f,0,90,0,2)} />
    <div style={{position:'absolute',left:96,bottom:75,color:MUTED,fontSize:21,opacity:tween(f,20,34)}}>Working prototype · 2 sample profiles</div>
    <div style={{position:'absolute',left:625,bottom:83,color:'#D7DFEC',fontSize:23,opacity:tween(f,20,34)}}>Team view → Signal detail</div>
  </AbsoluteFill>;
};

const Signal: React.FC = () => {
  const f=useCurrentFrame();
  return <AbsoluteFill>
    <ProductBackdrop />
    <Brand width={272} style={{position:'absolute',left:92,top:37}} />
    <div style={{position:'absolute',right:96,top:73}}><Source /></div>
    <div style={{position:'absolute',left:96,top:214}}>
      <div style={{fontSize:22,letterSpacing:2.4,color:COBALT,marginBottom:22}}>02 / SIGNAL DETAIL</div>
      <Reveal at={1} size={86}>Understand the change.</Reveal>
    </div>
    <Screen src="capture/alex-heart-rate-panel@2x.png" left={444} top={375} width={1380} height={612} imageWidth={1380} imageTop={0} progress={tween(f,0,19)} angle={0} />
    <div style={{position:'absolute',left:96,top:433,width:176,color:MUTED,fontSize:24,lineHeight:1.4,opacity:tween(f,10,24)}}>
      <span style={{display:'block',color:PAPER,fontSize:31,marginBottom:15}}>Heart rate</span>
      Beats per minute
      <div style={{marginTop:35,width:52,height:3,background:COBALT}} />
    </div>
  </AbsoluteFill>;
};

const Closing: React.FC = () => {
  const f=useCurrentFrame();
  const p=tween(f,3,30);
  const fade=tween(f,108,120,1,0);
  return <AbsoluteFill style={{background:INK,opacity:fade}}>
    <div style={{position:'absolute',left:96,right:96,top:136,height:1,background:'#283448',opacity:1-tween(f,0,30)}} />
    <div style={{position:'absolute',left:0,right:0,top:281,display:'flex',flexDirection:'column',alignItems:'center',transform:`translateY(${(1-p)*25}px)`,opacity:p}}>
      <Brand width={705} />
      <div style={{fontSize:47,lineHeight:1.28,letterSpacing:-1.7,fontWeight:400,color:PAPER,textAlign:'center',marginTop:38,opacity:tween(f,19,38)}}>Physiological intelligence<br/>for work.</div>
      <div style={{marginTop:58,width:74,height:3,background:COBALT,transform:`scaleX(${tween(f,26,48)})`}} />
    </div>
    <div style={{position:'absolute',left:96,bottom:67,color:MUTED,fontSize:21,opacity:tween(f,29,44)}}>Wearables → Phone → Team dashboard</div>
    <div style={{position:'absolute',right:96,bottom:67,color:MUTED,fontSize:21,opacity:tween(f,29,44)}}>Prototype film · 15-second sample</div>
  </AbsoluteFill>;
};

export const NeurasignSample: React.FC = () => <AbsoluteFill style={{background:INK,color:PAPER,fontFamily:'Arial, Helvetica, sans-serif'}}>
  <Audio src={staticFile('audio/neurasign-film-bed-15s.wav')} />
  <Sequence from={0} durationInFrames={105}><Opening /></Sequence>
  <Sequence from={105} durationInFrames={45}><Wrist /></Sequence>
  <Sequence from={150} durationInFrames={90}><Team /></Sequence>
  <Sequence from={240} durationInFrames={90}><Signal /></Sequence>
  <Sequence from={330} durationInFrames={120}><Closing /></Sequence>
</AbsoluteFill>;
