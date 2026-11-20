import React from 'react';
import {layoutPointStatus} from './layoutPointStatus.mjs';

export type Kind='observed-main'|'observed-inner'|'observed-station'|'observed-siding'|'straight'|'short-straight'|'curve'|'wide-curve'|'left-point'|'right-point'|'curved-left-point'|'curved-right-point'|'y-point'|'three-way-point'|'diamond'|'single-slip'|'double-slip'|'buffer-stop'|'uncoupler'|'point-motor'|'pillar'|'peco-flex'|'roco-35900'|'tunnel-portal'|'bridge'|'level-crossing'|'elevated-line'|'shelf-outline'|'platform-pair'|'plan-label';
export type Piece={id:string;kind:Kind;x:number;y:number;rotation:number;length:number;curve:number;text?:string};
export type Building={id:string;name:string;x:number;y:number;width:number;height:number;rotation:number};
export type Vertex={x:number;y:number};
export type CanvasSize={width:number;height:number};
export const DEFAULT_PERIMETER:Vertex[]=[{x:22,y:28},{x:878,y:28},{x:878,y:261},{x:273,y:261},{x:273,y:477},{x:22,y:477}];
export type Layout={name:string;segments:{x1:number;y1:number;x2:number;y2:number}[];pieces?:Piece[];buildings?:Building[];diagramVersion?:number|null;perimeter?:Vertex[];canvas?:CanvasSize};
export const INITIAL_BUILDINGS:Building[]=[
 {id:'initial-industrial-building',name:'Industrial building',x:40,y:336,width:45,height:73,rotation:0},
 {id:'initial-station-building',name:'Station',x:445,y:75,width:103,height:28,rotation:0},
 {id:'initial-track-shed',name:'Track fan / shed',x:776,y:74,width:79,height:27,rotation:0},
];
export const visibleBuildings=(buildings?:Building[])=>buildings??INITIAL_BUILDINGS;

