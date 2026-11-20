// Indicate only the last command accepted by this app, never physical position.
export function pointLastCommand(point, mode) {
  return mode === 'HARDWARE' ? (point.hardware_commanded ?? null) : (point.commanded ?? null);
}
