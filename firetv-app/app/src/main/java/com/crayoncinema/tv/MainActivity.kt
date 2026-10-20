package com.crayoncinema.tv

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.webkit.WebViewAssetLoader

/**
 * Fire TV shell for Crayon Cinema.
 *
 * - Hosts the 10-foot web UI in a hardware-accelerated WebView.
 * - Forwards every remote key (D-pad, select, back, menu, media keys) to the page through
 *   window.tvRemote.dispatch(action), so remote handling is identical on every Fire OS version.
 * - Back exits the app only when the page says it did not handle it (i.e. on the home screen).
 * - Falls back to the copy of the web app bundled in the APK (offline sample story) if the
 *   story server cannot be reached.
 *
 * Point it at a server without rebuilding:
 *   adb shell am start -n com.crayoncinema.tv/.MainActivity --es url http://192.168.1.10:8787/tv/
 */
class MainActivity : Activity() {

    private lateinit var webView: WebView
    private var usingBundled = false

    private val assetLoader by lazy {
        WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        webView = WebView(this).apply {
            setBackgroundColor(Color.parseColor("#1B1430"))
            isFocusable = true
            isFocusableInTouchMode = true
            setLayerType(View.LAYER_TYPE_HARDWARE, null)
        }
        setContentView(webView)

        with(webView.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false // narration starts without a tap - there is no touch on TV
            cacheMode = WebSettings.LOAD_DEFAULT
            allowFileAccess = false
            mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
            userAgentString = "$userAgentString CrayonCinemaFireTV/${BuildConfig.VERSION_NAME}"
        }
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        webView.addJavascriptInterface(NativeBridge(), "CrayonNative")
        webView.webChromeClient = WebChromeClient()
        webView.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                assetLoader.shouldInterceptRequest(request.url)

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame && !usingBundled) {
                    Log.w(TAG, "Story server unreachable (${error.description}); loading bundled app")
                    loadBundled()
                }
            }
        }

        handleUrlExtra(intent)
        webView.requestFocus()
        if (savedInstanceState != null) webView.restoreState(savedInstanceState) else webView.loadUrl(startUrl())
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (handleUrlExtra(intent)) {
            usingBundled = false
            webView.loadUrl(startUrl())
        }
    }

    /** Persist a server URL passed with `--es url ...` (handy when the dev machine's IP changes). */
    private fun handleUrlExtra(intent: Intent?): Boolean {
        val url = intent?.getStringExtra("url")?.trim().orEmpty()
        if (url.isEmpty()) return false
        val scheme = Uri.parse(url).scheme
        if (scheme != "http" && scheme != "https") return false
        prefs().edit().putString(KEY_URL, url).apply()
        return true
    }

    private fun prefs() = getSharedPreferences("crayon", Context.MODE_PRIVATE)

    private fun startUrl(): String = prefs().getString(KEY_URL, null) ?: BuildConfig.START_URL

    private fun loadBundled() {
        usingBundled = true
        webView.loadUrl("https://appassets.androidplatform.net/assets/tv/index.html")
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        webView.saveState(outState)
    }

    override fun onPause() {
        super.onPause()
        webView.onPause()
    }

    override fun onResume() {
        super.onResume()
        webView.onResume()
    }

    override fun onDestroy() {
        webView.destroy()
        super.onDestroy()
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        val action = ACTIONS[event.keyCode] ?: return super.dispatchKeyEvent(event)
        if (event.action == KeyEvent.ACTION_DOWN) {
            if (action == "back") {
                if (event.repeatCount == 0) sendBack()
            } else {
                dispatchToPage(action)
            }
        }
        return true // the page owns all remote keys
    }

    private fun dispatchToPage(action: String, callback: ((Boolean) -> Unit)? = null) {
        val js = "(window.tvRemote && window.tvRemote.dispatch('$action')) === true"
        webView.evaluateJavascript(js) { result -> callback?.invoke(result == "true") }
    }

    private fun sendBack() {
        dispatchToPage("back") { handled -> if (!handled) finish() }
    }

    inner class NativeBridge {
        @JavascriptInterface
        fun version(): String = BuildConfig.VERSION_NAME

        @JavascriptInterface
        fun platform(): String = "firetv"
    }

    companion object {
        private const val TAG = "CrayonCinema"
        private const val KEY_URL = "server_url"

        private val ACTIONS = mapOf(
            KeyEvent.KEYCODE_DPAD_UP to "up",
            KeyEvent.KEYCODE_DPAD_DOWN to "down",
            KeyEvent.KEYCODE_DPAD_LEFT to "left",
            KeyEvent.KEYCODE_DPAD_RIGHT to "right",
            KeyEvent.KEYCODE_DPAD_CENTER to "select",
            KeyEvent.KEYCODE_ENTER to "select",
            KeyEvent.KEYCODE_NUMPAD_ENTER to "select",
            KeyEvent.KEYCODE_BACK to "back",
            KeyEvent.KEYCODE_ESCAPE to "back",
            KeyEvent.KEYCODE_MENU to "menu",
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE to "playpause",
            KeyEvent.KEYCODE_MEDIA_PLAY to "playpause",
            KeyEvent.KEYCODE_MEDIA_PAUSE to "playpause",
            KeyEvent.KEYCODE_MEDIA_FAST_FORWARD to "next",
            KeyEvent.KEYCODE_MEDIA_NEXT to "next",
            KeyEvent.KEYCODE_MEDIA_REWIND to "prev",
            KeyEvent.KEYCODE_MEDIA_PREVIOUS to "prev",
        )
    }
}
