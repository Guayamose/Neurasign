/** Native-shell lifecycle tests with injected OS transports; no hardware claim. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as gateway from '../dist/gateway.js';
import * as contract from '../dist/contract.js';
import * as multisignal from '../dist/multisignal.js';
import * as enrollment from '../dist/enrollment.js';
import { randomUUID, randomBytes } from 'node:crypto';

function shell(initial = {}, overrides = {}) {
  const saved = new Map(Object.entries(initial));
  const intervals=[];let queueCleared=0;
  const exports={};
  const mocks={
    'react-native':{AppState:{currentState:'active'},Platform:{OS:'ios'}},
    'react-native-background-actions':{default:{}},
    'expo-constants':{default:{expoConfig:{extra:{allowLocalHttp:true}}}},
    'expo-crypto':{randomUUID},
    '../../src/gateway':gateway,'../../src/contract':contract,'../../src/multisignal':multisignal,'../../src/enrollment':enrollment,
    './storage':{secret:()=>randomBytes(32).toString('base64url'),readSecret:async key=>saved.get(key)??null,writeSecret:async(key,value)=>saved.set(key,structuredClone(value)),removeSecret:async key=>saved.delete(key),EncryptedQueue:{open:async()=>({count:async()=>0,clear:async()=>{queueCleared++}})}},
    './ble':{NativeBle:class {async stopScan(){} async permission(){} }},
    './health': { healthKitAvailable: false, syncHealthKit: async () => ({channels: [], warnings: []}) },
    './watch':{pairedWatches:async()=>[],connectPairedWatch:async()=>{throw new Error('No paired watch in this fixture');}},
    ...overrides,
  };
  const code=ts.transpileModule(fs.readFileSync(new URL('../mobile/src/controller.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
  vm.runInNewContext(code,{exports,require:id=>{if(!mocks[id])throw new Error(`Missing mock ${id}`);return mocks[id]},setTimeout,clearTimeout,setInterval:fn=>{intervals.push(fn)},AbortController,console});
  return {controller:new exports.LinkController(),saved,intervals,get queueCleared(){return queueCleared}};
}
const receipt={credential:`nsd_${'a'.repeat(32)}.${'b'.repeat(43)}`,gateway_id:'a'.repeat(32),organization_id:'c'.repeat(32),employee_id:'d'.repeat(32),company:'Example company',employee:'Alex',apiOrigin:'http://localhost:3000'};
const token=`nse_${'e'.repeat(32)}.${'f'.repeat(43)}`;
test('a lost enrollment response persists exactly the claim needed for safe recovery',async()=>{
  const original=global.fetch;const calls=[];
  global.fetch=async(_url,init)=>{const body=JSON.parse(init.body);calls.push(body);if(calls.length===1)throw new Error('Offline');return new Response(JSON.stringify({...receipt,credential:`nsd_${receipt.gateway_id}.${body.claim_secret}`}));};
  try {
    const first=shell();await first.controller.initialize();
    await assert.rejects(first.controller.enroll({apiOrigin:receipt.apiOrigin,token}),/Offline/);
    assert.equal(first.controller.state.pending,true);assert.ok(first.saved.get('pending-claim'));
    const restarted=shell(Object.fromEntries(first.saved));await restarted.controller.initialize();await restarted.controller.retryEnrollment();
    assert.deepEqual(calls[0],calls[1]);assert.equal(restarted.controller.state.pending,false);assert.equal(restarted.controller.state.running,false);assert.equal(restarted.saved.has('pending-claim'),false);
  }finally{global.fetch=original}
});
test('offline pause stops capture, clears queued data and survives restart until acknowledged',async()=>{
  const original=global.fetch;
  global.fetch=async()=>{throw new Error('Offline')};
  try {
    const first=shell({enrollment:receipt});await first.controller.initialize();await first.controller.pause();
    assert.equal(first.controller.state.running,false);assert.equal(first.queueCleared,1);assert.equal(first.saved.get('enrollment').intent,'pause');
    let requests=0;global.fetch=async(_url,init)=>{requests++;assert.equal(JSON.parse(init.body).enabled,false);return new Response(JSON.stringify({sharing:false}));};
    const restarted=shell(Object.fromEntries(first.saved));await restarted.controller.initialize();
    assert.equal(restarted.saved.get('enrollment').intent,undefined);assert.equal(restarted.saved.get('enrollment').paused,true);assert.equal(restarted.controller.state.running,false);assert.equal(requests,1);
    await restarted.intervals[0]();assert.equal(requests,1);
  }finally{global.fetch=original}
});
test('offline disconnect retains only a pending revocation and a second company cannot replace it',async()=>{
  const original=global.fetch;global.fetch=async()=>{throw new Error('Offline')};
  try{
    const first=shell({enrollment:receipt});await first.controller.initialize();await first.controller.disconnect();
    assert.equal(first.saved.get('enrollment').intent,'disconnect');assert.equal(first.queueCleared,1);
    await assert.rejects(first.controller.preview(`neurasign://enroll#${new URLSearchParams({server:receipt.apiOrigin,token})}`),/Disconnect/);
    global.fetch=async()=>new Response(JSON.stringify({detail:'Revoked'}),{status:401});
    const restarted=shell(Object.fromEntries(first.saved));await restarted.controller.initialize();
    assert.equal(restarted.saved.has('enrollment'),false);assert.equal(restarted.controller.state.enrollment,null);
  }finally{global.fetch=original}
});

test('paired-watch capture checks nearby permissions before enabling server sharing or a foreground service', async () => {
  const original = global.fetch; let requests = 0, permissions = 0;
  global.fetch = async () => { requests++; throw new Error('Unexpected request'); };
  try {
    const first = shell({ enrollment: receipt }, {
      'react-native': { AppState: { currentState: 'active' }, Platform: { OS: 'android' } },
      './ble': { NativeBle: class { async stopScan() {} async permission() { permissions++; throw new Error('Nearby devices denied'); } } },
    });
    await first.controller.initialize();
    await assert.rejects(first.controller.start({ id: 'paired-watch', name: 'Watch', services: [], route: 'wear_os' }), /Nearby devices denied/);
    assert.equal(permissions, 1); assert.equal(requests, 0); assert.equal(first.controller.state.running, false);
    assert.deepEqual(first.saved.get('enrollment'), receipt);
  } finally { global.fetch = original; }
});

test('cloud sync bypasses Bluetooth and foreground services, and pauses through company controls', async () => {
  const original=global.fetch; const requests=[]; let started;
  const syncing = new Promise(resolve => { started=resolve; });
  global.fetch=async (url, init) => {
    requests.push(url);
    if (url.endsWith('/sync')) { started(); return new Response(JSON.stringify({accepted:2,warnings:[]})); }
    return new Response(JSON.stringify({sharing:true}));
  };
  try {
    const instance = shell({enrollment:receipt}, {
      'react-native': {AppState:{currentState:'active'},Platform:{OS:'android'}},
      './ble': {NativeBle: class { async stopScan(){} async permission(){throw Error('Cloud must not request Bluetooth');} }},
      'react-native-background-actions': {default:{isRunning:()=>false,start:()=>{throw Error('Cloud must not start connected-device service');}}},
    });
    await instance.controller.initialize();
    await instance.controller.start({id:'whoop',name:'WHOOP',services:[],route:'cloud'});
    await syncing;
    assert.equal(instance.controller.state.running,true);
    await instance.controller.pause();
    assert.equal(instance.controller.state.running,false);
    assert.equal(instance.saved.get('enrollment').paused,true);
    assert.equal(requests.filter(url=>url.endsWith('/sync')).length,1);
  } finally { global.fetch=original; }
});
