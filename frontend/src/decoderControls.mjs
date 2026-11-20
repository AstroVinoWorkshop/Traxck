import {functionIconFor} from './functionIcons.mjs';
// Inventory is not an address: only entries surfaced as addressable locomotives may drive.
export function selectableRoster(roster, locomotives) {
  return roster.map(entry => ({
    id: entry.id,
    address: entry.address,
    disabled: entry.address == null || !locomotives.some(l => l.address === entry.address),
    label: entry.name + (entry.address == null ? ' · ID to confirm' : ' · DCC ' + entry.address),
  }));
}

// The app only exposes the supported F0–F28 range; unsourced slots stay inert.
export function functionNumbers(mappings) {
  return Array.from({length: 29}, (_, key) => {
    const mapped = mappings.find(f => f.key === key && f.source?.trim() && ['manual', 'verified'].includes(f.confidence));
    return {icon: mapped ? functionIconFor(mapped.label, mapped.icon) : 'function', key, label: mapped?.label || 'Not mapped', momentary: !!mapped?.momentary, mapped: !!mapped, source: mapped?.source, confidence: mapped?.confidence};
  });
}

export function validCvInput(cv, value) {
  return /^\d+$/.test(cv) && /^\d+$/.test(value) && Number(cv) >= 1 && Number(cv) <= 1024 && Number(value) >= 0 && Number(value) <= 255;
}
