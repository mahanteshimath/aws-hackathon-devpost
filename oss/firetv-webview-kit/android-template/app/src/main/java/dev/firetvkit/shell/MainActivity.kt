package dev.firetvkit.shell

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.KeyEvent
import android.view.WindowManager
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.webkit.WebViewAssetLoader

/**
 * firetv-webview-kit shell: a minimal, production-minded host for a 10-foot web app on Fire TV.
 *
 *  - Every remote key is forwarded to the page as window.tvRemote.dispatch('<action>')
 *    (see src/tv-remote.js). The WebView alone never sees Back, Menu or most media keys.
 *  - Back leaves the app only if the page returns false (e.g. on its home screen).
 *  - Media autoplay is allowed - there is no touch on a TV to "unlock" audio.
 *  - LAN dev mode: point the installed app at your laptop's dev server without rebuilding:
 *      adb shell am start -n <your.package>/dev.firetvkit.shell.MainActivity --es url http://192.168.1.10:5173/
 *  - Offline fallback: web assets bundled in src/main/assets are served from
 *      https://appassets.androidplatform.net/assets/ (set START_URL to that in build.gradle).
 */
class MainActivity : Activity() {
    private lateinit var webView: WebView

    private val assetLoader by lazy {
        WebViewAssetLoader.Builder().addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this)).build()
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        webView = WebView(this)
        setContentView(webView)
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            allowFileAccess = false
        }
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG) // chrome://inspect over adb
        webView.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                assetLoader.shouldInterceptRequest(request.url)
        }
        saveUrlExtra(intent)
        webView.requestFocus()
        webView.loadUrl(startUrl())
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (saveUrlExtra(intent)) webView.loadUrl(startUrl())
    }

    private fun saveUrlExtra(intent: Intent?): Boolean {
        val url = intent?.getStringExtra("url")?.trim().orEmpty()
        val scheme = Uri.parse(url).scheme
        if (url.isEmpty() || (scheme != "http" && scheme != "https")) return false
        getSharedPreferences("shell", Context.MODE_PRIVATE).edit().putString("url", url).apply()
        return true
    }

    private fun startUrl(): String =
        getSharedPreferences("shell", Context.MODE_PRIVATE).getString("url", null) ?: BuildConfig.START_URL

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        val action = ACTIONS[event.keyCode] ?: return super.dispatchKeyEvent(event)
        // Forward key-downs; ignore auto-repeat for Back so a long press doesn't exit twice.
        if (event.action == KeyEvent.ACTION_DOWN && !(action == "back" && event.repeatCount > 0)) {
            webView.evaluateJavascript("(window.tvRemote && window.tvRemote.dispatch('$action')) === true") { handled ->
                if (action == "back" && handled != "true") finish()
            }
        }
        return true
    }

    override fun onPause() { super.onPause(); webView.onPause() }
    override fun onResume() { super.onResume(); webView.onResume() }
    override fun onDestroy() { webView.destroy(); super.onDestroy() }

    companion object {
        val ACTIONS = mapOf(
            KeyEvent.KEYCODE_DPAD_UP to "up", KeyEvent.KEYCODE_DPAD_DOWN to "down",
            KeyEvent.KEYCODE_DPAD_LEFT to "left", KeyEvent.KEYCODE_DPAD_RIGHT to "right",
            KeyEvent.KEYCODE_DPAD_CENTER to "select", KeyEvent.KEYCODE_ENTER to "select",
            KeyEvent.KEYCODE_BACK to "back", KeyEvent.KEYCODE_MENU to "menu",
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE to "playpause", KeyEvent.KEYCODE_MEDIA_PLAY to "playpause",
            KeyEvent.KEYCODE_MEDIA_PAUSE to "playpause", KeyEvent.KEYCODE_MEDIA_FAST_FORWARD to "next",
            KeyEvent.KEYCODE_MEDIA_NEXT to "next", KeyEvent.KEYCODE_MEDIA_REWIND to "prev",
            KeyEvent.KEYCODE_MEDIA_PREVIOUS to "prev",
        )
    }
}
