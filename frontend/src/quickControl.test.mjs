import test from 'node:test';
import assert from 'node:assert/strict';
import {nextPointPosition, pointCommandUnavailable, locomotiveControlUnavailable, rosterControlAddress} from './quickControl.mjs';

test('point chip toggles last command in the active mode and defaults to straight',()=>{
  const point={address:1,commanded:'diverging',hardware_commanded:'straight'};
  assert.equal(nextPointPosition(point,'HARDWARE'),'diverging');
  assert.equal(nextPointPosition(point,'SIMULATION'),'straight');
  assert.equal(nextPointPosition({address:1,hardware_commanded:null},'HARDWARE'),'straight');
});
test('point chips cannot command an unconfigured or unsafe hardware point',()=>{
  const safe={mode:'HARDWARE',connected:true,power:true,estop:false};
  assert.equal(pointCommandUnavailable({address:null},safe),true);
  assert.equal(pointCommandUnavailable({address:1},{...safe,connected:false}),true);
  assert.equal(pointCommandUnavailable({address:1},{...safe,power:false}),true);
  assert.equal(pointCommandUnavailable({address:1},{...safe,estop:true}),true);
  assert.equal(pointCommandUnavailable({address:1},safe),false);
  assert.equal(pointCommandUnavailable({address:null},{...safe,mode:'SIMULATION'}),false);
});
test('roster requires a mapped, valid locomotive address; no default train',()=>{
  assert.equal(rosterControlAddress({address:600},[{address:600}]),600);
  assert.equal(rosterControlAddress({address:600},[]),null);
  assert.equal(rosterControlAddress({address:null},[{address:600}]),null);
});
test('quick throttle and functions obey power, emergency stop and connection gate',()=>{
  const safe={mode:'HARDWARE',connected:true,power:true,estop:false};
  assert.equal(locomotiveControlUnavailable(600,safe),false);
  assert.equal(locomotiveControlUnavailable(null,safe),true);
  assert.equal(locomotiveControlUnavailable(600,{...safe,power:false}),true);
  assert.equal(locomotiveControlUnavailable(600,{...safe,estop:true}),true);
  assert.equal(locomotiveControlUnavailable(600,{...safe,connected:false}),true);
});
