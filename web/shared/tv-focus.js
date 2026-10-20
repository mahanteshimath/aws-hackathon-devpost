/**
 * tv-focus: tiny spatial navigation for 10-foot web UIs (Fire TV, Android TV, set-top boxes).
 *
 * Mark focusable elements with `data-focus`. Arrow keys move focus to the nearest element in that
 * direction (geometry-based, with a preference for elements aligned on the cross axis). Enter clicks.
 *
 *   import { FocusManager } from './tv-focus.js';
 *   const fm = new FocusManager({ root: document.querySelector('#screen') });
 *   fm.focusFirst();
 *   fm.move('right');
 *
 * Optional attributes:
 *   data-focus-default        element focused first when a scope activates
 *   data-focus-group="row"    `move` prefers elements in the same group before leaving it
 *
 * Zero dependencies. MIT licensed.
 */

const DIRS = {
  up: { axis: 'y', sign: -1 },
  down: { axis: 'y', sign: 1 },
  left: { axis: 'x', sign: -1 },
  right: { axis: 'x', sign: 1 },
};

/** @typedef {{x:number,y:number,w:number,h:number,cx:number,cy:number}} Box */

/** @param {{left:number,top:number,width:number,height:number}} r @returns {Box} */
export function toBox(r) {
  return { x: r.left, y: r.top, w: r.width, h: r.height, cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
}

/**
 * Pick the best candidate box in a direction from `from`. Pure function - easy to unit test.
 * @param {Box} from
 * @param {Box[]} candidates
 * @param {'up'|'down'|'left'|'right'} dir
 * @returns {number} index of the chosen candidate, or -1
 */
export function pickNext(from, candidates, dir) {
  const d = DIRS[dir];
  if (!d) return -1;
  let best = -1;
  let bestScore = Infinity;
  candidates.forEach((c, i) => {
    const main = d.axis === 'x' ? (c.cx - from.cx) * d.sign : (c.cy - from.cy) * d.sign;
    if (main <= 1) return; // not in that direction
    // Edge gap along the main axis (0 when overlapping), and misalignment on the cross axis.
    const gap = d.axis === 'x'
      ? Math.max(0, d.sign > 0 ? c.x - (from.x + from.w) : from.x - (c.x + c.w))
      : Math.max(0, d.sign > 0 ? c.y - (from.y + from.h) : from.y - (c.y + c.h));
    const overlap = d.axis === 'x'
      ? Math.min(from.y + from.h, c.y + c.h) - Math.max(from.y, c.y)
      : Math.min(from.x + from.w, c.x + c.w) - Math.max(from.x, c.x);
    const cross = d.axis === 'x' ? Math.abs(c.cy - from.cy) : Math.abs(c.cx - from.cx);
    const aligned = overlap > 0 ? 0 : 1;
    const score = gap + main * 0.1 + cross * (aligned ? 2.5 : 0.4) + aligned * 400;
    if (score < bestScore) {
      bestScore = score;
      best = i;
    }
  });
  return best;
}

export class FocusManager {
  /** @param {{root?: Element, focusedClass?: string, onChange?: (el: Element|null) => void}} [opts] */
  constructor(opts = {}) {
    this.root = opts.root || document.body;
    this.focusedClass = opts.focusedClass || 'is-focused';
    this.onChange = opts.onChange || null;
    /** @type {Element|null} */
    this.current = null;
  }

  /** Change the active scope (e.g. a modal or a new screen) and focus its default element. */
  setRoot(root, { focus = true } = {}) {
    this.root = root;
    if (focus) this.focusFirst();
  }

  candidates() {
    return Array.from(this.root.querySelectorAll('[data-focus]')).filter((el) => {
      if (el.hasAttribute('disabled') || el.getAttribute('aria-hidden') === 'true') return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    });
  }

  focusFirst() {
    const els = this.candidates();
    const el = els.find((e) => e.hasAttribute('data-focus-default')) || els[0] || null;
    this.focus(el);
    return el;
  }

  /** @param {Element|null} el */
  focus(el) {
    if (this.current === el) return;
    if (this.current) this.current.classList.remove(this.focusedClass);
    this.current = el;
    if (el) {
      el.classList.add(this.focusedClass);
      if (typeof el.focus === 'function') el.focus({ preventScroll: true });
      if (typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    }
    if (this.onChange) this.onChange(el);
  }

  /** @param {'up'|'down'|'left'|'right'} dir @returns {boolean} whether focus moved */
  move(dir) {
    const els = this.candidates();
    if (!els.length) return false;
    if (!this.current || !els.includes(this.current)) {
      this.focusFirst();
      return true;
    }
    const group = this.current.getAttribute('data-focus-group');
    const others = els.filter((e) => e !== this.current);
    const from = toBox(this.current.getBoundingClientRect());
    const pools = group ? [others.filter((e) => e.getAttribute('data-focus-group') === group), others] : [others];
    for (const pool of pools) {
      const idx = pickNext(from, pool.map((e) => toBox(e.getBoundingClientRect())), dir);
      if (idx >= 0) {
        this.focus(pool[idx]);
        return true;
      }
    }
    return false;
  }

  select() {
    if (this.current && typeof this.current.click === 'function') {
      this.current.click();
      return true;
    }
    return false;
  }
}
