import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pickNext, toBox, FocusManager } from '../src/tv-focus.js';

const box = (x, y, w = 100, h = 100) => toBox({ left: x, top: y, width: w, height: h });

// A 3x3 grid of 100px cards with 20px gaps:
//  0 1 2
//  3 4 5
//  6 7 8
const grid = [];
for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) grid.push(box(c * 120, r * 120));

test('moves to the adjacent cell in a grid', () => {
  const centre = grid[4];
  const others = grid.filter((_, i) => i !== 4);
  const ids = grid.map((_, i) => i).filter((i) => i !== 4);
  assert.equal(ids[pickNext(centre, others, 'right')], 5);
  assert.equal(ids[pickNext(centre, others, 'left')], 3);
  assert.equal(ids[pickNext(centre, others, 'up')], 1);
  assert.equal(ids[pickNext(centre, others, 'down')], 7);
});

test('returns -1 at the edge', () => {
  const others = grid.slice(1);
  assert.equal(pickNext(grid[0], others, 'left'), -1);
  assert.equal(pickNext(grid[0], others, 'up'), -1);
});

test('prefers an aligned element over a closer diagonal one', () => {
  const from = box(0, 0);
  const diagonal = box(130, 140); // nearer, but on the next row (no vertical overlap)
  const aligned = box(400, 0);   // further, same row
  assert.equal(pickNext(from, [diagonal, aligned], 'right'), 1);
});

test('jumps between rows of different sizes (hero row -> shelf row)', () => {
  const hero = box(0, 0, 1200, 400);
  const shelf = [box(0, 460, 300, 200), box(340, 460, 300, 200), box(680, 460, 300, 200)];
  // from a wide hero banner, down should land on the shelf card under its centre
  assert.equal(pickNext(hero, shelf, 'down'), 1);
});

test('ignores unknown directions', () => {
  assert.equal(pickNext(grid[0], grid.slice(1), 'sideways'), -1);
});

// --- FocusManager against a tiny fake DOM -------------------------------------------------

function fakeEl(id, rect, attrs = {}) {
  const classes = new Set();
  return {
    id,
    attrs: { 'data-focus': '', ...attrs },
    clicked: 0,
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c) },
    hasAttribute(name) { return name in this.attrs; },
    getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; },
    getBoundingClientRect: () => rect,
    focus() {},
    scrollIntoView() {},
    click() { this.clicked++; },
  };
}

function fakeRoot(els) {
  return { querySelectorAll: () => els };
}

test('FocusManager focuses the default element, moves, and selects', () => {
  const a = fakeEl('a', { left: 0, top: 0, width: 100, height: 100 });
  const b = fakeEl('b', { left: 200, top: 0, width: 100, height: 100 }, { 'data-focus-default': '' });
  const c = fakeEl('c', { left: 400, top: 0, width: 100, height: 100 });
  const changes = [];
  const fm = new FocusManager({ root: fakeRoot([a, b, c]), onChange: (el) => changes.push(el && el.id) });
  assert.equal(fm.focusFirst().id, 'b');
  assert.ok(b.classList.contains('is-focused'));
  assert.equal(fm.move('right'), true);
  assert.equal(fm.current.id, 'c');
  assert.ok(!b.classList.contains('is-focused'));
  assert.equal(fm.move('right'), false); // edge: stays put
  fm.select();
  assert.equal(c.clicked, 1);
  assert.deepEqual(changes, ['b', 'c']);
});

test('FocusManager skips disabled and hidden elements', () => {
  const a = fakeEl('a', { left: 0, top: 0, width: 100, height: 100 });
  const hidden = fakeEl('h', { left: 200, top: 0, width: 0, height: 0 });
  const disabled = fakeEl('d', { left: 300, top: 0, width: 100, height: 100 }, { disabled: '' });
  const c = fakeEl('c', { left: 500, top: 0, width: 100, height: 100 });
  const fm = new FocusManager({ root: fakeRoot([a, hidden, disabled, c]) });
  fm.focusFirst();
  fm.move('right');
  assert.equal(fm.current.id, 'c');
});

test('data-focus-group keeps focus inside a row before leaving it', () => {
  const r1 = fakeEl('r1', { left: 0, top: 0, width: 100, height: 100 }, { 'data-focus-group': 'row' });
  const r2 = fakeEl('r2', { left: 600, top: 40, width: 100, height: 100 }, { 'data-focus-group': 'row' });
  const near = fakeEl('near', { left: 150, top: 160, width: 100, height: 100 });
  const fm = new FocusManager({ root: fakeRoot([r1, r2, near]) });
  fm.focus(r1);
  fm.move('right');
  assert.equal(fm.current.id, 'r2');
});
