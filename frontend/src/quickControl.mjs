import {pointLastCommand} from './pointStatus.mjs';

export function nextPointPosition(point, mode) {
  return pointLastCommand(point,mode)==='straight' ? 'diverging' : 'straight';
}
export function pointCommandUnavailable(point,{mode,connected,power,estop}) {
  return !!estop || (mode==='HARDWARE' && (!Number.isInteger(point.address) || point.address<1 || !connected || !power));
}
export function rosterControlAddress(entry,locomotives) {
  return Number.isInteger(entry.address) && entry.address>0 && locomotives.some(loco=>loco.address===entry.address) ? entry.address : null;
}
export function locomotiveControlUnavailable(address,{mode,connected,power,estop}) {
  return address==null || !power || !!estop || (mode==='HARDWARE' && !connected);
}
