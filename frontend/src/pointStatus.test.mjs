import test from 'node:test';
import assert from 'node:assert/strict';
import {pointLastCommand} from './pointStatus.mjs';

test('hardware indicator is unknown until a command is sent, even for a seeded straight point', () => {
  assert.equal(pointLastCommand({commanded:'straight',hardware_commanded:null}, 'HARDWARE'), null);
});
test('hardware indicator uses sent command, simulation indicator uses simulated command', () => {
  const point={commanded:'diverging',hardware_commanded:'straight'};
  assert.equal(pointLastCommand(point,'HARDWARE'),'straight');
  assert.equal(pointLastCommand(point,'SIMULATION'),'diverging');
});
