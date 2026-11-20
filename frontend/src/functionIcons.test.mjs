import test from 'node:test';
import assert from 'node:assert/strict';
import {functionIcons, functionIconIds, resolveFunctionIcon, inferFunctionIcon, functionIconFor} from './functionIcons.mjs';

test('label-derived icons cover Steam locomotive A while preserving explicit overrides', () => {
  const cases = [
    ['Day Light','headlight'], ['Sound ON/OFF','speaker'], ['Multiple Whistles: 1','whistle'],
    ['Brake Squeal','brake'], ['Cylinder Cock','steam-release'], ['Wheel Slip (Sound: ON)','brake'],
    ['Coal Shovelling','steam'], ['Injector Valve','steam-release'], ['Safety Valve','steam-release'],
    ['Guards Whistle','whistle'], ['Coupling','coupler'], ['Carriage Brake Squeal','brake'],
    ['Flange Squeal','brake'], ['Blower','steam-release'], ['Door Closed','doors'],
    ["Fireman's Breakfast",'steam'], ['Blow Down','steam-release'], ['Coal Pusher','steam'],
    ['Water','steam'], ['Chuffing/Coasting','steam'], ['Aux Lighting','interior-light'],
    ['Shunting Mode','shunting'], ['Creep Mode','shunting'], ['Brake','brake'],
    ['Automated Function Control','gear'],
  ];
  for (const [label,icon] of cases) assert.equal(inferFunctionIcon(label), icon, label);
  assert.equal(functionIconFor('Day Light','bell'),'bell');
  assert.equal(functionIconFor('Day Light','invalid'),'function');
  assert.equal(inferFunctionIcon('Unrecognised'), 'function');
});

test('Diesel labels get specific presentation icons', () => {
  const cases = [
    ['Engine Start','engine'], ['Multiple Horns: 1','horn'], ['Multiple Horns: 2','horn'],
    ['Diesel Notch Up','diesel'], ['Diesel Notch Down','diesel'], ['Idle','engine'],
    ['Diesel Engine Thrash','diesel'], ['Diesel Cold Start','diesel'],
    ['Compressor','compressor'], ['Windscreen Wipers','wipers'], ['Spirax Valve','steam-release'],
    ['Brake Application','brake'], ['Brake Release','brake'], ['Buffering Up','coupler'],
    ['Diesel Primer','diesel'], ['Guards Whistle','whistle'],
  ];
  for (const [label, icon] of cases) assert.equal(inferFunctionIcon(label), icon, label);
});

test('the function icon picker covers sounds, lighting and railway actions', () => {
  assert.ok(functionIconIds.length >= 30);
  for (const id of ['whistle','horn','bell','engine','headlight','cab-light','shunting','coupler','smoke','doors']) {
    assert.ok(functionIconIds.includes(id), id);
  }
  assert.equal(new Set(functionIconIds).size, functionIconIds.length);
});

test('legacy and unrecognised icons render a safe fallback', () => {
  assert.equal(resolveFunctionIcon(undefined), 'function');
  assert.equal(resolveFunctionIcon('<script>'), 'function');
  assert.equal(resolveFunctionIcon('whistle'), 'whistle');
});
