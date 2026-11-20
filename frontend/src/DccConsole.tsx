import {useState} from 'react';
import {ArrowRight, Check, ChevronDown, Clock3, Terminal, Trash2} from 'lucide-react';

type Entry = {time: string; text: string; kind: 'sent'|'received'|'notice'|'error'};
// Catalogued against https://dcc-ex.com/reference/software/command-summary-consolidated.html
// The backend independently validates every command before transmission.
const commands = [
  {value:'<s>',label:'Version and station info',group:'System information',detail:'Request firmware and motor-controller details; also returns defined turnout states.'},
  {value:'<c>',label:'Track current',group:'System information',detail:'Request the station’s current report for the main track.'},
  {value:'<#>',label:'Available cab slots',group:'System information',detail:'Request the maximum number of locomotive slots.'},
  {value:'<J I>',label:'Track currents',group:'Power monitoring',detail:'Request current readings for defined tracks in milliamps.'},
  {value:'<J G>',label:'Current trip limits',group:'Power monitoring',detail:'Request maximum current trip values for defined tracks.'},
  {value:'<=>',label:'Track manager configuration',group:'Track manager',detail:'Request each track output’s current mode and assigned cab, where applicable.'},
  {value:'<J R>',label:'Roster IDs',group:'Station inventory',detail:'Request the list of command-station roster entries.'},
  {value:'<J T>',label:'Turnout IDs',group:'Station inventory',detail:'Request the list of defined turnout IDs.'},
  {value:'<J O>',label:'Turntable IDs',group:'Station inventory',detail:'Request the list of defined turntables and traversers.'},
  {value:'<J A>',label:'Route and automation IDs',group:'Station inventory',detail:'Request the list of EXRAIL routes and automations.'},
  {value:'<Q>',label:'Sensor states',group:'Station inventory',detail:'Request current states of defined sensors.'},
  {value:'<S>',label:'Sensor definitions',group:'Station inventory',detail:'Request the list of defined sensors and their input pins.'},
  {value:'<T>',label:'Turnout states',group:'Station inventory',detail:'Request states of defined turnouts.'},
  {value:'<I>',label:'Turntable positions',group:'Station inventory',detail:'Request current positions of defined turntables and traversers.'},
  {value:'<JC>',label:'Fast clock time',group:'Station inventory',detail:'Request the optional EX-FastClock time, if installed.'},
  {value:'<1 JOIN>',label:'Join main and programming tracks',group:'Power and track changes',detail:'Energises the programming output with the main-track signal. Check matching rail phase and compatible wiring before confirming.',locked:true},
  {value:'<0 MAIN>',label:'Main track power off',group:'Power and track changes',detail:'Cuts main-track power; the other output may remain powered. Verify the station reply.',locked:true},
  {value:'<1 MAIN>',label:'Main track power on',group:'Power and track changes',detail:'Energises the main output. Check wiring and confirm the station reply.',locked:true},
  {value:'<0 PROG>',label:'Programming track power off',group:'Power and track changes',detail:'Cuts programming output power; main output may remain powered.',locked:true},
  {value:'<1 PROG>',label:'Programming track power on',group:'Power and track changes',detail:'Energises the programming output. Confirm its wiring and track configuration before sending.',locked:true},
  {value:'<= A MAIN>',label:'Set track A to main',group:'Power and track changes',detail:'Changes Track Manager output configuration and automatically switches track power off. Not enabled here.',locked:true},
  {value:'<D RESET>',label:'Restart command station',group:'Power and track changes',detail:'Reboots the command station. Not available through the browser command desk.',locked:true},
  {value:'<0>',label:'Track power off',group:'Power and track changes',detail:'Cuts track power; check the station reply and use the physical cut-off if it is not confirmed.',locked:true},
  {value:'<1>',label:'Track power on',group:'Power and track changes',detail:'Energises track outputs. Check the railway before sending and verify the station reply.',locked:true},
  {value:'<t cab speed dir>',label:'Set locomotive speed',group:'Loco control',detail:'Requires a roster address, speed 0–126 and direction 0 or 1. No station acknowledgement is expected.',locked:true},
  {value:'<F cab function state>',label:'Set decoder function',group:'Loco control',detail:'Requires a roster address, valid function number and state 0 or 1. No station acknowledgement is expected.',locked:true},
  {value:'<T id state>',label:'Throw or close turnout',group:'Accessories and routes',detail:'Requires verified turnout IDs and hardware mapping; unavailable through this console.',locked:true},
  {value:'<a addr subaddr activate>',label:'Operate accessory decoder',group:'Accessories and routes',detail:'Sends accessory instructions to the rails. No hardware mapping is validated here.',locked:true},
  {value:'<A address aspect>',label:'Set signal aspect',group:'Accessories and routes',detail:'Sends an extended accessory packet. No signal mapping is validated here.',locked:true},
  {value:'</ START id>',label:'Start EXRAIL route',group:'Accessories and routes',detail:'Starts a configured route or automation; not enabled without route verification.',locked:true},
  {value:'</ KILL id>',label:'Stop EXRAIL route',group:'Accessories and routes',detail:'Stops a configured route or automation; not enabled without route verification.',locked:true},
  {value:'<R cv>',label:'Read programming-track CV',group:'Decoder programming',detail:'Requires an isolated programming track, verified main power off and stopped trains; CV 1–1024.',locked:true},
  {value:'<W cv value>',label:'Write programming-track CV',group:'Decoder programming',detail:'Requires an isolated programming track, verified main power off and stopped trains; CV 1–1024, value 0–255. Read back after writing.',locked:true},
  {value:'<w cab cv value>',label:'Write CV on main',group:'Decoder programming',detail:'No read-back on the main track; not available through this console.',locked:true},
  {value:'<R>',label:'Read decoder address',group:'Decoder programming',detail:'Reads the decoder address from an electrically isolated programming track.',locked:true},
  {value:'<V cv value>',label:'Verify CV value',group:'Decoder programming',detail:'Verifies a CV value on an electrically isolated programming track.',locked:true},
  {value:'<e>',label:'Erase EEPROM definitions',group:'Station configuration',detail:'Erases station turnout, sensor and output definitions. Destructive command never sent through this console.',locked:true},
  {value:'<E>',label:'Store EEPROM definitions',group:'Station configuration',detail:'Stores station definitions. Not enabled without a configuration backup.',locked:true},
  {value:'<D HAL SHOW>',label:'HAL device inventory',group:'Station configuration',detail:'Diagnostic output may be serial-monitor only, so this network console does not claim to display it.',locked:true},
  {value:'<D RAM>',label:'Free memory',group:'Station configuration',detail:'Diagnostic output is serial-monitor only and may not appear on this network connection.',locked:true},
  {value:'<C WIFI "ssid" "password">',label:'Join Wi-Fi network',group:'Station configuration',detail:'Changes network credentials and may disconnect the station; not enabled.',locked:true},
] as const;

