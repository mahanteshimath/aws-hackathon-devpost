# Friction log

These are real problems found while building Crayon Cinema, each with a suggested fix. (The hackathon awards up to a 10% bonus for this log; nothing here is invented.)

Each entry is marked with its status:
- **Verified:** reproduced or confirmed against the official documentation while building.
- **To verify:** found while writing the integration code but **not yet reproduced** on the Fire TV or in the AWS account. These must be confirmed, or deleted, before submission.

---

## 1. Lambda function URL with `AuthType=NONE` now needs two permission statements, and most samples show one  · Verified (docs)

- **Where:** AWS Lambda, creating a public function URL from boto3 or CloudFormation (not the console).
- **What happened:** Most blog posts, samples and older answers show a single `lambda:InvokeFunctionUrl` permission. Since October 2025, *new* function URLs also need `lambda:InvokeFunction` with the `lambda:InvokedViaFunctionUrl` condition. Without it, the URL returns **403 Forbidden** and the error doesn't say what's missing. I only caught it because the note at the top of the "Control access to Lambda function URLs" page mentions it.
- **Impact:** Easy to lose an hour thinking it's an IAM role, CORS or Auth problem.
- **Suggestion:** Return a specific 403 body (for example `"missing lambda:InvokeFunction permission with InvokedViaFunctionUrl"`). Alternatively, have `CreateFunctionUrlConfig` with `AuthType=NONE` optionally add both statements, as the console already does.
- **Workaround used:** `infra/deploy.py` adds both statements idempotently.

## 2. Polly speech-mark offsets count SSML markup, which isn't obvious for read-along  · Verified (docs and unit test)

- **Where:** Amazon Polly `SynthesizeSpeech` with `TextType=ssml` and `SpeechMarkTypes=["word"]`.
- **What happened:** The `start` and `end` values in word marks are **byte** offsets into the *full SSML string*, including `<speak><prosody …>`. They are not character offsets into the spoken text. With a child-friendly slower `prosody rate`, every highlight was off by 31 positions. Curly quotes and accented names ("Zoë") added more drift, because UTF-8 bytes are not characters.
- **Evidence:** The "Speech marks with SSML" example in the docs shows the first word starting at offset 31, but the page doesn't call out that consequence.
- **Suggestion:** Add an optional `charOffsets=true`, or return offsets relative to the text content, plus a short note in the speech-marks docs.
- **Workaround used:** `backend/crayon/aws_services.py` subtracts the SSML prefix length and converts bytes to characters. A unit test with "Zoë" and curly quotes guards it.

## 3. The Fire TV WebView never sees Back, Menu or media keys, and the rule isn't documented in one place  · To verify on device

- **Where:** Fire TV, hosting a web app in `android.webkit.WebView`.
- **What happened:** D-pad and Select arrive in JavaScript as `keydown` (`ArrowUp`, `Enter`). **Back** goes to the Activity and exits the app by default. **Menu** and media keys (Play/Pause, Rewind, Fast-forward) don't reach the page reliably. Web developers expect a single `keydown` stream.
- **Impact:** Every web-based Fire TV app has to rebuild the same bridge. It's also easy to ship an app where Back on an inner screen quits the app, which is a common certification failure.
- **Suggestion:** Add a "Web apps on Fire TV" page to the Fire TV docs with a canonical key-forwarding snippet, or provide an official helper in the Web App Starter Kit.
- **Workaround used:** `MainActivity.dispatchKeyEvent` forwards every remote key to `window.tvRemote.dispatch()`. The page returns `true` if it handled the key, otherwise the shell exits. This is published as MIT in `oss/firetv-webview-kit`.

## 4. Media autoplay in the Fire TV WebView needs a native setting with no web-side signal  · To verify on device

- **Where:** Fire TV WebView with `HTMLAudioElement.play()`.
- **What happened:** Narration that starts on its own (after the drawing is cast) is blocked, because the default WebView requires a user gesture. There's no touch on a TV to provide one. `play()` rejects with `NotAllowedError`, and the page can't fix that from JavaScript.
- **Suggestion:** Mention `WebSettings.setMediaPlaybackRequiresUserGesture(false)` in the Fire TV web app guidance, and consider making it the default for TV-type devices.
- **Workaround used:** The shell sets it to false. The web app also falls back to silent timed highlighting if `play()` is still rejected.

## 5. AgentCore `runtimeSessionId` has a minimum length of 33 characters  · Verified (minor)

- **Where:** `bedrock-agentcore` `InvokeAgentRuntime`.
- **What happened:** I wanted to reuse the story's ID (24 hex characters) as the session ID, but it has to be at least 33 characters. Sample code usually generates a UUID (36 characters), so you never meet the rule until you use your own IDs. To be fair, boto3 rejects the call locally with a clear message: `Invalid length for parameter runtimeSessionId, value: 24, valid min length: 33`.
- **Suggestion:** Mention the minimum next to `runtimeSessionId` in the AgentCore Runtime developer guide, not only in the API reference, since apps naturally want to reuse their own job or conversation IDs.
- **Workaround used:** `crayon-story-{id}` padded to 40 characters (`backend/crayon/api.py`).

