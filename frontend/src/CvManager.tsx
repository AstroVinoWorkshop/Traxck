import {useEffect,useState} from 'react';
import {validCvInput} from './decoderControls.mjs';
import {cvDescription,cvReference,cvReferenceSource} from './cvReference.mjs';
import type {RosterEntry} from './RosterEditor';

type Props={entry:RosterEntry;mode:string;connected:boolean;power:boolean;mainPowerOffVerified:boolean;estop:boolean;moving:boolean;addressable:boolean;onClose:()=>void;onStored:()=>void};
type Profile={id:string;stored_values:Record<string,number>};
const pageSize=64;

export function CvManager({entry,onClose,onStored}:Props){
 const [stored,setStored]=useState<Record<string,number>>({});
 const [cv,setCv]=useState('1'),[value,setValue]=useState('');
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[refreshing,setRefreshing]=useState(false);
 const [loadedAt,setLoadedAt]=useState<string|null>(null),[filter,setFilter]=useState(''),[page,setPage]=useState(0);
 const chosen=Number(cv),validCv=/^\d+$/.test(cv)&&chosen>=1&&chosen<=1024;
 const base='/api/roster/'+encodeURIComponent(entry.id)+'/cvs';
 async function refresh(){
  setRefreshing(true);setError('');
  try{const r=await fetch(base,{cache:'no-store'});const data=await r.json() as Profile;if(!r.ok)throw Error((data as Profile & {detail?:string}).detail||'Could not load stored CVs');setStored(data.stored_values||{});setLoadedAt(new Date().toLocaleTimeString());}
  catch(e){setError((e as Error).message)}finally{setRefreshing(false)}
 }
 useEffect(()=>{void refresh()},[entry.id]);
 async function run(kind:'save'|'delete'){
  if(!validCv||(kind==='save'&&!validCvInput(cv,value)))return setError('Enter CV 1–1024 and value 0–255.');
  setBusy(true);setError('');
  try{
   const response=await fetch(base+'/'+cv,{method:kind==='delete'?'DELETE':'PUT',headers:{'Content-Type':'application/json'},body:kind==='delete'?undefined:JSON.stringify({value:Number(value)})});
   const data=await response.json();if(!response.ok)throw Error(data.detail||'CV operation failed');
   await refresh();onStored();
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 const query=filter.trim().toLowerCase();
 const rows=cvReference.filter(({number,description}:{number:number;description:string})=>!query||String(number)===query.replace(/^cv\s*/,'')||('cv'+number+' '+description).toLowerCase().includes(query));
 const totalPages=Math.ceil(rows.length/pageSize),currentPage=Math.min(page,Math.max(0,totalPages-1));
 return <div className="camera-overlay" role="dialog" aria-modal="true" aria-label={'CV settings for '+entry.name}><div className="panel camera-dialog roster-dialog cv-dialog"><div className="panel-heading"><div><span className="eyebrow">DECODER CV PROFILE</span><h2>{entry.name}</h2><small>Roster address: {entry.address??'not recorded'} · {entry.decoder||'decoder not recorded'}</small></div><button type="button" className="secondary" onClick={onClose}>Close</button></div>
 <section><h3>Stored profile · offline only</h3><p>Values are saved against this vehicle, not read from its decoder. Unknown means no value recorded, not zero. Refresh reloads the saved profile only and sends no hardware command.</p><div className="photo-actions"><button type="button" className="secondary" disabled={refreshing||busy} onClick={()=>void refresh()}>{refreshing?'Refreshing…':'Refresh saved CVs'}</button><small>{loadedAt?'Last loaded '+loadedAt:'Not loaded yet'} · {Object.keys(stored).length} saved values</small></div><div className="cv-fields"><label>CV number (1–1024)<input type="number" min="1" max="1024" value={cv} onChange={e=>setCv(e.target.value)}/></label><label>Stored / proposed value (0–255)<input type="number" min="0" max="255" value={value} onChange={e=>setValue(e.target.value)}/></label></div><small>{validCv?cvDescription(chosen):'Select a CV number.'} · Check this decoder’s manual before editing.</small><div className="photo-actions"><button className="secondary" disabled={busy||!validCvInput(cv,value)} onClick={()=>run('save')}>Save to roster only</button><button className="secondary" disabled={busy||!validCv||stored[cv]===undefined} onClick={()=>run('delete')}>Remove stored value</button></div></section>
 <section><h3>Standard CV numbering reference (1–1024)</h3><p>This complete NMRA multi-function CV number range is a reference, not 1,024 expected values: many CVs are optional, reserved, indexed, or manufacturer-specific. Actual support, factory defaults and current values depend on the fitted decoder. A roster DCC address does not establish CV1 or CV17/18 values.</p><p><a href={cvReferenceSource} target="_blank" rel="noopener noreferrer">Source: NMRA S-9.2.2, Table 1 (2012.07)</a>. For SUSI CVs see TN-9.2.3 and consult the decoder manual for vendor-specific definitions.</p><label>Find CV number or description<input type="search" value={filter} onChange={e=>{setFilter(e.target.value);setPage(0)}} placeholder="e.g. 29, speed table, manufacturer"/></label><div className="cv-reference-list" aria-label="Standard CV reference for this vehicle">{rows.slice(currentPage*pageSize,(currentPage+1)*pageSize).map(({number,description}:{number:number;description:string})=><button type="button" className="cv-reference-row" key={number} onClick={()=>{setCv(String(number));setValue(stored[number]===undefined?'':String(stored[number]))}}><strong>CV{number}</strong><span>{description}</span><em>{stored[number]===undefined?'Unknown':'Saved: '+stored[number]}</em></button>)}</div>{!rows.length&&<p>No matching CV number or description.</p>}<div className="photo-actions"><button className="secondary" disabled={currentPage===0} onClick={()=>setPage(currentPage-1)}>Previous</button><span>{rows.length} CVs · page {totalPages?currentPage+1:0} of {totalPages}</span><button className="secondary" disabled={currentPage+1>=totalPages} onClick={()=>setPage(currentPage+1)}>Next</button></div></section>
 <section><h3>Live decoder read-back · unavailable</h3><p className="cv-gate">Refreshing cannot read CVs from a locomotive on the main track. Live CV discovery, reads and writes remain disabled until an actual isolated programming track and command-station read-back are validated. No operator checkbox can enable them.</p></section>
 {error&&<p role="alert" className="cv-error">{error}</p>}</div></div>
}
