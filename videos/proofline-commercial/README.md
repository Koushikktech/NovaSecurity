# Proofline hackathon film

100 seconds · 1920×1080 · 30 fps · H.264 MP4.

- `proofline-hackathon-music.mp4`: final film, quiet instrumental bed, no narration.
- `proofline-hackathon-clean.mp4`: the same picture without audio, ready for a custom mix.
- `NARRATION.md`: the timed, conversational voice-over script.
- `UPLOAD-DESCRIPTION.md`: copyable upload description and required music credit.
- `CREDITS.md`: asset sources, licenses and modifications.

The story follows the actual authored checkout case: a pricing default disappears, an unchanged caller breaks, source evidence explains it, the model repairs the caller, and the same protected test passes/fails/passes on the original/changed/repaired snapshots. Diagrams and the cart are original explanatory motion graphics. The app image is an actual recorded result. This is an edited demonstration, not uninterrupted live inference or general accuracy measurement.

## Reproduce

Requires Node.js 22+, FFmpeg, and the Chromium browser used by HyperFrames. Dependencies and media are pinned/local. No model calls, account access or backend are needed to replay/render this film.

```sh
npm run check
npx --yes hyperframes@0.9.9 preview --background
npm run render -- --quality delivery --fps 30 --output proofline-hackathon-music.mp4
ffmpeg -i proofline-hackathon-music.mp4 -map 0:v:0 -c:v copy -an -movflags +faststart proofline-hackathon-clean.mp4
```

The composition uses one paused, seekable GSAP timeline. Scene times and audio automation are authored explicitly; the renderer owns audio playback. The earlier static 120-second chapter walkthrough remains in `../checkout-film` for reference.
