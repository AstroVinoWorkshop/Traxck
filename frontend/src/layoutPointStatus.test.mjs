import test from 'node:test';
import assert from 'node:assert/strict';
import {layoutPointStatus} from './layoutPointStatus.mjs';

const points=[{id:'P1',label:'Station throat',commanded:'straight',hardware_commanded:'diverging'}, {id:'P7',label:'Other',commanded:'diverging',hardware_commanded:null}];

test('mapped motor reflects the same mode-specific last command as upper status',()=>{
 assert.deepEqual(layoutPointStatus({kind:'point-motor',text:'P1'},points,'HARDWARE'),{id:'P1',position:'diverging'});
 assert.deepEqual(layoutPointStatus({kind:'point-motor',text:'P1'},points,'SIMULATION'),{id:'P1',position:'straight'});
});
test('unmapped, invalid and uncommanded motors never imply a known position',()=>{
 for(const text of [undefined,'','P9','P01','Station throat'])assert.deepEqual(layoutPointStatus({kind:'point-motor',text},points,'HARDWARE'),{id:null,position:null});
 assert.deepEqual(layoutPointStatus({kind:'point-motor',text:'P7'},points,'HARDWARE'),{id:'P7',position:null});
 assert.deepEqual(layoutPointStatus({kind:'pillar',text:'P1'},points,'HARDWARE'),{id:null,position:null});
});
