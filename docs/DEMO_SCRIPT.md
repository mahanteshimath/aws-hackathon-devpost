# Demo video script (target 2:45, hard limit under 3:00)

**Rules check:** the app must be shown **running on a real Fire TV**. Film the TV screen with the remote in frame for at least the reveal and the choice. Use `scripts/firetv.sh record` for clean screen captures if the device supports `screenrecord`, and cut in shots of the room (phone, paper, remote, child's hands).

**Props:** a real child's drawing, or your own crayon doodle (the sample dino is fine for rehearsal). A phone, the Fire TV remote, and a dim room for the bedtime segment.

**Before filming:** run one warm-up story so the Lambda and AgentCore runtimes are warm. Keep `.env` in `aws` mode. Pick the best take of the reveal.

| Time | Picture | Voice-over / on-screen text |
|---|---|---|
| 0:00–0:10 | Close-up: child's hand finishing a crayon drawing. | "Every kid draws heroes. Then the drawing goes on the fridge… and the TV plays someone else's story." |
| 0:10–0:22 | Fire TV home screen → open **Crayon Cinema** with the remote. Home shows the QR code and the Story Shelf. | "Crayon Cinema turns tonight's story into *their* story." |
| 0:22–0:35 | Parent scans the QR code, snaps the drawing, types the name "Maya", taps **Bring it to life**. | "No app to install. Scan, snap, send." |
| 0:35–0:55 | **TV: the drawing jumps off the paper.** Confetti, the name card, and the hero greets Maya in a child's voice with words lighting up. | Let the moment play; no voice-over for 5 s. Then: "It's really her drawing, cut out of the paper and cast as the hero." |
| 0:55–1:25 | Story pages: scenes painted in *the same crayon colours*, the hero walking or hopping across, read-along highlighting. | "Nova writes a gentle story, Stability paints worlds in her crayon colours, and Polly reads along word by word." |
| 1:25–1:45 | **Choice moment:** "Where should Captain Doodle go?" Child presses ◀/▶ on the remote and selects. | "Kids choose what happens next, right on the remote." |
| 1:45–2:05 | Bedtime mode (dim room): stars, slower narration, the hero yawns and falls asleep. The End, then saved to the Story Shelf. | "After 7 pm it becomes a bedtime story: calmer, slower, with a sleepy ending. And every hero is saved to the family's shelf, ready to come back tomorrow." |
| 2:05–2:35 | Architecture diagram (from the README), animated in 3 beats: Phone → Lambda → **AgentCore Runtime** (Casting and Director agents, Memory) → Stability AI images, Polly, **Guardrails** → Fire TV. | "Under the hood: two Strands agents on Amazon Bedrock AgentCore, with AgentCore Memory so heroes come back. Every word a child sees passes Bedrock Guardrails. The photo is deleted after the cut-out, and everything expires in 30 days." |
| 2:35–2:45 | Quick cut: `firetv-webview-kit` README and its tests passing. Final frame: the child's hero on the TV, logo, "Crayon Cinema". | "We open-sourced the Fire TV web kit we built along the way. Crayon Cinema: tonight's story stars whatever you drew today." |

**Captions:** burn in subtitles; judges often watch muted.

**Export:** 1080p, under 3:00. Upload to YouTube as unlisted or public, and test the link in a private window.
