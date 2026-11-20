export type Mapping = {key:number;label:string;momentary:boolean;icon?:string};
export function selectableRoster(roster:{id:string;name:string;address:number|null}[], locomotives:{address:number}[]):{id:string;address:number|null;disabled:boolean;label:string}[];
export function functionNumbers(mappings:Mapping[]):(Mapping & {mapped:boolean})[];
export function validCvInput(cv:string,value:string):boolean;
