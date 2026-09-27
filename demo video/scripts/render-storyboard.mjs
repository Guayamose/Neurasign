import {bundle} from '@remotion/bundler';
import {openBrowser,selectComposition,renderStill} from '@remotion/renderer';
import {mkdir} from 'node:fs/promises';

const frames=process.argv.slice(2).map(Number);
const selected=frames.length?frames:[90,270,480,615,735,930,1140,1390,1565,1640,1760,1950,2080,2220];
await mkdir('review/hospital',{recursive:true});
const serveUrl=await bundle({entryPoint:'src/index.ts',symlinkPublicDir:true});
const browser=await openBrowser('chrome',{browserExecutable:'/usr/bin/google-chrome',chromeMode:'chrome-for-testing'});
try{
 const composition=await selectComposition({serveUrl,id:'NeurasignHospital1080',inputProps:{audio:false},puppeteerInstance:browser});
 for(let i=0;i<selected.length;i+=2){
  await Promise.all(selected.slice(i,i+2).map(async frame=>{
   const output=`review/hospital/frame-${String(frame).padStart(4,'0')}.png`;
   await renderStill({serveUrl,composition,frame,output,inputProps:{audio:false},puppeteerInstance:browser,imageFormat:'png'});
   console.log(output);
  }));
 }
}finally{await browser.close({silent:true});}
