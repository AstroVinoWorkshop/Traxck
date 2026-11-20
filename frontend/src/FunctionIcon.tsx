import {Activity, AlertTriangle, ArrowDownToLine, Bell, Check, Clock3, Cog, DoorOpen, Fan, Gauge, LampCeiling, Lightbulb, LightbulbOff, Megaphone, Mic, Music2, Play, Power, Radio, RotateCcw, Siren, Sparkles, Sun, TrainFront, Unplug, Volume1, Volume2, VolumeX, Waves, Wind, Wrench, X, Zap} from 'lucide-react';
import {resolveFunctionIcon} from './functionIcons.mjs';

const icons = {
  function: Cog, power: Power, play: Play, stop: X, check: Check,
  whistle: Wind, horn: Megaphone, bell: Bell, speaker: Volume2, mute: VolumeX,
  'volume-up': Volume2, 'volume-down': Volume1, announcement: Mic, radio: Radio,
  music: Music2, brake: Gauge, compressor: Waves, engine: Activity, diesel: Cog, steam: Wind,
  headlight: Sun, 'rear-light': Lightbulb, 'cab-light': LampCeiling, 'interior-light': Lightbulb,
  'marker-light': Lightbulb, 'flashing-light': Zap, beacon: Siren, 'dim-light': LightbulbOff,
  shunting: RotateCcw, coupler: Unplug, doors: DoorOpen, fan: Fan, smoke: Waves,
  'steam-release': Wind, pantograph: ArrowDownToLine, wipers: Wrench,
  gear: Cog, train: TrainFront, clock: Clock3, warning: AlertTriangle, spark: Sparkles,
};
export function FunctionIcon({id, size=20}: {id?: string; size?: number}) {
  const Icon = icons[resolveFunctionIcon(id) as keyof typeof icons];
  return <Icon size={size} aria-hidden="true" strokeWidth={1.9}/>;
}
