import {pointLastCommand} from './pointStatus.mjs';

// A map marker is an independently placed location. Only an explicit P-ID link
// makes it reflect a point command; neither proximity nor array order is safe.
export function layoutPointStatus(piece, points, mode) {
  const id = piece.kind === 'point-motor' && /^P[1-9][0-9]*$/.test(piece.text ?? '') ? piece.text : null;
  const point = id && points.find(p => p.id === id);
  return point ? {id, position: pointLastCommand(point, mode)} : {id:null, position:null};
}