## 6. Amazon Nova Canvas has reached end of life, and nothing first-party replaces it  · Verified (account 2026-10-20)

- **Where:** Bedrock `InvokeModel` with `amazon.nova-canvas-v1:0` in us-east-1, eu-west-1 and ap-northeast-1. In us-west-2 the same ID is rejected as invalid.
- **What happened:** The whole image design (`BACKGROUND_REMOVAL` for the cut-out, `COLOR_GUIDED_GENERATION` with the child's crayon palette) was built on Nova Canvas. The first live call returned `ResourceNotFoundException: This model version has reached the end of its life`. The model is gone from `ListFoundationModels`. The only image-output models left in the account are Stability AI models sold through AWS Marketplace. Many tutorials and samples still use Nova Canvas.
- **Impact:** A late, forced redesign. Colour-guided generation, which had no equivalent elsewhere, is lost; the palette is now approximated with colour words in the prompt.
- **Suggestion:** Return a pointer to a successor model in the end-of-life error, and add a banner to the samples and docs pages that still show Nova Canvas.
- **Workaround used:** Stability AI on Bedrock. Stable Image Remove Background handles the cut-out and SD3.5 Large (us-west-2 only) handles the scenes; the palette is mapped to colour names (`imaging.colour_names`). Every image call keeps a local fallback.

## 7. Marketplace-backed models look "ACTIVE", work for a few minutes, then fail with `INVALID_PAYMENT_INSTRUMENT`  · Verified (account 2026-10-20)

- **Where:** Bedrock `InvokeModel` and `Converse` for Anthropic Claude and Stability AI models.
- **What happened:**
  - Both models are listed as `ACTIVE`, and `GetFoundationModelAvailability` reports `authorizationStatus: AUTHORIZED` and `entitlementAvailability: AVAILABLE`.
  - The first Stability calls **succeeded** (background removal in 9.8 s, an SD3.5 scene in 7.7 s). About 15 minutes later every call failed with `AccessDeniedException: Model access is denied due to INVALID_PAYMENT_INSTRUMENT … Your AWS Marketplace subscription for this model cannot be completed at this time`.
  - Claude models failed the same way from the start. One Claude call instead returned a different message, "IAM user or service role is not authorized to perform the required AWS Marketplace actions", for the same root cause.
  - The real state is only visible in `agreementAvailability: {status: ERROR}`.
- **Impact:** A pipeline that passed its first live test broke silently minutes later. The two different error messages sent me looking at IAM first.
- **Suggestion:** Fail consistently from the first call while the subscription is pending. Show the agreement state in `ListFoundationModels` and the console model catalog. Use one error message that names the fix (add a payment method).
- **Workaround used:** `scripts/list_models.py` now sends one tiny request to each configured model instead of trusting the listing. The default agents moved to first-party **Amazon Nova 2 Lite** (no Marketplace). Image calls fall back to the local paper-key cut-out and procedural crayon-paper scenes, so a story always plays.

## 8. Nova Pro produced an invalid tool-use sequence under Strands structured output  · Verified (one run)

- **Where:** Strands Agents 1.x `structured_output_model` with an extra tool (`recall_household_universe`), model `us.amazon.nova-pro-v1:0`.
- **What happened:**
  - First run: the director hit `MaxTokensReachedException` at 6,000 tokens, then the retry produced a weak plan (one branch had a single page labelled "Recap"). The step took **449 s**.
  - A direct benchmark failed after 48 s with `modelStreamErrorException: Model produced invalid sequence as part of ToolUse`.
  - With the same prompt, schema and tool, **Nova 2 Lite** returned a valid plan in **6.5 s** and used the memory tool correctly.
- **Suggestion:** A compatibility note in the Strands docs on which Bedrock models are reliable for structured output combined with other tools.
- **Workaround used:** Nova 2 Lite for both agents. `StoryPlan` now enforces exactly 3 pages per section (`min_length`/`max_length`), so malformed plans are rejected and retried instead of shipped.

## 9. AgentCore observability setup fails on a fresh account while X-Ray is still "PENDING"  · Verified (account 2026-10-20)

- **Where:** `bedrock-agentcore-starter-toolkit` `launch()` with direct code deploy, on the first deploy in an account.
- **What happened:** The runtime deployed, but enabling observability printed `ValidationException: X-Ray Delivery Destination is supported with CloudWatch Logs as a Trace Segment Destination…`. The toolkit had just configured that destination itself, and it reported the status as `PENDING (typically 10-15 minutes)`. Logs worked; traces were not set up.
- **Suggestion:** Wait for the destination to become active, or retry, inside the toolkit. At minimum, print "re-run launch in 15 minutes to enable traces" instead of a raw API error.
- **Workaround used:** Re-run `infra/deploy_agentcore.py` later (it is idempotent). Confirmed: about 40 minutes later the destination was `ACTIVE` and the re-run enabled traces with no other change.

---

### Other checks during deployment and filming

- Whether `adb shell screenrecord` works on the test Fire TV (some protected surfaces record black).
- AgentCore cold start: the first story after a deploy reached "ready" in 18 s end to end (phone upload → 9 narrated pages), compared with 14–16 s warm through Lambda only. Not yet measured after a long idle period.
