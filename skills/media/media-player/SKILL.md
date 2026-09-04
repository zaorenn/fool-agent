---
name: media-player
description: "Search, play, and control YouTube videos, Spotify music, and media playback."
version: 1.0.0
author: The Fool Team
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Media, YouTube, Music, Spotify, Video, Playback]
    related_skills: [youtube-content]
---

# Media Player & Streaming Skill

## When to Use
Use when the user asks to:
- Play, watch, or listen to any song, album, podcast, or video.
- Recommend and open an interesting video from YouTube or a topic of interest.
- Control Spotify playback or search for music on Spotify.
- Open media streams in the background or default browser.

## Core Rules for Fast Media Playback
1. **Never use heavy browser automation (`browser_navigate`, `browser_exec`) just to open or play media.**
   Automation windows are separate from the user's browser, lack user logins/cookies, and consume 40,000+ tokens.
2. **Always open the link in the user's default browser or local desktop app using `terminal`**:
   - **Windows**: `cmd /c start "" "<url>"`
   - **macOS**: `open "<url>"`
   - **Linux**: `xdg-open "<url>"`
3. **Autoplay Parameter**:
   When opening YouTube, append `&autoplay=1` (or `?autoplay=1`) so playback begins automatically.

## YouTube Video Discovery & Playback Flow
When the user asks for a video (e.g. "ana sayfamda ilgi çekici bir video aç", "yapay zeka hakkında son gelişmeleri içeren bir video aç"):
1. **Search YouTube**:
   Run `web_search(query="site:youtube.com <search keywords>", limit=3)`.
2. **Select the Best Video**:
   Pick the most relevant, high-quality, and recent video link (`https://www.youtube.com/watch?v=...`).
3. **Launch the Video**:
   Run terminal command to open it in default browser with `&autoplay=1`:
   - Windows: `cmd /c start "" "https://www.youtube.com/watch?v=VIDEO_ID&autoplay=1"`
4. **Report back**:
   In 1-2 sentences, tell the user the title of the video you opened and a brief 1-line description of what it covers.

## Spotify Integration Flow
1. **If Spotify Tools Are Active (`spotify_*`)**:
   Use `spotify_search` and `spotify_play` to stream directly to active Spotify Connect devices.
2. **If Spotify Is Not Yet Authenticated**:
   Open the search/track directly in their native Spotify desktop app:
   - Windows: `cmd /c start spotify:search:<song+or+artist>`
   - macOS: `open "spotify:search:<song+or+artist>"`
   - Linux: `xdg-open "spotify:search:<song+or+artist>"`
   And inform the user:
   "Playing in your Spotify app! To control Spotify seamlessly in the background, run `fool tools` and `fool auth spotify`."