// Keep the actionable library in sync with the backend allow-list. Other documented
// forms remain visible for explanation but cannot reach the send workflow.
const enabledCommands = new Set([
  '<s>','<c>','<#>','<J I>','<J G>','<=>','<J R>','<J T>','<J O>','<J A>','<Q>','<S>','<T>','<I>','<JC>',
  '<0>','<1>','<0 MAIN>','<1 MAIN>','<0 PROG>','<1 PROG>','<1 JOIN>',
  '<t cab speed dir>','<F cab function state>','<R cv>','<W cv value>',
]);

export function DccConsole({connected,onSetup,onProfiles}:{connected:boolean;onSetup:()=>void;onProfiles:()=>void}) {
  const [command, setCommand] = useState<string>('<s>');
  const [frame, setFrame] = useState('');
  const [pending, setPending] = useState<string|null>(null);
  const [wiringConfirmed, setWiringConfirmed] = useState(false);
  const [trackIsolated, setTrackIsolated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [entries, setEntries] = useState<Entry[]>([]);
  const add = (kind:Entry['kind'], text:string) => setEntries(old=>[...old,{kind,text,time:new Date().toLocaleTimeString()}].slice(-60));
  const choose = (value:string) => {setCommand(value); setFrame(''); setPending(null); setWiringConfirmed(false); setTrackIsolated(false)};
  const requiresParameters = /\b(?:cab|speed|dir|function|state|id|addr|subaddr|activate|address|aspect|cv|value|ssid|password)\b/.test(command);
  const completeCommand = requiresParameters ? frame.trim() : command;
  const isJoin = completeCommand==='<1 JOIN>';
  const isCv = /^<(?:R|W)\s/.test(completeCommand);
  const isWifi = command.startsWith('<C WIFI');
  const displayCommand = (value:string) => /^<C WIFI\b/.test(value) ? '<C WIFI [credentials redacted]>' : value;
  async function send() {
    if (!pending || busy || !connected) return;
    const selected = pending;
    setPending(null);
    setBusy(true);
    try {
      const response = await fetch('/api/hardware/command', {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({command:selected,confirmed:true,wiring_confirmed:wiringConfirmed,programming_track_isolated:trackIsolated})
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`);
      if (body.sent !== true) throw new Error('The station did not confirm that the command was sent');
      add('sent', displayCommand(selected));
      if (body.output) add('received', String(body.output));
      if (!body.acknowledged && body.status !== 'response_received') add('notice', 'Sent; no station acknowledgement was verified. Check the station and track before relying on the change.');
    } catch (error) {
      add('error', `${displayCommand(selected)}: ${error instanceof Error ? error.message : 'Request failed'}`);
    } finally {setBusy(false); setFrame(''); setWiringConfirmed(false); setTrackIsolated(false)}
  }
  const info = commands.find(item=>item.value===command);
  const enabled = enabledCommands.has(command);
  return <div className="dcc-workspace">
    <div className="dcc-intro"><div><span className="eyebrow">COMMAND STATION / OPERATOR WORKSPACE</span><h2>Command desk</h2><p>Choose a known DCC-EX command, review it, then explicitly confirm transmission. Station replies appear in the session console.</p></div><span className={'dcc-link '+(connected?'is-connected':'')}><span className="status-dot"/>{connected?'STATION ONLINE':'STATION OFFLINE'}</span></div>
    <div className="dcc-layout">
      <section className="panel dcc-control" aria-label="DCC-EX command selection">
        <div className="dcc-section-head"><span className="dcc-section-icon"><Terminal size={19}/></span><div><span className="eyebrow">01 / COMMAND LIBRARY</span><h2>DCC-EX commands</h2></div></div>
        <p className="dcc-muted">Choose a documented command and confirm each transmission. Unavailable forms are listed for reference but cannot be sent. Track and decoder changes can take effect immediately.</p>
        <label className="dcc-field" htmlFor="dcc-command"><span>KNOWN COMMAND</span><span className="dcc-select-wrap"><select id="dcc-command" value={command} onChange={e=>choose(e.target.value)} disabled={busy}>{[...new Set(commands.map(item=>item.group))].map(group=><optgroup key={group} label={group}>{commands.filter(item=>item.group===group).map(item=><option key={item.value} value={item.value}>{item.value}  ·  {item.label}{enabledCommands.has(item.value)?'':' (not available)'}</option>)}</optgroup>)}</select><ChevronDown size={17}/></span></label>
        <div className="dcc-command-card"><div><span className="eyebrow">SELECTED COMMAND</span><code>{command}</code></div><p>{info?.detail}</p><small>{info&&'locked' in info?'CHANGES THE STATION OR TRACK · explicit confirmation required':'STATION QUERY · reply appears in the console'}</small></div>
        {requiresParameters&&<label className="dcc-field" htmlFor="dcc-frame"><span>COMPLETE COMMAND · REPLACE PLACEHOLDERS</span><input id="dcc-frame" type={isWifi?'password':'text'} autoComplete="off" spellCheck={false} value={frame} onChange={e=>{setFrame(e.target.value);setPending(null)}} placeholder={command} maxLength={128}/></label>}
        {!connected&&<div className="dcc-connection-notice" role="status"><Clock3 size={16}/><span>Connect the station and select hardware control in Setup to enable sending.</span><button type="button" onClick={onSetup}>Open Setup <ArrowRight size={14}/></button></div>}
        {pending&&<div className="dcc-confirm" role="group" aria-label="Confirm DCC-EX command"><strong>Send <code>{displayCommand(pending)}</code> to the connected station?</strong><p>{info&&'locked' in info?'This command can change the station or energise the track. Check the command, wiring and affected equipment before sending.':'Confirm after checking the station connection.'}</p>{isJoin&&<label className="dcc-ack"><input type="checkbox" checked={wiringConfirmed} onChange={e=>setWiringConfirmed(e.target.checked)}/> I have checked that the main and programming rails are phase-matched and joining them is safe.</label>}{isCv&&<label className="dcc-ack"><input type="checkbox" checked={trackIsolated} onChange={e=>setTrackIsolated(e.target.checked)}/> I have checked that the programming track is electrically isolated from the main rails.</label>}<div><button disabled={!connected||busy||(isJoin&&!wiringConfirmed)||(isCv&&!trackIsolated)} onClick={send}><Check size={15}/> Confirm send</button><button className="secondary" onClick={()=>setPending(null)}>Cancel</button></div></div>}
        {!pending&&<button className="dcc-review" disabled={!connected||busy||!info||!enabled||!/^<[^<>\r\n]{1,124}>$/.test(completeCommand)} onClick={()=>setPending(completeCommand)}>{busy?'Waiting for station…':'Review command'} <ArrowRight size={16}/></button>}
      </section>
      <section className="panel dcc-terminal" aria-label="Interface console output"><div className="dcc-log-heading"><div><span className="eyebrow">02 / LIVE SESSION</span><h2>Interface console</h2></div><button className="secondary" onClick={()=>setEntries([])} disabled={!entries.length||busy}><Trash2 size={14}/> Clear</button></div><div className="dcc-output" role="log" aria-live="polite" aria-label="Station output">{entries.length?entries.map((entry,i)=><div className={'dcc-entry '+entry.kind} key={i}><time>{entry.time}</time><span>{entry.kind==='sent'?'TX':entry.kind==='received'?'RX':entry.kind==='notice'?'INFO':'ERR'}</span><code>{entry.text}</code></div>):<div className="dcc-empty"><Terminal size={25}/><strong>Awaiting station response</strong><span>Commands and replies from this session will appear here.</span></div>}</div><div className="dcc-terminal-foot">SESSION ONLY <span>·</span> {entries.length} {entries.length===1?'ENTRY':'ENTRIES'} <span>·</span> NO AUTO-SEND</div></section>
    </div>
    <section className="panel dcc-profile"><div><span className="eyebrow">DECODER PROGRAMMING / PROFILES</span><h2>CV profiles</h2><p>Record proposed CV values and consult the decoder reference from a locomotive’s profile. These notes are offline; direct programming commands above require an electrically isolated programming track and explicit confirmation. Confirm actual CV results from the station response.</p></div><button className="secondary" onClick={onProfiles}>Open locomotive profiles <ArrowRight size={16}/></button></section>
  </div>;
}
