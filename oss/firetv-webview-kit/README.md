# firetv-webview-kit

**Ship a web app to Fire TV in an afternoon.** You get three small pieces: D-pad spatial navigation for 10-foot web UIs, a bridge that delivers Fire TV remote keys to your page, and a Kotlin WebView shell template you can sideload today.

Extracted from [Crayon Cinema](https://github.com/mahanteshimath/aws-hackathon-devpost), built during the Amazon Developer Hackathon 2026. MIT licensed.

## Why

A web UI that works in a desktop browser falls apart on a TV:

- **No pointer.** Every action needs a D-pad path, and `Tab` order is not spatial.
- **Missing keys.** Inside an Android `WebView`, Back, Menu and most media keys (Play/Pause, Fast-forward, Rewind) never reach JavaScript.
- **Back exits by default.** Back should mean "go back a screen", not quit the app.
- **No autoplay.** Media is blocked until the user taps the screen, and a TV has no touch.

This kit solves each of these in under 300 lines, with no dependencies.

## What's inside

| Path | What it does |
|---|---|
| `src/tv-focus.js` | Geometry-based spatial navigation: `data-focus`, `data-focus-default`, `data-focus-group`. `pickNext()` is a pure, unit-tested function. |
| `src/tv-remote.js` | Normalises keyboard events and native-shell key events into `up/down/left/right/select/back/playpause/next/prev/menu`. Handlers return `true` when they handled a key. |
| `android-template/` | Kotlin `MainActivity`. It forwards every remote key to the page, lets Back exit only when the page doesn't handle it, allows media autoplay, and has a LAN dev-server mode (`--es url`) plus a bundled-assets offline fallback. |
| `examples/index.html` | A grid of focusable cards you can drive with the remote. |
| `test/` | `node --test` suite for the navigation algorithm and the `FocusManager`. |

## Quick start (web)

```html
<button data-focus data-focus-default>Play</button>
<button data-focus>Settings</button>

<script type="module">
  import { FocusManager } from './src/tv-focus.js';
  import { createRemote } from './src/tv-remote.js';

  const fm = new FocusManager();       // style .is-focused in your CSS
  fm.focusFirst();
  createRemote().on((action) => {
    if (['up', 'down', 'left', 'right'].includes(action)) return fm.move(action);
    if (action === 'select') return fm.select();
    if (action === 'back') return false;  // false = let the Fire TV shell exit the app
    return true;
  });
</script>
```

## Quick start (Fire TV)

1. On the Fire TV, go to **Settings → My Fire TV → About** and select the device name 7 times. Then go to **Developer options** and turn on **ADB debugging**.
2. Build and install the shell:
   ```bash
   cd android-template
   ./gradlew installDebug                       # bundled example
   adb connect <fire-tv-ip>:5555
   ```
3. Point it at your dev server without rebuilding, so every save reloads on the TV:
   ```bash
   adb shell am start -n dev.firetvkit.shell/.MainActivity --es url http://<laptop-ip>:5173/
   ```
4. To debug the page on the TV, open `chrome://inspect` on your laptop. Debug builds enable WebView debugging.

## How the navigation works

`pickNext(from, candidates, direction)` scores each candidate on four things:
- the gap between the edges along the direction of travel
- a small penalty for centre distance
- how far it is out of line on the other axis
- a large penalty when it doesn't overlap the current row or column

The effect is that rows and columns feel "sticky", the same way a TV launcher behaves. `data-focus-group` lets you keep focus inside a row (such as a shelf) before it is allowed to leave.

## Tests

```bash
node --test test/tv-focus.test.js
```

## License

MIT. See [LICENSE](LICENSE).
