export type PointCommandState = {mode:string;connected:boolean;power:boolean;estop:boolean};
export function nextPointPosition(point:{commanded?:string|null;hardware_commanded?:string|null},mode:string):'straight'|'diverging';
export function pointCommandUnavailable(point:{address:number|null},state:PointCommandState):boolean;
export function rosterControlAddress(entry:{address:number|null},locomotives:{address:number}[]):number|null;
export function locomotiveControlUnavailable(address:number|null,state:PointCommandState):boolean;
