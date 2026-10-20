/**
 * Remote control normalisation for Fire TV.
 *
 * Inputs:
 *  - Keyboard events (D-pad arrives as Arrow keys + Enter inside the Fire TV WebView; desktop testing too)
 *  - The native Kotlin shell, which forwards keys the WebView never sees (Back, Menu, media keys) by calling
 *    window.tvRemote.dispatch('<action>')
 *
 * Output: a single stream of actions:
 *   up | down | left | right | select | back | playpause | next | prev | menu
 */

const KEYMAP = {
  ArrowUp: 'up',
  ArrowDown: 'down',
  ArrowLeft: 'left',
  ArrowRight: 'right',
  Enter: 'select',
  ' ': 'playpause',
  Escape: 'back',
  Backspace: 'back',
  GoBack: 'back',
  BrowserBack: 'back',
  MediaPlayPause: 'playpause',
  MediaPlay: 'playpause',
  MediaPause: 'playpause',
  MediaFastForward: 'next',
  MediaTrackNext: 'next',
  MediaRewind: 'prev',
  MediaTrackPrevious: 'prev',
  ContextMenu: 'menu',
};

const KEYCODES = { 4: 'back', 82: 'menu', 85: 'playpause', 89: 'prev', 90: 'next', 179: 'playpause', 227: 'prev', 228: 'next' };

export function createRemote() {
  const listeners = new Set();
  /** Listeners return true when they handled the action. */
  const emit = (action, source) => {
    let handled = false;
    listeners.forEach((fn) => {
      if (fn(action, source) === true) handled = true;
    });
    return handled;
  };

  window.addEventListener('keydown', (e) => {
    const action = KEYMAP[e.key] || KEYCODES[e.keyCode];
    if (!action) return;
    e.preventDefault();
    emit(action, 'key');
  });

  // Bridge for the native shell (see firetv-app MainActivity.kt). Returning false for 'back'
  // tells the shell to perform the default system action (leave the app).
  window.tvRemote = {
    dispatch(action) {
      return emit(String(action), 'native');
    },
  };

  return {
    on(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    emit,
  };
}

/** True when running inside the Crayon Cinema Fire TV shell. */
export function isFireTvShell() {
  return typeof window.CrayonNative !== 'undefined' || /AFT[A-Z0-9]/.test(navigator.userAgent);
}
