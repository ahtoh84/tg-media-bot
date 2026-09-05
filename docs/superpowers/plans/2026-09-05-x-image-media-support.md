# X Image and Mixed-Media Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Download and return all static photos, videos, and mixed media from one X post without changing the existing video or cookie behavior.

**Architecture:** Keep yt-dlp as the video pipeline and add gallery-dl as an X-media manifest and static-photo downloader. A media kind and X source-order value travel from download results to the uploader and cache so photos are sent as Telegram photos and mixed posts retain their source order.

**Tech Stack:** Python 3.12, aiogram 3.x, yt-dlp, gallery-dl, pytest, Docker.

---

### Task 1: Add an explicit media-result contract

**Files:**
- Modify: `src/downloaders/ytdlp.py`
- Test: `tests/test_ytdlp.py`

- [ ] **Step 1: Write the failing test**

```python
def test_downloaded_files_exclude_thumbnail_images(tmp_path):
    (tmp_path / "video.mp4").write_bytes(b"video")
    (tmp_path / "video.jpg").write_bytes(b"thumbnail")
    assert downloader._find_downloaded_files(tmp_path) == [tmp_path / "video.mp4"]
```

- [ ] **Step 2: Run the targeted test and verify it passes as the existing safety contract**

Run: `python -m pytest tests/test_ytdlp.py -q`

- [ ] **Step 3: Add `media_kind` and `source_order` fields to `DownloadResult`**

```python
media_kind: str = "video"
source_order: int = 0
```

- [ ] **Step 4: Run the targeted test**

Run: `python -m pytest tests/test_ytdlp.py -q`

- [ ] **Step 5: Commit**

```bash
git add src/downloaders/ytdlp.py tests/test_ytdlp.py
git commit -m "feat: model downloaded media kinds"
```

### Task 2: Extract and download X static photos

**Files:**
- Modify: `src/downloaders/ytdlp.py`
- Modify: `requirements.txt`
- Modify: `Dockerfile`
- Modify: `docker-entrypoint.sh`
- Test: `tests/test_ytdlp.py`

- [ ] **Step 1: Write failing tests for a gallery-dl manifest and photo-only result**

```python
async def test_twitter_photo_only_result_succeeds_when_ytdlp_has_no_video(...):
    results = await downloader.download_many(...)
    assert [result.media_kind for result in results] == ["photo"]
```

- [ ] **Step 2: Run the targeted test and verify it fails because no gallery-dl photo path exists**

Run: `python -m pytest tests/test_ytdlp.py -q`

- [ ] **Step 3: Implement gallery-dl manifest parsing and static-photo downloading**

```python
manifest = await self._inspect_twitter_media(url)
photos = await self._download_twitter_photos(url, output_dir, manifest)
```

Use `--config-ignore`, the existing `COOKIES_FILE` when available, and
`extractor.twitter.videos=false` for the download command. Keep image files in
a dedicated task subdirectory so yt-dlp thumbnail discovery cannot select them.

- [ ] **Step 4: Merge successful photo and yt-dlp video results by manifest order**

```python
return sorted(results, key=lambda result: result.source_order)
```

- [ ] **Step 5: Run the targeted tests**

Run: `python -m pytest tests/test_ytdlp.py -q`

- [ ] **Step 6: Commit**

```bash
git add src/downloaders/ytdlp.py requirements.txt Dockerfile docker-entrypoint.sh tests/test_ytdlp.py
git commit -m "feat: download X post photos"
```

### Task 3: Send and cache Telegram photos

**Files:**
- Modify: `src/services/uploader.py`
- Modify: `src/bot/handlers.py`
- Test: `tests/test_media_cache.py`
- Test: `tests/test_handlers.py`

- [ ] **Step 1: Write failing tests for `send_photo`, cached photo resend, and photo/video order**

```python
message = await uploader.upload_media(..., media_kind="photo")
bot.send_photo.assert_awaited_once()
assert cache_entry_from_message(message)["kind"] == "photo"
```

- [ ] **Step 2: Run the targeted tests and verify they fail because photo is not a supported upload/cache kind**

Run: `python -m pytest tests/test_media_cache.py tests/test_handlers.py -q`

- [ ] **Step 3: Add `upload_photo`, photo cache extraction, and cache resend**

```python
if media_kind == "photo":
    return await self.upload_photo(...)
```

- [ ] **Step 4: Pass each result's media kind through the handler and make completion wording media-neutral**

```python
media_kind=result.media_kind
suffix = f"{len(successful_results)} media files"
```

- [ ] **Step 5: Run the targeted tests**

Run: `python -m pytest tests/test_media_cache.py tests/test_handlers.py -q`

- [ ] **Step 6: Commit**

```bash
git add src/services/uploader.py src/bot/handlers.py tests/test_media_cache.py tests/test_handlers.py
git commit -m "feat: upload X post photos"
```

### Task 4: Verify, document, and deploy

**Files:**
- Modify: `README.md`
- Test: `tests/test_ytdlp.py`
- Test: `tests/test_media_cache.py`
- Test: `tests/test_handlers.py`

- [ ] **Step 1: Add README language stating that X static photos and mixed-media posts are supported**

- [ ] **Step 2: Run the full suite and syntax check**

Run: `python -m pytest -q && python -m py_compile main.py src/**/*.py`

Expected: all tests pass and the syntax check exits zero.

- [ ] **Step 3: Build the Docker image**

Run: `docker build -t tg-media-bot:image-media-support .`

Expected: image builds with both yt-dlp and gallery-dl installed.

- [ ] **Step 4: Review staged changes for secrets and scope**

Run: `git diff --staged && git diff --staged | grep -i "password\\|secret\\|api_key\\|token"`

Expected: no credentials or cookie contents appear.

- [ ] **Step 5: Commit**

```bash
git add README.md tests
git commit -m "docs: describe X image media support"
```
