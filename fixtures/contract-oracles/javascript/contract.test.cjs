const {test}=require('node:test');
const assert=require('node:assert/strict');
const {total}=require('/work/contract.cjs');
test('test_regression',()=>assert.equal(total([]),0));
test('test_happy',()=>assert.equal(total([2,3]),5));
