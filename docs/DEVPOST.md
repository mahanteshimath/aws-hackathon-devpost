# Devpost submission text (draft)

> Paste into Devpost. Replace every `TODO` with real links and measured numbers before submitting.

**Project name:** Crayon Cinema
**Tagline:** Tonight's bedtime story stars whatever your child drew today.
**Tracks:** Fire TV (main) · AWS Builder mini challenge · Open Source mini challenge
**Built by:** Mahantesh Hiremath (solo)

## Inspiration

Kids draw heroes every day: dinosaurs with too many legs, cats with wings, a "rainbow robot". The drawings go on the fridge, and at bedtime the TV plays someone else's characters. I wanted the biggest screen in the house to celebrate what the child made, and to turn screen time into a shared, calm, creative ritual.

## What it does

1. **Draw:** a child draws any hero on paper.
2. **Snap:** a parent scans the QR code on the TV (no app install) and photographs the drawing.
3. **Meet your hero:** the drawing jumps off the page on Fire TV. It's cut out of the paper with a sticker border, named, and greets the child in a child's voice.
4. **Watch and read along:** a picture-book story is narrated and each word lights up as it's read. Every scene is painted with the child's own crayon colours, and the hero walks, hops or flies across it.
5. **Choose:** halfway through, kids decide what happens next with the Fire TV remote.
6. **Bedtime mode:** after 7 pm it gets darker and slower and ends with the hero falling asleep.
7. **Story Shelf:** every hero is saved for the family and can make cameos in future stories.

## How we built it

- **Fire TV app:** a Kotlin WebView shell running a 10-foot web UI.
  - Every remote key (D-pad, OK, Back, Menu, media keys) goes through one bridge.
  - Back exits only from the home screen.
  - Narration autoplays, a copy of the app bundled in the APK works offline, and a LAN dev mode lets me iterate on the real TV.
  - Spatial D-pad navigation; only transforms and opacity are animated, for smooth playback on stick hardware.
- **Agents (Strands Agents on Amazon Bedrock AgentCore Runtime):**
  - **Casting agent** (Amazon Nova 2 Lite with vision) looks at the drawing and returns a validated `CharacterCard`: name, species, traits, how it moves, voice, greeting.
  - **Director agent** (Amazon Nova 2 Lite) calls a `recall_household_universe` tool backed by **AgentCore Memory**. It returns a validated `StoryPlan`: 3 pages, a choice, and 2 branches of 3 pages.
- **Generation:**
  - **Stability AI Remove Background** on Bedrock cuts the hero out of the paper. A coverage check and a local "paper key" fallback protect thin crayon strokes.
  - **Stability AI SD3.5 Large** on Bedrock paints every scene; the prompt names the drawing's own crayon colours.
  - **Amazon Polly** neural voices narrate, with word speech marks for read-along.
- **Safety:** **Bedrock Guardrails** (content filters, denied scary topics, PII blocking) check every text a child will see. Blocked generations fall back to a safe template story.
- **Serving:** a Lambda function URL serves the API plus the TV and phone apps. S3 holds the story documents and assets. One idempotent boto3 script deploys everything.
- **Streaming UX:** the cast reveal arrives first, pages stream as they finish, and the branch the child picks is rendered first.

## Challenges

- **Latency for a 4-year-old's patience.** I restructured the pipeline so the reveal arrives first and illustration and narration run in priority order, streaming page by page. On the deployed stack the hero is on screen about 6 s after the upload, and all 9 narrated pages are ready by about 18 s.
- **The image model disappeared.** Nova Canvas, the base of the original design, reached end of life during the build. I moved to Stability AI on Bedrock and kept a local fallback for every image step, so a story always plays.
- **Picking a model by measuring it.** Nova Pro needed 449 s and broke the tool-use format; Nova 2 Lite wrote the same validated story in about 6 s.
- **Crayon on paper is not a photo.** Generic background removal can drop thin lines, so I added a coverage check plus a deterministic local fallback.
- **Read-along sync.** Polly's speech-mark offsets are UTF-8 byte positions in the SSML, tags included. I convert them to character ranges, with tests.
- **Fire TV remote in a WebView.** Back, Menu and media keys never reach the page by default, so I built a native bridge and open-sourced it.

## Accomplishments

- A real child's drawing becomes an animated, voiced character in about 6 seconds, with the full 9-page narrated story ready in about 18 seconds (measured on the deployed AWS stack; TODO: confirm on the Fire TV).
- It runs without a touchscreen, account or ads, and the original photo is deleted after the cut-out.
- **Open source:** [`firetv-webview-kit`](https://github.com/mahanteshimath/aws-hackathon-devpost/tree/main/oss/firetv-webview-kit). It provides D-pad spatial navigation, the remote bridge and a Kotlin shell template, MIT licensed and tested.

## What we learned

- On TV, the first 10 seconds matter more than everything after; the "jump off the page" moment carries the experience.
- Structured outputs plus guardrails make generative content for kids practical. You design the shape of the story, not just the prompt.

## What's next

- Voice: Alexa+ ("Alexa, read tonight's Crayon Cinema").
- Multiple drawings becoming a cast of friends in one story.
- Printable storybook export.
- Submission to the Amazon Appstore.

## Built with

`fire-tv` `kotlin` `android-webview` `javascript` `amazon-bedrock` `bedrock-agentcore` `agentcore-memory` `strands-agents` `amazon-nova` `stability-ai` `amazon-polly` `bedrock-guardrails` `aws-lambda` `amazon-s3` `python`

## Links

- Repo: https://github.com/mahanteshimath/aws-hackathon-devpost (MIT)
- Video: TODO
- APK: TODO (GitHub release; built locally at `dist/crayon-cinema-firetv.apk`)
- Try it: https://e7szjoxoeoyy3fwly4nyzjv2e40djaoh.lambda-url.us-east-1.on.aws/tv/ (open in a browser; arrow keys and Enter act as the remote, and a phone scans the QR code)
