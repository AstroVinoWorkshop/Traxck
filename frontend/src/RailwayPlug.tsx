import {useEffect, useRef, useState} from 'react';
import {Power} from 'lucide-react';

type Plug = {configured:boolean;available:boolean;on:boolean|null;entity_id:string|null;message:string|null};

export function RailwayPlug(){
  const [plug,setPlug]=useState<Plug|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [pending,setPending]=useState<boolean|null>(null);
  const confirmButton=useRef<HTMLButtonElement>(null);
  useEffect(()=>{if(pending!==null)confirmButton.current?.focus()},[pending]);
  useEffect(()=>{
    let live=true;
    async function refresh(){try{const r=await fetch('/api/railway-plug');if(!r.ok)throw Error('Plug status unavailable');const data=await r.json();if(live)setPlug(data)}catch{if(live)setPlug({configured:false,available:false,on:null,entity_id:null,message:'Plug status unavailable'})}}
    refresh();const timer=window.setInterval(refresh,8000);return ()=>{live=false;window.clearInterval(timer)};
  },[]);
  async function confirmToggle(){
    if(pending===null||!plug?.available||busy)return;
    const desired=pending;
    setPending(null);
    if(desired===plug.on)return;
    setBusy(true);setError('');
    try{
      const r=await fetch('/api/railway-plug',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({on:desired,confirmed:true})});
      const data=await r.json();if(!r.ok)throw Error(data.detail||'Plug command failed');setPlug(data);
    }catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  const status=!plug?'Checking…':!plug.configured?'Not configured':!plug.available?'Unavailable':plug.on?'On':'Off';
  return <section className="railway-plug" aria-label="Model Railway mains plug" title="Hue mains plug: powers DCC-EX and other railway equipment. Separate from track power; not an emergency stop.">
    <div className="railway-plug-line">
      <div className="railway-plug-label"><Power size={16} aria-hidden="true"/><span>Railway mains</span><small>HUE PLUG</small></div>
      <div className="railway-plug-actions"><span className={'railway-plug-state'+(plug?.available&&plug.on?' is-on':'')} role="status">{status}</span>
        <button type="button" className="railway-plug-button" aria-label={plug?.on?'Turn Model Railway mains plug off':'Turn Model Railway mains plug on'} aria-expanded={pending!==null} aria-controls="railway-plug-confirm" disabled={!plug?.available||busy} onClick={()=>{setError('');setPending(pending===null?!plug?.on:null)}}>{busy?'Verifying…':plug?.on?'Turn off':'Turn on'}</button></div>
    </div>
    {pending!==null&&<div id="railway-plug-confirm" className="railway-plug-confirm" onKeyDown={e=>{if(e.key==='Escape'){setPending(null);e.stopPropagation()}}}>
      <p><strong>{pending?'Turn railway mains on?':'Turn railway mains off?'}</strong> {pending?'This energises DCC-EX and other railway equipment, not just the track.':'This cuts mains power to DCC-EX and other railway equipment. This is not a track emergency stop.'}</p>
      <div className="railway-plug-confirm-actions"><button type="button" className="railway-plug-button" onClick={()=>setPending(null)}>Cancel</button><button ref={confirmButton} type="button" className="railway-plug-button railway-plug-confirm-primary" disabled={!plug?.available||busy||pending===plug.on} onClick={confirmToggle}>{pending?'Confirm turn on':'Confirm turn off'}</button></div>
    </div>}
    {error&&<p className="railway-plug-error" role="alert">{error}</p>}
  </section>;
}
