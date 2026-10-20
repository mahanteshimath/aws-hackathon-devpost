# Product feedback

This is feedback on the Amazon and AWS products used to build Crayon Cinema, written for the product teams. Each point says what worked, what didn't, and what would have helped.

> **Draft status:** AWS sections were verified against a live account on 2026-10-20 (Lambda + AgentCore deployment, real stories). Sections marked _(pending device run)_ still need the Fire TV. Do not submit them unverified.

## Fire TV (Fire OS, WebView, sideloading) _(pending device run)_

**What the shell relies on** (to be confirmed on the test device)
- Sideloading with ADB over Wi-Fi plus `am start --es url …` lets the installed app point at a laptop dev server, so changes show up on the TV without rebuilding.
- The design avoids animating anything except CSS transforms and opacity, so 1080p animation should stay smooth in the Chromium WebView. Frame rate on the real device is to be measured.
- `LEANBACK_LAUNCHER` plus a 320×180 banner makes a sideloaded app look first-class in Your Apps & Channels.

**What would help**
- **An official "web app on Fire TV" guide.** It would need to cover forwarding remote keys to JavaScript, Back-button semantics, `mediaPlaybackRequiresUserGesture`, WebView debugging over `chrome://inspect`, and expected WebView versions per Fire OS release. I had to put this together from Android docs and trial and error, and I published it as [`firetv-webview-kit`](../oss/firetv-webview-kit).
- **A published table of WebView or Chromium versions per Fire TV model.** Choosing which JS and CSS features are safe (ES modules, optional chaining, `inset`) is guesswork without it.
- **A built-in way to record the screen for demo videos.** Hackathon rules require real-device footage, and recording an HDMI device usually needs a capture card.

## Amazon Bedrock: image models

- **Nova Canvas reached end of life mid-project** (friction log #6). Its `COLOR_GUIDED_GENERATION`, which takes a palette of hex colours, was the feature that made each world match the child's crayons. Nothing on Bedrock replaces it today. A palette parameter on a first-party successor would be the single most useful addition for personal and kids' apps.
- **Stability AI on Bedrock works well when it works.** Stable Image Remove Background kept every thin crayon stroke of a line drawing on paper (9.8 s), and SD3.5 Large produced a lovely watercolour-and-crayon storybook scene at 16:9 (7.7 s). SD3.5 is only served from us-west-2, so the app needs a second regional client.
- **Marketplace billing state is invisible until it breaks** (friction log #7). Models listed as ACTIVE and AUTHORIZED worked, then failed with `INVALID_PAYMENT_INSTRUMENT`. Please show the agreement state in the model catalog and use one consistent error.

## Amazon Bedrock: Amazon Nova 2 Lite through Strands Agents

- Structured output (`structured_output_model=PydanticModel`) is the right abstraction. Getting a validated `StoryPlan` (3 pages plus 2 branches of 3 pages, each with mood, motion and scene) removed a whole layer of JSON-repair code. Adding `min_length`/`max_length` to the pydantic fields made the model retry instead of shipping a short branch.
- Image content blocks went straight into a Strands agent with no glue code. **Nova 2 Lite** cast the drawing in 2.4 s (it correctly saw "a purple space dino with a spiky back") and wrote a full branching story, including a tool call to recall the household, in about 5–7 s.
- **Nova Pro was not reliable** for structured output combined with a tool (friction log #8). A compatibility table for Strands would save others the benchmarking.
- The model is a one-line env change (`STORY_MODEL_ID`), so Claude can be used once Marketplace billing is in place.
- Request: a documented pattern for **fan-out after structured output**, meaning streaming partial structured results so rendering can start before the whole plan is done. Today I wait for the full plan.

## Amazon Bedrock AgentCore (Runtime and Memory)

- Direct code deploy (no Docker) in the starter toolkit is a great fit for a laptop with no container runtime. It cross-compiled Linux ARM64 dependencies with uv and shipped a 68 MB package without any container tooling. The first story after the deploy was ready 18 s after the phone upload.
- Observability setup failed on the first deploy in a fresh account (friction log #9); logs worked, traces did not.
- Async tasks (`add_async_task` / `complete_async_task`) fit this "fire and poll" workload well. The API Lambda returns immediately and the microVM keeps rendering. A first-class example of this pattern in the docs would help, because most samples are request/response chat.
- Memory's semantic strategy with `{actorId}` namespaces maps naturally to "one household = one actor". About a minute after two stories, recall returned an extracted fact ("The user's child Maya drew a purple egg-like creature with a springy tail named Zap") next to the app's own shelf. I'd like to see a sample that combines structured application state with extracted long-term facts, since that's what most real apps need.
- The auto-created execution role is fine for Bedrock, but apps also need S3. Remember `s3:ListBucket`: without it, a missing key comes back as `AccessDenied` instead of `NoSuchKey`, which crashed my render workers the first time.

## Amazon Polly

- Neural voices are fast: about 1.4 s for a page of narration plus its word speech marks. Child voices (Ivy, Kevin) give each hero its own voice for the greeting.
- Word speech marks enable real read-along, but the byte offsets into SSML (tags included) are a trap. An option for character offsets relative to the text content would make this much easier (see the friction log).

## Amazon Bedrock Guardrails

- `ApplyGuardrail` as a standalone call is perfect for a multi-model pipeline: one policy checks the casting text, the story plan and the labels the child sees, whichever model produced them.
- Request: kid-safety presets (for example "ages 3–8") with sensible denied topics. Every family or education app has to write the same "no scary content" topic definitions by hand.

## AWS Lambda

- Function URLs are the shortest path from code to a public HTTPS endpoint, and they work well for serving both the API and the static TV and phone apps.
- The October 2025 change requiring a second `lambda:InvokeFunction` statement with `InvokedViaFunctionUrl` breaks most existing IaC samples and fails with a bare 403 (see the friction log).
