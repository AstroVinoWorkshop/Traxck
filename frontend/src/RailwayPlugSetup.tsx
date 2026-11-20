import {useEffect, useState, type FormEvent} from 'react';

type Config = {url:string;entity_id:string;credential_configured:boolean};

export function RailwayPlugSetup(){
  const [config,setConfig]=useState<Config|null>(null);
  const [url,setUrl]=useState('');
  const [entity,setEntity]=useState('');
  const [token,setToken]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  useEffect(()=>{
    let active=true;
    fetch('/api/railway-plug/config').then(async r=>{
      if(!r.headers.get('content-type')?.includes('application/json'))throw Error('Plug setup backend is not active yet. The control service needs a coordinated restart when hardware is safely disconnected.');
      const data=await r.json();if(!r.ok)throw Error(data.detail||'Unable to load plug setup');return data as Config;
    }).then(data=>{if(active){setConfig(data);setUrl(data.url);setEntity(data.entity_id)}})
      .catch(e=>{if(active)setError((e as Error).message)});
    return ()=>{active=false};
  },[]);
  async function save(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setBusy(true);setError('');setNotice('');
    try{
      const r=await fetch('/api/railway-plug/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:url.trim(),entity_id:entity.trim(),token})});
      const data=await r.json();
      if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Check the Home Assistant URL and entity ID');
      setConfig(data as Config);setUrl(data.url);setEntity(data.entity_id);setToken('');
      setNotice('Saved. No plug or track-power command was sent. Check status on Overview.');
    }catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  return <section className="panel connection-panel railway-plug-setup" aria-label="Model Railway Hue plug setup">
    <span className="eyebrow">HOME ASSISTANT / MAINS POWER</span>
    <h2>Model Railway Hue plug</h2>
    <p>Configure the mains plug powering DCC-EX and other railway equipment. This is separate from DCC-EX track power and is not an emergency stop.</p>
    <form onSubmit={save}>
      <label>Home Assistant URL<input type="url" required value={url} onChange={e=>setUrl(e.target.value)} placeholder="http://home-assistant:8123" autoComplete="url"/></label>
      <label>Plug entity ID<input required pattern="(switch|light)\.[a-z0-9_]+" title="A switch or light entity ID, for example switch.model_railway" value={entity} onChange={e=>setEntity(e.target.value)} placeholder="switch.model_railway" autoComplete="off"/></label>
      <label>Long-lived access token<input type="password" value={token} onChange={e=>setToken(e.target.value)} placeholder={config?.credential_configured?'Saved token (leave blank to keep)':'Paste Home Assistant token'} autoComplete="new-password" required={!config?.credential_configured}/></label>
      <button type="submit" className="secondary" disabled={busy||!config}>{busy?'Saving…':'Save plug setup'}</button>
    </form>
    <p className="railway-plug-setup-note">{!config?(error?'Save unavailable: the plug setup backend is offline. Your entries have not been saved.':'Checking plug setup backend…'):(config.credential_configured?'Token saved; its value is not displayed. Blank retains it.':'Token not configured.')} Saving does not switch the plug or connect to DCC-EX.</p>
    {error&&<p className="railway-plug-error" role="alert">{error}</p>}
    {notice&&<p className="railway-plug-setup-success" role="status">{notice}</p>}
  </section>;
}
