import test from 'node:test';
import assert from 'node:assert/strict';
import {cvDescription,cvReference} from './cvReference.mjs';
test('NMRA multi-function range covers every CV exactly once with no unclassified number',()=>{
 assert.equal(cvReference.length,1024);
 assert.deepEqual(cvReference.map(row=>row.number),Array.from({length:1024},(_,i)=>i+1));
 assert.ok(cvReference.every(row=>typeof row.description==='string'&&row.description.length));
 assert.equal(cvDescription(0),null);assert.equal(cvDescription(1025),null);
});
test('reference distinguishes named, reserved, indexed and manufacturer-specific slots',()=>{
 assert.match(cvDescription(29),/Configuration/);
 assert.match(cvDescription(20),/Reserved by NMRA/);
 assert.match(cvDescription(47),/Manufacturer use/);
 assert.match(cvDescription(257),/CV31\/32/);
 assert.match(cvDescription(1024),/SUSI/);
});
