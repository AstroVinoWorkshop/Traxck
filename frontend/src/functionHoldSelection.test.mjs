import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const css = readFileSync(new URL('./style.css', import.meta.url), 'utf8');

test('throttle function buttons disable text selection and iOS touch callout on long press', () => {
  const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)];
  const declarations = rules.filter(([, selector]) => selector.split(',').some(s => s.trim() === '.functions .function')).map(([, , body]) => body).join(';');
  assert.match(declarations, /(?:^|;)\s*user-select\s*:\s*none\s*(?:;|$)/);
  assert.match(declarations, /(?:^|;)\s*-webkit-user-select\s*:\s*none\s*(?:;|$)/);
  assert.match(declarations, /(?:^|;)\s*-webkit-touch-callout\s*:\s*none\s*(?:;|$)/);
});
