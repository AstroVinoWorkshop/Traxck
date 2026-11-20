// Locally drawn Lucide symbols; IDs are persisted, not coupled to any product artwork.
export const functionIcons = [
  ['General', [['function','Function'],['power','Power'],['play','Start'],['stop','Stop'],['check','Confirm']]],
  ['Sounds', [['whistle','Whistle'],['horn','Horn'],['bell','Bell'],['speaker','Speaker'],['mute','Mute'],['volume-up','Volume up'],['volume-down','Volume down'],['announcement','Announcement'],['radio','Radio'],['music','Music'],['brake','Brake squeal'],['compressor','Compressor'],['engine','Engine'],['diesel','Diesel engine'],['steam','Steam chuff']]],
  ['Lights', [['headlight','Headlight'],['rear-light','Rear light'],['cab-light','Cab light'],['interior-light','Interior light'],['marker-light','Marker light'],['flashing-light','Flashing light'],['beacon','Beacon'],['dim-light','Dim light']]],
  ['Movement & effects', [['shunting','Shunting'],['coupler','Coupler'],['doors','Doors'],['fan','Fan'],['smoke','Smoke'],['steam-release','Steam release'],['pantograph','Pantograph'],['wipers','Wipers'],['gear','Gear'],['train','Train'],['clock','Timer'],['warning','Warning'],['spark','Spark']]],
];
export const functionIconIds = functionIcons.flatMap(([, entries]) => entries.map(([id]) => id));
export function resolveFunctionIcon(id) { return functionIconIds.includes(id) ? id : 'function'; }

// Presentation only: never infer a decoder F-number or button behaviour from a label.
// Specific matches precede broad ones (e.g. brake squeal before brake).
const labelRules = [
  [/\b(?:day|head|front)\s*light\b/i, 'headlight'],
  [/\b(?:rear|tail)\s*light\b/i, 'rear-light'],
  [/\bcab\s*light\b/i, 'cab-light'],
  [/\b(?:aux(?:iliary)?|interior|coach)\s*light(?:ing)?\b/i, 'interior-light'],
  [/\b(?:flash(?:ing)?|strobe)\s*light\b/i, 'flashing-light'],
  [/\blight(?:ing)?\b/i, 'headlight'],
  [/\b(?:guard(?:s|'s)?\s*)?whistles?\b/i, 'whistle'],
  [/\bhorns?\b/i, 'horn'],
  [/\bbell\b/i, 'bell'],
  [/\b(?:windscreen\s*)?wipers?\b/i, 'wipers'],
  [/\bcompressor\b/i, 'compressor'],
  [/\b(?:buffering|buffer)\s*up\b/i, 'coupler'],
  [/\b(?:sound\s*(?:on\/?off|off|on)|mute)\b/i, 'speaker'],
  [/\b(?:brake\s*squeal|flange\s*squeal|wheel\s*slip)\b/i, 'brake'],
  [/\b(?:carriage\s*brake|brake)\b/i, 'brake'],
  [/\b(?:coupling|uncoupl(?:e|ing)|coupler)\b/i, 'coupler'],
  [/\b(?:door|doors)\b/i, 'doors'],
  [/\b(?:shunting|creep)\s*mode\b/i, 'shunting'],
  [/\b(?:automated|automatic)\s*function\s*control\b/i, 'gear'],
  [/\b(?:cylinder\s*cock|safety\s*valve|injector\s*valve|spirax\s*valve|blow\s*down|blower)\b/i, 'steam-release'],
  [/\b(?:coal|fireman|firebox|water|chuff(?:ing)?|coasting|steam|smoke)\b/i, 'steam'],
  [/\b(?:diesel|engine\s*thrash)\b/i, 'diesel'],
  [/\b(?:engine|idle)\b/i, 'engine'],
  [/\b(?:announcement|guard)\b/i, 'announcement'],
];
export function inferFunctionIcon(label) {
  if (typeof label !== 'string') return 'function';
  return labelRules.find(([pattern]) => pattern.test(label))?.[1] || 'function';
}
export function functionIconFor(label, override) {
  return override == null || override === '' ? inferFunctionIcon(label) : resolveFunctionIcon(override);
}
