# Command Reference

Complete reference for all bot commands.

## Commands

### `/start`

Starts the bot and sends welcome message.

**Usage:**
```
/start
```

**Response:**
```
👋 Welcome to Media Downloader Bot!

Send me a URL to download media.
Use /help for all commands.
```

---

### `/help`

Shows help message with supported platforms.

**Usage:**
```
/help
```

**Response:**
```
<b>Media Downloader Bot</b>

Send me any media URL and I'll download and send it back to you.

<b>Commands:</b>

/start - Start the bot
/help - Show this help
/audio - Switch to audio-only mode (MP3)
/video - Switch to video download mode
/formats <url> - Pick a download quality (buttons)
/cancel <task_id> - Cancel a download
/status - Show your active downloads
/minimal on|off - Toggle minimal UI (no status messages, no caption on media)
/topic lock|unlock|status - Restrict the bot to one forum topic in this group

<b>Supported Platforms:</b>
• YouTube
• SoundCloud
• Vimeo
• TikTok
• Twitter/X
• Instagram
• Reddit
• Twitch
• And 1000+ more via yt-dlp
```

---

### `/audio`

Switch to audio-only download mode. Downloads will be converted to MP3.

**Usage:**
```
/audio
```

**Response:**
```
🎵 Audio-only mode enabled. Downloads will be converted to MP3.
```

**Notes:**
- Persists until changed with `/video`
- Best for music/podcasts

---

### `/video`

Switch to video download mode. Downloads will include video when available.

**Usage:**
```
/video
```

**Response:**
```
🎬 Video mode enabled. Downloads will include video when available.
```

**Notes:**
- Persists until changed with `/audio`
- Best for music videos, clips

---

### `/formats <url>`

Show an inline quality picker for a URL — tap a button to queue that download,
instead of using the current `/audio`/`/video` preference.

**Usage:**
```
/formats https://youtube.com/watch?v=...
```

**Response:** a "🎚️ Choose a quality:" message with buttons:

```
[ 🎬 Best ]
[ 1080p ]
[ 720p ]
[ 480p ]
[ 🎵 Audio (MP3) ]
```

**Notes:**
- A height cap that exceeds what's actually available just falls back to the best stream — every button is always valid.
- The picker expires if the bot restarts before you tap one; just send `/formats <url>` again.

---

### `/cancel <task_id>`

Cancel a pending or active download.

**Usage:**
```
/cancel <task_id>
```

**Example:**
```
/cancel a1b2c3d4
```

**Response (success):**
```
✅ Task a1b2c3d4 cancelled.
```

**Response (failure):**
```
❌ Could not cancel task a1b2c3d4.
Make sure the task is yours and still active.
```

**Notes:**
- Get task ID from status message
- Can only cancel your own tasks
- Only works on active tasks

---

### `/status`

Show your active downloads and queue status.

**Usage:**
```
/status
```

**Response:**
```
📊 Your Downloads:

Total tasks: 5
Active: 2/2

  queued: 1
  downloading: 1
  completed: 3
```

---

### `/minimal on|off`

Toggle minimal UI mode for the current chat: no queued/progress/"Done!"
status messages, and uploaded media carries no title/source-URL caption —
just the file itself. Failures are still reported.

**Usage:**
```
/minimal on
/minimal off
/minimal
```

**Response:**
```
🤫 Minimal UI mode enabled. Downloads will be sent with no status messages and no caption.
```

Run with no argument to see the current state instead of changing it.

**Notes:**
- Per-chat, not per-user — affects everyone using the bot in that chat.
- Persists across restarts if `MINIMAL_MODE_FILE` is set.

---

### `/topic lock|unlock|status`

Restrict the bot to a single forum topic in a group with topics enabled.
Once locked, messages in every other topic — including "General" — are
ignored; `/topic` itself always still works, from any topic, so a chat can't
get locked out of managing its own restriction.

**Usage:**
```
/topic lock      (send from inside the topic you want the bot confined to)
/topic unlock
/topic status
```

**Response:**
```
🔒 Bot restricted to this topic (id 7) in this group.
Other topics, including General, are now ignored. /topic unlock to undo.
```

**Notes:**
- Per-chat — each group can lock to its own topic independently, or not lock at all.
- Only applies to groups/supergroups with topics enabled; has no effect in a private chat.
- Persists across restarts if `TOPIC_LOCK_FILE` is set.

---

## URL Processing

### Sending URLs

Simply send any supported URL as a message:

```
https://youtube.com/watch?v=dQw4w9WgXcQ
https://soundcloud.com/artist/track
https://vimeo.com/123456789
```

**Features:**
- Extracts URLs from text (no need for clean URL)
- Supports multiple URLs (up to 3 per message)
- Truncates URLs longer than 2048 characters

### Download Flow

1. URL sent → Queued
2. Status message shows progress
3. File uploaded to Telegram
4. Temp files cleaned up

### Status Messages

During download, you'll see:

```
⏳ Queued download...
Platform: youtube
Task ID: `a1b2c3d4`
Quality: auto
```

```
📥 Downloading...
`███████░░░░░░░░░░░░░` 35%
2.1MiB/s · ETA 00:12
Task: `a1b2c3d4`
```

The same message is edited in place as the download progresses, then briefly
shows `🔄 Processing (merging/encoding)…` if yt-dlp needs a post-processing
step (e.g. muxing separate audio/video streams).

```
📤 Uploading… 4s · 12 MB
Task: `a1b2c3d4`
```

Uploads have no real progress from the Bot API, so this is a liveness
indicator (elapsed time + size) rather than a percentage.

```
✅ Done!
rickroll.mp4
Size: 12.5MB
```

In minimal mode (`/minimal on`), none of the above status messages appear —
only the final file, with no caption. Failures are still reported.

### Error Messages

```
❌ Download failed

Unsupported URL
```

```
❌ Upload failed.
File: video.mp4
Size: 125.0MB

Telegram Bot API has a 50MB upload limit.
Consider using a Local Bot API Server for larger files.
```

## Supported Platforms

| Platform | URL Patterns |
|----------|--------------|
| YouTube | youtube.com, youtu.be |
| SoundCloud | soundcloud.com |
| Vimeo | vimeo.com |
| TikTok | tiktok.com |
| Twitter/X | twitter.com, x.com |
| Instagram | instagram.com |
| Reddit | reddit.com |
| Twitch | twitch.tv |

Plus 1000+ more via yt-dlp. Run `/formats <url>` to check specific sites.

## Tips

1. **Batch downloading**: Send multiple URLs in one message (max 3)
2. **Audio mode**: Use `/audio` before sending music URLs
3. **Check formats**: Use `/formats` before downloading to see options
4. **Cancel stuck downloads**: Use `/cancel` with task ID
5. **Check status**: Use `/status` to see your queue
