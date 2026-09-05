# X Image and Mixed-Media Support

## Goal

Let the bot return all media from an X post: one photo, several photos, or a
mixture of photos and videos. Existing X video downloads and the persisted
`COOKIES_FILE` path must continue to work unchanged.

## Scope

- Support X static-photo media (`jpg`, `jpeg`, `png`, and `webp`) as Telegram
  photos.
- Return each item from a mixed X post in the order in which X presents it.
- Keep yt-dlp as the video and animated-GIF downloader.
- Reuse the existing Netscape cookies file for X photo extraction.
- Cache photo `file_id` values so repeat requests do not download the post
  again.

## Design

yt-dlp intentionally excludes X media whose type is `photo`, so it remains the
video path only. A `gallery-dl` probe will read the X post's full media manifest
with the same cookies file. Its `num` field identifies each asset's original
position. A second gallery-dl invocation downloads only static photos into the
task directory; yt-dlp continues to download video items.

`DownloadResult` gains an explicit media kind and source order. The handler
merges photo results and video results by that order before uploading them. A
failure to inspect photos must fall back to the current yt-dlp-only video
behavior, so an unavailable optional extractor cannot break current downloads.

The uploader adds a photo path (`send_photo`) before the existing
audio/video/document branches. Cache extraction and cache resend gain a
`photo` entry. Generated yt-dlp thumbnails remain excluded: they are not added
to the primary media-file extension set and are never used as photo results.

## Error Handling

- A photo-only post succeeds when gallery-dl downloads at least one photo,
  regardless of yt-dlp's expected "no video" result.
- A mixed post returns every asset that was downloaded; a failed optional photo
  probe does not hide a successful video download.
- Unsupported image formats are sent as documents rather than being coerced
  into videos.
- If gallery-dl is absent, the bot logs the condition and preserves the
  pre-feature yt-dlp behavior.

## Verification

Unit tests cover manifest parsing/order, photo-only success, mixed-result
ordering, photo upload, photo cache extraction/resend, and the guard that
keeps thumbnail files out of primary results. The full pytest suite and a
Docker image build verify the integration.