// The initial editable pieces reproduce the overview rather than a second invented drawing.
// Initial observed rails remain editable, including the two curves and long arm.
export const INITIAL_PIECES:Piece[]=[
 {id:'observed-main',kind:'observed-main',x:0,y:0,rotation:0,length:360,curve:0},
 {id:'observed-inner',kind:'observed-inner',x:0,y:0,rotation:0,length:360,curve:0},
 {id:'observed-station',kind:'observed-station',x:0,y:0,rotation:0,length:360,curve:0},
 {id:'observed-siding',kind:'observed-siding',x:0,y:0,rotation:0,length:360,curve:0},
 {id:'observed-turntable',kind:'roco-35900',x:270,y:96,rotation:-28,length:90,curve:0},
];
// Previously hard-coded drawing is added once to old plans. The version flag
// makes deletion durable: removed decorations never reappear after Save.
export const INITIAL_DECORATIONS:Piece[]=[
 {id:'initial-shelf-outline',kind:'shelf-outline',x:450,y:250,rotation:0,length:360,curve:0},
 {id:'initial-zone-corner',kind:'plan-label',x:45,y:56,rotation:0,length:160,curve:0,text:'02 / CORNER + TURNTABLE'},
 {id:'initial-zone-station',kind:'plan-label',x:396,y:56,rotation:0,length:130,curve:0,text:'03 / STATION'},
 {id:'initial-zone-end',kind:'plan-label',x:694,y:56,rotation:0,length:170,curve:0,text:'04 / MULTI-TRACK END'},
 {id:'initial-zone-arm',kind:'plan-label',x:42,y:295,rotation:0,length:190,curve:0,text:'01 / SHORT INDUSTRIAL ARM'},
 {id:'initial-platform-pair',kind:'platform-pair',x:511,y:181,rotation:0,length:223,curve:0},
 {id:'initial-tunnel-portal',kind:'tunnel-portal',x:829,y:118,rotation:0,length:42,curve:0},
 {id:'initial-turntable-label',kind:'plan-label',x:210,y:64,rotation:0,length:90,curve:0,text:'TURNTABLE'},
 {id:'initial-tunnel-label',kind:'plan-label',x:780,y:147,rotation:0,length:100,curve:0,text:'TUNNEL END'},
 {id:'initial-elevated-line',kind:'elevated-line',x:58,y:304,rotation:0,length:145,curve:0},
 {id:'initial-elevated-label',kind:'plan-label',x:44,y:225,rotation:0,length:90,curve:0,text:'ELEVATED LINE'},
 {id:'initial-video-note',kind:'plan-label',x:42,y:461,rotation:0,length:360,curve:0,text:'VIDEO START ↓  •  SHORT ARM ON LEFT  •  RAIL LINKS / POINT IDS NOT SURVEYED'},
];
export const visiblePieces=(pieces?:Piece[],diagramVersion?:number|null)=>diagramVersion===2?(pieces??[]):[...(pieces??INITIAL_PIECES),...INITIAL_DECORATIONS.filter(d=>!pieces?.some(p=>p.id===d.id))];
export const observed=(kind:Kind)=>kind.startsWith('observed-');
export const scenery=(kind:Kind)=>['tunnel-portal','bridge','level-crossing','elevated-line','shelf-outline','platform-pair','plan-label','point-motor','pillar'].includes(kind);
export function pieceGeometry(kind:Kind,length:number,curve:number,text?:string){
  const a=-length/2,b=length/2;
  if(kind==='point-motor')return <><rect x="-13" y="-11" width="26" height="22" rx="4" fill="#163d45" stroke="#62cddd" strokeWidth="2"/><circle r="4" fill="#e4b663" stroke="none"/><path d="M 0 -11 V -21 M -6 -21 H 6" stroke="#62cddd" strokeWidth="2"/></>;
  if(kind==='pillar')return <><ellipse cy="9" rx="14" ry="5" fill="#26353a" stroke="#c89f67" strokeWidth="2"/><rect x="-10" y="-13" width="20" height="21" fill="#394b50" stroke="#c89f67" strokeWidth="2"/><ellipse cy="-13" rx="10" ry="4" fill="#536d70" stroke="#e4b663" strokeWidth="2"/></>;
  if(kind==='shelf-outline')return <path d="M -428 -222 H 428 V 11 H -177 V 227 H -428 Z" stroke="#35515a" strokeWidth="1.5" strokeDasharray="6 5"/>;
  if(kind==='plan-label')return <text x="0" y="0" fill="#9bbfbc" stroke="none" fontSize="10" fontWeight="700" letterSpacing=".6">{text||'New label'}</text>;
  if(kind==='platform-pair')return <><path d={`M ${a} -17 H ${b} M ${a} 17 H ${b}`} stroke="#dcb46d" strokeWidth="7"/></>;
  if(kind==='tunnel-portal')return <><rect x={a} y="-12" width={length} height="24" rx="7" fill="#17252a" stroke="#668486" strokeWidth="1.5"/><path d={`M ${a+1} 10 Q 0 -19 ${b-1} 10`} stroke="#e4b663" strokeWidth="2"/></>;
  if(kind==='bridge')return <><path d={`M ${a} -13 H ${b} M ${a} 13 H ${b}`} stroke="#c89f67" strokeWidth="5"/><path d={`M ${a+8} -13 V 13 M 0 -13 V 13 M ${b-8} -13 V 13`} stroke="#c89f67" strokeWidth="2"/></>;
  if(kind==='level-crossing')return <><path d={`M ${a} -14 H ${b} M ${a} 14 H ${b}`} stroke="#9db1a5" strokeWidth="3" strokeDasharray="7 4"/><path d={`M -13 -24 V 24 M 13 -24 V 24`} stroke="#e4b663" strokeWidth="4"/></>;
  if(kind==='elevated-line')return <path d={`M 0 0 V -89 Q 0 -180 ${length*.92} -218`} stroke="#c89f67" strokeWidth="2" strokeDasharray="5 6"/>;
  if(kind==='observed-main')return <path d="M 92 421 V 242 Q 92 148 291 148 H 835"/>;
 if(kind==='observed-inner')return <path d="M 127 417 V 243 Q 127 183 293 183 H 835"/>;
 if(kind==='observed-station')return <path d="M 298 213 H 835"/>;
 if(kind==='observed-siding')return <path d="M 699 236 H 835"/>;
 if(kind==='roco-35900')return <><circle r="31" fill="#15383b" stroke="#a9d9d1" strokeWidth="2"/><path d={`M ${a*.59} 0 H ${b*.59}`} stroke="#dcb46d" strokeWidth="4"/></>;
 if(kind==='buffer-stop')return <><path d={`M ${a} 0 H ${b}`} /><path d={`M ${b} -16 V 16`} strokeWidth="6"/></>;
 if(kind==='uncoupler')return <><path d={`M ${a} 0 H ${b}`} /><path d="M -8 -9 L 8 9 M -8 9 L 8 -9" stroke="#e5bb72"/></>;
 if(kind==='curve'||kind==='wide-curve'||kind==='peco-flex')return <path d={`M ${a} 0 Q 0 ${-curve*2} ${b} 0`}/>;
 if(kind==='diamond'||kind==='single-slip'||kind==='double-slip')return <><path d={`M ${a} -18 L ${b} 18 M ${a} 18 L ${b} -18`}/>{kind!=='diamond'&&<path d={`M ${a*.7} ${kind==='double-slip'?10:-10} Q 0 0 ${b*.7} ${kind==='double-slip'?-10:10}`} stroke="#e5bb72"/>}</>;
 if(kind.includes('point'))return <><path d={`M ${a} 0 H ${b}`}/>{kind==='three-way-point'||kind==='y-point'?<path d={`M ${a} 0 Q 0 ${-curve} ${b} ${-curve} M ${a} 0 Q 0 ${curve} ${b} ${curve}`}/>:<path d={`M ${a} 0 Q 0 ${curve*1.2} ${b} ${curve}`}/>}</>;
 return <path d={`M ${a} 0 H ${b}`}/>;
}
const partName=(kind:Kind)=>kind.replace('observed-','').replace(/-/g,' ');
export function TrackDiagram({pieces,buildings,segments,perimeter=DEFAULT_PERIMETER,canvas={width:900,height:500},selected,selectedIds=[],selectionBox,onBackgroundPointerDown,onVertexPointerDown,onPointerDown,onBuildingPointerDown,onSelect,svgRef,onPointerMove,onPointerUp,onDrop,onDragOver,editable=false,points=[],mode='SIMULATION'}:{pieces:Piece[];buildings:Building[];segments:Layout['segments'];points?:{id:string;commanded?:string|null;hardware_commanded?:string|null}[];mode?:string;perimeter?:Vertex[];canvas?:CanvasSize;selected?:string|null;selectedIds?:string[];selectionBox?:{x:number;y:number;width:number;height:number}|null;onBackgroundPointerDown?:React.PointerEventHandler<SVGRectElement>;onVertexPointerDown?:(e:React.PointerEvent<SVGCircleElement>,index:number)=>void;onPointerDown?:(e:React.PointerEvent<SVGGElement>,id:string)=>void;onBuildingPointerDown?:(e:React.PointerEvent<SVGGElement>,id:string)=>void;onSelect?:(id:string)=>void;svgRef?:React.Ref<SVGSVGElement>;onPointerMove?:React.PointerEventHandler<SVGSVGElement>;onPointerUp?:React.PointerEventHandler<SVGSVGElement>;onDrop?:React.DragEventHandler<SVGSVGElement>;onDragOver?:React.DragEventHandler<SVGSVGElement>;editable?:boolean}){
 const outline=perimeter.map(p=>`${p.x},${p.y}`).join(' ');
 return <svg ref={svgRef} className={editable?'editable-map':'track-map'} viewBox={`0 0 ${canvas.width} ${canvas.height}`} role="img" aria-label={editable?'Editable track plan':'Workshop shelf track plan'} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp} onDrop={onDrop} onDragOver={onDragOver}>
  <defs><pattern id={editable?'edit-grid':'overview-grid'} width="28" height="28" patternUnits="userSpaceOnUse"><path d="M 28 0 L 0 0 0 28" fill="none" stroke="#20353b" strokeWidth=".6"/></pattern></defs>
  <polygon points={outline} fill="#0c1c22"/><polygon points={outline} fill={`url(#${editable?'edit-grid':'overview-grid'})`}/>
  {editable&&<rect width={canvas.width} height={canvas.height} fill="transparent" onPointerDown={onBackgroundPointerDown} data-testid="map-background"/>}
  {buildings.map(b=><g key={b.id} className={'map-building '+(editable?'editable-building ':'')+(selectedIds.includes(b.id)?'chosen':'')} transform={`translate(${b.x} ${b.y}) rotate(${b.rotation} ${b.width/2} ${b.height/2})`} onPointerDown={editable?e=>onBuildingPointerDown?.(e,b.id):undefined} role={editable?'button':undefined} tabIndex={editable?0:undefined} aria-label={editable?'Select and drag building '+b.name:undefined} onKeyDown={editable?e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect?.(b.id)}}:undefined}><title>{b.name}</title><rect width={b.width} height={b.height} rx="3"/><text x={b.width/2} y={b.height/2} textAnchor="middle" dominantBaseline="middle">{b.name.length>Math.max(5,Math.floor(b.width/7))?b.name.slice(0,Math.max(4,Math.floor(b.width/7)-1))+'…':b.name}</text></g>)}
  {[...pieces].sort((a,b)=>Number(scenery(b.kind))-Number(scenery(a.kind))).map(p=>{const status=layoutPointStatus(p,points,mode);const color=status.position==='straight'?'#51cb87':status.position==='diverging'?'#ff6b6b':'#8ca5a9';return <g key={p.id} className={editable?'editable-piece '+(selectedIds.includes(p.id)?'chosen':''):''} transform={`translate(${p.x} ${p.y}) rotate(${p.rotation}) ${observed(p.kind)||p.kind==='shelf-outline'?`scale(${p.length/360})`:['point-motor','pillar'].includes(p.kind)?`scale(${p.length/50})`:''}`} onPointerDown={editable?e=>onPointerDown?.(e,p.id):undefined} role={editable?'button':undefined} aria-label={editable?'Select and drag '+(p.text||partName(p.kind)):undefined} tabIndex={editable?0:undefined} onKeyDown={editable?e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect?.(p.id)}}:undefined}>
   <g fill="none" stroke="#a2ddd4" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">{pieceGeometry(p.kind,p.length,p.curve,p.text)}</g>
   {!editable&&p.kind==='point-motor'&&<g pointerEvents="none"><title>{status.id?`${status.id}: ${status.position??'no command'} last commanded in ${mode.toLowerCase()}; physical position unverified`:'Point motor location not linked to a point ID'}</title><rect x="-14" y="-12" width="28" height="24" rx="4" fill="#14292e" stroke={color} strokeWidth="2.5"/><circle r="5" fill={color}/>{status.id&&<text x="0" y="-18" textAnchor="middle" fill={color} stroke="none" fontSize="9" fontWeight="700" transform={`rotate(${-p.rotation})`}>{status.id}</text>}</g>}
   {editable&&p.kind==='shelf-outline'&&<path d="M -428 -222 H 428 V 11 H -177 V 227 H -428 Z" fill="none" stroke="transparent" strokeWidth="18"/>}
   {editable&&p.kind==='elevated-line'&&<path d={`M 0 0 V -89 Q 0 -180 ${p.length*.92} -218`} fill="none" stroke="transparent" strokeWidth="18"/>}
   {editable&&p.kind==='plan-label'&&<rect x="0" y="-12" width={Math.max(p.length,30)} height="17" fill="transparent"/>}
   {editable&&['platform-pair','tunnel-portal','bridge','level-crossing'].includes(p.kind)&&<rect x={-p.length/2} y="-22" width={p.length} height="44" fill="transparent"/>}
   {editable&&!scenery(p.kind)&&<g fill="none" stroke="transparent" strokeWidth="22" strokeLinecap="round" strokeLinejoin="round">{pieceGeometry(p.kind,p.length,p.curve)}</g>}
   {editable&&p.id===selected&&<circle cx={observed(p.kind)?420:0} cy={observed(p.kind)?180:0} r="7" fill="#e4b663" pointerEvents="none"/>}
  </g>})}
  {segments.map((s,i)=><line key={i} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} stroke="#e4b663" strokeWidth="4" strokeLinecap="round"/>)}
  <polygon points={outline} fill="none" stroke="#5d8585" strokeWidth="2" strokeDasharray="7 5" pointerEvents="none"/>
  {editable&&onVertexPointerDown&&perimeter.map((p,i)=><circle key={i} cx={p.x} cy={p.y} r="9" className="perimeter-handle" role="button" aria-label={`Move perimeter corner ${i+1}`} onPointerDown={e=>onVertexPointerDown(e,i)}/>)}
  {selectionBox&&<rect {...selectionBox} className="selection-box" pointerEvents="none"/>}
 </svg>;
}
