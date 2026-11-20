import {useEffect, useState} from 'react';
import {ArrowLeftRight, CircleStop, TrainFront} from 'lucide-react';
import {FunctionIcon} from './FunctionIcon';
import {functionNumbers} from './decoderControls.mjs';
import {locomotiveControlUnavailable, rosterControlAddress} from './quickControl.mjs';
import type {RosterEntry} from './RosterEditor';

type Loco={address:number;functions:{key:number;label:string;momentary:boolean;source:string;confidence:'manual'|'verified';icon?:string}[]};
type Props={entry:RosterEntry;locomotives:Loco[];mode:string;connected:boolean;power:boolean;estop:boolean;speed:{speed:number;direction:number}|undefined;activeFunctions:Record<string,boolean>|undefined;onThrottle:(address:number,speed:number,direction:number)=>void;onFunction:(address:number,key:number,on:boolean)=>void;onMomentaryStart:(address:number,key:number)=>void;onMomentaryRelease:()=>void;onOpenThrottle:(address:number)=>void};

export function QuickRosterControls({entry,locomotives,mode,connected,power,estop,speed,activeFunctions,onThrottle,onFunction,onMomentaryStart,onMomentaryRelease,onOpenThrottle}:Props){
 const address=rosterControlAddress(entry,locomotives);
 const loco=locomotives.find(item=>item.address===address);
 const disabled=locomotiveControlUnavailable(address,{mode,connected,power,estop});
 const currentSpeed=speed?.speed??0,direction=speed?.direction??1;
 const [draft,setDraft]=useState(currentSpeed),[dirty,setDirty]=useState(false);
 useEffect(()=>{if(!dirty)setDraft(currentSpeed)},[currentSpeed,dirty]);
 const commit=()=>{if(dirty){setDirty(false);if(!disabled&&address!==null&&draft!==currentSpeed)onThrottle(address,draft,direction)}};
 const mapped=loco?functionNumbers(loco.functions).filter(f=>f.mapped):[];
 return <div className="quick-roster-controls" aria-label={`${entry.name} quick controls`}>
  {address===null?<p className="quick-roster-warning">Set and verify the decoder DCC ID in Locomotives before driving.</p>:<>
   <div className="quick-roster-status"><span>DCC {address} · {mode==='HARDWARE'?'HARDWARE':'SIMULATION'}</span><span>{estop?'EMERGENCY STOP':!power?'TRACK POWER OFF':mode==='HARDWARE'&&!connected?'STATION DISCONNECTED':`STEP ${String(currentSpeed).padStart(2,'0')} / 126`}</span></div>
   <label className="quick-roster-speed" htmlFor={`quick-speed-${entry.id}`}><span>Throttle</span><strong>{draft} / 126</strong></label>
   <input id={`quick-speed-${entry.id}`} aria-label={`${entry.name} speed`} type="range" min="0" max="126" value={draft} disabled={disabled} onChange={e=>{setDraft(Number(e.target.value));setDirty(true)}} onPointerUp={commit} onPointerCancel={()=>{setDraft(currentSpeed);setDirty(false)}} onKeyUp={commit} onBlur={commit}/>
   <div className="quick-roster-actions"><button type="button" className="secondary" disabled={disabled||currentSpeed>0} title={currentSpeed>0?'Stop before changing direction':undefined} onClick={()=>onThrottle(address, 0, -direction)}><ArrowLeftRight size={16}/>Direction: {direction===1?'Forward':'Reverse'}</button><button type="button" className="secondary" disabled={disabled} onClick={()=>{setDraft(0);setDirty(false);onThrottle(address,0,direction)}}><CircleStop size={16}/>Stop train</button><button type="button" className="secondary" onClick={()=>onOpenThrottle(address)}><TrainFront size={16}/>Open throttle</button></div>
   <div className="quick-roster-functions"><strong>Mapped functions</strong>{mapped.length?<div className="quick-function-list">{mapped.map(f=>{const active=!!activeFunctions?.[String(f.key)];return <button type="button" key={f.key} disabled={disabled} className={'function '+(active?'active':'')} title={`${f.label}${f.momentary?' · hold to activate':''}`} onPointerDown={e=>{if(f.momentary){e.currentTarget.setPointerCapture(e.pointerId);onMomentaryStart(address,f.key)}}} onPointerUp={onMomentaryRelease} onPointerCancel={onMomentaryRelease} onLostPointerCapture={onMomentaryRelease} onKeyDown={e=>{if(f.momentary&&(e.key==='Enter'||e.key===' ')&&!e.repeat)onMomentaryStart(address,f.key)}} onKeyUp={e=>{if(f.momentary&&(e.key==='Enter'||e.key===' '))onMomentaryRelease()}} onBlur={onMomentaryRelease} onClick={()=>{if(!f.momentary)onFunction(address,f.key,!active)}}><small>F{f.key.toString().padStart(2,'0')}</small><FunctionIcon id={f.icon} size={18}/><span>{f.label}</span><i>{f.momentary?'HOLD':active?'ON':'OFF'}</i></button>})}</div>:<p>No sourced function mapping. Add one in Locomotives before use.</p>}</div>
  </>}
 </div>;
}
