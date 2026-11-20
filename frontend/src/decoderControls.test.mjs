import test from 'node:test';
import assert from 'node:assert/strict';
import {functionNumbers, selectableRoster, validCvInput} from './decoderControls.mjs';

test('F0–F28 expose only sourced manual or verified mappings', () => {
  const slots = functionNumbers([
    {key: 0, label: 'Headlight', momentary: false, source: 'Decoder manual p. 3', confidence: 'manual'},
    {key: 1, label: 'Unconfirmed', momentary: false},
    {key: 28, label: 'Bell', momentary: true, source: 'Operator observation', confidence: 'verified'},
    {key: 68, label: 'Out of range', momentary: true, source: 'Manual', confidence: 'verified'},
  ]);
  assert.equal(slots.length, 29);
  assert.deepEqual(slots[0], {icon: 'headlight', key: 0, label: 'Headlight', momentary: false, mapped: true, source: 'Decoder manual p. 3', confidence: 'manual'});
  assert.equal(slots[1].mapped, false);
  assert.equal(slots[1].icon, 'function');
  assert.equal(slots[28].label, 'Bell');
  assert.equal(slots[28].icon, 'bell');
  assert.equal(slots[28].momentary, true);
});

test('unmapped inventory remains visible but never selectable for driving', () => {
  const entries = selectableRoster([{id:'pending', name:'Pending', address:null}, {id:'ready', name:'Ready', address:3}], [{address:3}]);
  assert.equal(entries.length, 2);
  assert.equal(entries[0].disabled, true);
  assert.match(entries[0].label, /ID to confirm/);
  assert.equal(entries[1].disabled, false);
});

test('CV input rejects incomplete or out-of-range numbers', () => {
  assert.equal(validCvInput('1', '255'), true);
  assert.equal(validCvInput('1024', '0'), true);
  for (const [cv,value] of [['', '2'],['0','2'],['1025','2'],['1','256'],['1','-1'],['1','2.5']]) assert.equal(validCvInput(cv,value), false);
});
