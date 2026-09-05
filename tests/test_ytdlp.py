"""Tests for the yt-dlp downloader wrapper (no network)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.downloaders.ytdlp as ytdlp_module
from src.downloaders.ytdlp import (
    DownloadResult,
    YtDlpDownloader,
    friendly_error,
    parse_progress_line,
    render_progress_bar,
)
from src.types.download import MediaFormat


class TestFriendlyError:
    @pytest.mark.parametrize("raw,needle", [
        ("ERROR: Sign in to confirm your age", "age-restricted"),
        ("ERROR: Private video. Sign in", "private"),
        ("ERROR: Requested format is not available", "quality"),
        ("ERROR: Video unavailable", "unavailable"),
        ("ERROR: Unsupported URL: https://x", "supported media URL"),
        ("ERROR: HTTP Error 404: Not Found", "404"),
        ("ERROR: blocked it in your country", "Region-restricted"),
    ])
    def test_maps_known_errors(self, raw, needle):
        assert needle.lower() in friendly_error(raw).lower()

    def test_unknown_error_trimmed(self):
        out = friendly_error("ERROR: some novel failure mode")
        assert "some novel failure mode" in out
        assert "ERROR:" not in out

    def test_empty(self):
        assert friendly_error("") == "Download failed."


@pytest.fixture
def dl():
    # _check_yt_dlp is patched out by the autouse conftest fixture
    return YtDlpDownloader()


class TestDetectPlatform:
    @pytest.mark.parametrize("url,expected", [
        ("https://youtube.com/watch?v=x", "youtube"),
        ("https://youtu.be/x", "youtube"),
        ("https://soundcloud.com/a/b", "soundcloud"),
        ("https://vimeo.com/123", "vimeo"),
        ("https://www.tiktok.com/@a/video/1", "tiktok"),
        ("https://x.com/a/status/1", "twitter"),
        ("https://twitter.com/a/status/1", "twitter"),
        ("https://instagram.com/p/x", "instagram"),
        ("https://reddit.com/r/x", "reddit"),
        ("https://twitch.tv/x", "twitch"),
        ("https://example.com/x", "unknown"),
    ])
    def test_detect(self, dl, url, expected):
        assert dl.detect_platform(url) == expected


class TestValidateUrl:
    def test_valid(self, dl):
        assert dl.validate_url("https://youtube.com/watch?v=x")
        assert dl.validate_url("http://example.com")

    def test_invalid(self, dl):
        assert not dl.validate_url("")
        assert not dl.validate_url("ftp://example.com")
        assert not dl.validate_url("not a url")
        assert not dl.validate_url("https://" + "x" * 3000)


class TestBuildCommand:
    def test_x_urls_allow_multiple_playlist_entries(self, dl, tmp_path):
        cmd = dl._build_command(
            "https://x.com/user/status/123", tmp_path, MediaFormat.VIDEO
        )
        assert "--no-playlist" not in cmd
        output_template = cmd[cmd.index("-o") + 1]
        assert "%(id)s" in output_template

    def test_non_x_urls_keep_single_item_behavior(self, dl, tmp_path):
        cmd = dl._build_command(
            "https://youtube.com/watch?v=123", tmp_path, MediaFormat.VIDEO
        )
        assert "--no-playlist" in cmd

    def test_audio_embeds_thumbnail_and_metadata(self, dl, tmp_path):
        cmd = dl._build_command("https://x", tmp_path, MediaFormat.AUDIO)
        for flag in ("-x", "--embed-thumbnail", "--embed-metadata", "--write-info-json"):
            assert flag in cmd
        assert "mp3" in cmd

    def test_video_merges_to_mp4(self, dl, tmp_path):
        cmd = dl._build_command("https://x", tmp_path, MediaFormat.VIDEO)
        assert "--merge-output-format" in cmd
        assert "mp4" in cmd

    def test_video_recodes_for_inline_playback(self, dl, tmp_path):
        # Direct .webm URLs etc. must be transcoded so Telegram plays them inline
        cmd = dl._build_command("https://x", tmp_path, MediaFormat.VIDEO)
        assert "--recode-video" in cmd
        assert "VideoConvertor:-movflags +faststart" in cmd

    def test_auto_recodes_for_inline_playback(self, dl, tmp_path):
        cmd = dl._build_command("https://x", tmp_path, MediaFormat.AUTO)
        assert "--recode-video" in cmd
        assert "VideoConvertor:-movflags +faststart" in cmd

    def test_cookies_added_when_enabled(self, dl, tmp_path):
        dl.settings.use_browser_cookies = True
        dl.settings.browser_name = "firefox"
        cmd = dl._build_command("https://x", tmp_path, MediaFormat.AUTO)
        assert "--cookies-from-browser" in cmd
        assert "firefox" in cmd

    def test_cookies_absent_when_disabled(self, dl, tmp_path):
        dl.settings.use_browser_cookies = False
        dl.settings.cookies_file = ""
        cmd = dl._build_command("https://x", tmp_path, MediaFormat.AUTO)
        assert "--cookies-from-browser" not in cmd
        assert "--cookies" not in cmd

    def test_progress_flags_present(self, dl, tmp_path):
        cmd = dl._build_command("https://x", tmp_path, MediaFormat.AUDIO)
        assert "--newline" in cmd and "--progress-template" in cmd
        assert any(arg.startswith("download:PROG|") for arg in cmd)

    def test_use_cookies_false_omits_cookies(self, dl, tmp_path):
        cookies = tmp_path / "cookies.txt"
        cookies.write_text("# Netscape HTTP Cookie File\n")
        dl.settings.cookies_file = str(cookies)
        dl.settings.use_browser_cookies = True
        cmd = dl._build_command("https://x", tmp_path, MediaFormat.AUTO, use_cookies=False)
        assert "--cookies" not in cmd
        assert "--cookies-from-browser" not in cmd

    def test_user_agent_flag_present(self, dl, tmp_path):
        cmd = dl._build_command("https://x", tmp_path, MediaFormat.AUTO)
        assert "--user-agent" in cmd

    def test_gallery_dl_does_not_write_back_to_cookie_file(self, dl, tmp_path):
        cookies = tmp_path / "cookies.txt"
        cookies.write_text("# Netscape HTTP Cookie File\n")
        dl.settings.cookies_file = str(cookies)

        cmd = dl._gallery_base_command()

        assert "--cookies" in cmd and str(cookies) in cmd
        assert "extractor.cookies-update=false" in cmd


class TestResolveUserAgent:
    def test_no_cookies_uses_default(self, dl):
        dl.settings.use_browser_cookies = False
        dl.settings.cookies_file = ""
        assert dl._resolve_user_agent(use_cookies=True) == ytdlp_module._DEFAULT_USER_AGENT

    def test_use_cookies_false_uses_default_even_if_configured(self, dl):
        dl.settings.use_browser_cookies = True
        dl.settings.browser_name = "firefox"
        assert dl._resolve_user_agent(use_cookies=False) == ytdlp_module._DEFAULT_USER_AGENT

    def test_matches_configured_browser(self, dl):
        dl.settings.use_browser_cookies = True
        dl.settings.browser_name = "firefox"
        assert (
            dl._resolve_user_agent(use_cookies=True)
            == ytdlp_module._BROWSER_USER_AGENTS["firefox"]
        )

    def test_unrecognized_browser_falls_back_to_default(self, dl):
        dl.settings.use_browser_cookies = True
        dl.settings.browser_name = "some-obscure-browser"
        assert dl._resolve_user_agent(use_cookies=True) == ytdlp_module._DEFAULT_USER_AGENT

    def test_default_is_chrome(self):
        # The default is deliberately the most common browser (least likely
        # to look anomalous with no cookies attached) — pin it so a future
        # edit can't silently swap it for a less common family.
        assert ytdlp_module._DEFAULT_USER_AGENT == ytdlp_module._BROWSER_USER_AGENTS["chrome"]


class TestFormatErrorDetection:
    @pytest.mark.parametrize("err,expected", [
        ("ERROR: Requested format is not available", True),
        ("ERROR: Unable to extract player response", True),
        ("ERROR: no video formats found", True),
        ("ERROR: Private video", False),
        ("ERROR: HTTP Error 404", False),
        ("", False),
    ])
    def test_is_format_error(self, err, expected):
        assert YtDlpDownloader._is_format_error(err) is expected

    def test_cookies_file_used_when_present(self, dl, tmp_path):
        cookies = tmp_path / "cookies.txt"
        cookies.write_text("# Netscape HTTP Cookie File\n")
        dl.settings.cookies_file = str(cookies)
        dl.settings.use_browser_cookies = True  # file still wins
        cmd = dl._build_command("https://x", tmp_path, MediaFormat.AUTO)
        assert "--cookies" in cmd
        assert str(cookies) in cmd
        assert "--cookies-from-browser" not in cmd

    def test_missing_cookies_file_falls_back_to_browser(self, dl, tmp_path):
        dl.settings.cookies_file = str(tmp_path / "does-not-exist.txt")
        dl.settings.use_browser_cookies = True
        cmd = dl._build_command("https://x", tmp_path, MediaFormat.AUTO)
        assert "--cookies" not in cmd
        assert "--cookies-from-browser" in cmd


class TestProxyWorthy:
    @pytest.mark.parametrize("err,expected", [
        ("ERROR: blocked it in your country", True),
        ("ERROR: not available in your country", True),
        ("_ssl.c:993: The handshake operation timed out", True),
        ("ERROR: [Foo] x: Unable to download webpage: <urlopen error timed out>", True),
        ("ConnectionResetError: Connection reset by peer", True),
        ("ERROR: Private video", False),
        ("ERROR: Requested format is not available", False),
        ("", False),
    ])
    def test_is_proxy_worthy(self, dl, err, expected):
        assert dl._is_proxy_worthy(err) is expected

    @pytest.mark.parametrize("err,expected", [
        ("_ssl.c:993: The handshake operation timed out", True),
        ("ConnectionResetError: Connection reset by peer", True),
        ("ERROR: blocked it in your country", False),  # geo-block, not transient
        ("ERROR: Private video", False),
        ("", False),
    ])
    def test_is_connectivity_error(self, dl, err, expected):
        assert dl._is_connectivity_error(err) is expected


class TestEffectiveFormat:
    def test_soundcloud_forced_to_audio(self, dl):
        assert dl._effective_format("soundcloud", MediaFormat.AUTO) == MediaFormat.AUDIO
        assert dl._effective_format("soundcloud", MediaFormat.VIDEO) == MediaFormat.AUDIO

    def test_youtube_respects_preference(self, dl):
        assert dl._effective_format("youtube", MediaFormat.AUTO) == MediaFormat.AUTO
        assert dl._effective_format("youtube", MediaFormat.VIDEO) == MediaFormat.VIDEO
        assert dl._effective_format("youtube", MediaFormat.AUDIO) == MediaFormat.AUDIO


class TestFileDiscovery:
    def test_find_downloaded_file_picks_largest_media(self, dl, tmp_path):
        (tmp_path / "small.mp3").write_bytes(b"x" * 10)
        (tmp_path / "big.mp4").write_bytes(b"x" * 100)
        (tmp_path / "cover.jpg").write_bytes(b"x" * 9999)  # not media
        assert dl._find_downloaded_file(tmp_path).name == "big.mp4"

    def test_find_downloaded_file_none_when_empty(self, dl, tmp_path):
        assert dl._find_downloaded_file(tmp_path) is None

    def test_find_downloaded_files_returns_all_media_in_stable_order(self, dl, tmp_path):
        second = tmp_path / "2-second [b].mp4"
        first = tmp_path / "1-first [a].mp4"
        second.write_bytes(b"x" * 10)
        first.write_bytes(b"x" * 100)
        (tmp_path / "cover.jpg").write_bytes(b"x" * 9999)
        assert dl._find_downloaded_files(tmp_path) == [first, second]


class TestMediaResult:
    def test_defaults_to_a_video_with_no_source_order(self):
        result = DownloadResult(success=True)

        assert result.media_kind == "video"
        assert result.source_order == 0


class TestMultiResultDownload:
    async def test_download_many_returns_all_files_from_x_post(
        self, dl, tmp_path, monkeypatch
    ):
        from src.downloaders.ytdlp import DownloadResult

        async def fake_run(cmd, output_dir, platform, cb=None):
            (output_dir / "1-first [a].mp4").write_bytes(b"first")
            (output_dir / "2-second [b].mp4").write_bytes(b"second")
            return DownloadResult(
                success=True,
                output_path=output_dir / "1-first [a].mp4",
                platform=platform,
            )

        monkeypatch.setattr(dl, "_run_download", fake_run)
        results = await dl.download_many(
            "https://x.com/user/status/123", tmp_path, MediaFormat.VIDEO
        )

        assert [result.output_path.name for result in results] == [
            "1-first [a].mp4",
            "2-second [b].mp4",
        ]

    def test_find_thumbnail_prefers_jpg(self, dl, tmp_path):
        (tmp_path / "a.png").write_bytes(b"x")
        (tmp_path / "a.jpg").write_bytes(b"x")
        assert dl._find_thumbnail(tmp_path).suffix == ".jpg"

    def test_find_thumbnail_none(self, dl, tmp_path):
        (tmp_path / "only.mp3").write_bytes(b"x")
        assert dl._find_thumbnail(tmp_path) is None

    def test_find_thumbnail_finds_avif(self, dl, tmp_path):
        # Raw source format — we don't ask yt-dlp to convert (see
        # _build_command); _prepare_thumbnail() converts it downstream.
        (tmp_path / "a.avif").write_bytes(b"x")
        assert dl._find_thumbnail(tmp_path).suffix == ".avif"

    def test_read_info_json(self, dl, tmp_path):
        data = {"title": "T", "artist": "A", "duration": 100}
        (tmp_path / "song.info.json").write_text(json.dumps(data))
        assert dl._read_info_json(tmp_path)["artist"] == "A"

    def test_read_info_json_missing(self, dl, tmp_path):
        assert dl._read_info_json(tmp_path) == {}

    def test_read_info_json_invalid(self, dl, tmp_path):
        (tmp_path / "bad.info.json").write_text("{not json")
        assert dl._read_info_json(tmp_path) == {}


class TestTwitterPhotoDownloads:
    def test_parses_gallery_manifest_without_treating_video_as_a_photo(self, dl):
        payload = json.dumps([
            [2, {"content": "mixed post"}],
            [3, "https://pbs.twimg.com/media/one?format=jpg&name=orig", {
                "type": "photo", "num": 1, "filename": "one", "extension": "jpg",
            }],
            [3, "https://video.twimg.com/ext_tw_video/two.mp4", {
                "type": "video", "num": 2, "filename": "two", "extension": "mp4",
            }],
            [3, "https://pbs.twimg.com/media/three?format=png&name=orig", {
                "type": "photo", "num": 3, "filename": "three", "extension": "png",
            }],
        ])

        manifest = dl._parse_twitter_media_manifest(payload)

        assert manifest.title == "mixed post"
        assert [(photo.source_order, photo.filename, photo.extension) for photo in manifest.photos] == [
            (1, "one", "jpg"),
            (3, "three", "png"),
        ]
        assert manifest.video_orders == (2,)

    async def test_photo_only_tweet_succeeds_without_a_ytdlp_video(self, dl, tmp_path, monkeypatch):
        photo_path = tmp_path / "photos" / "one.jpg"
        photo_path.parent.mkdir()
        photo_path.write_bytes(b"photo")
        manifest = SimpleNamespace(
            photos=(SimpleNamespace(source_order=1, filename="one", extension="jpg"),),
            video_orders=(),
        )
        photo_result = DownloadResult(
            success=True,
            output_path=photo_path,
            file_size=photo_path.stat().st_size,
            media_kind="photo",
            source_order=1,
            platform="twitter",
        )
        dl._gallery_dl_available = True
        monkeypatch.setattr(
            dl, "_inspect_twitter_media", AsyncMock(return_value=manifest), raising=False
        )
        monkeypatch.setattr(
            dl, "_download_twitter_photos", AsyncMock(return_value=[photo_result]), raising=False
        )
        monkeypatch.setattr(
            dl,
            "_run_download",
            AsyncMock(return_value=DownloadResult(success=False, error="No video could be found")),
        )

        results = await dl.download_many(
            "https://x.com/user/status/123", tmp_path, MediaFormat.VIDEO
        )

        assert [(result.media_kind, result.output_path) for result in results] == [
            ("photo", photo_path),
        ]

    async def test_mixed_tweet_returns_photo_video_photo_in_source_order(
        self, dl, tmp_path, monkeypatch
    ):
        first_photo = tmp_path / "photos" / "one.jpg"
        last_photo = tmp_path / "photos" / "three.png"
        first_photo.parent.mkdir()
        first_photo.write_bytes(b"first photo")
        last_photo.write_bytes(b"last photo")
        manifest = SimpleNamespace(
            photos=(
                SimpleNamespace(source_order=1, filename="one", extension="jpg"),
                SimpleNamespace(source_order=3, filename="three", extension="png"),
            ),
            video_orders=(2,),
        )
        photos = [
            DownloadResult(success=True, output_path=first_photo, media_kind="photo", source_order=1),
            DownloadResult(success=True, output_path=last_photo, media_kind="photo", source_order=3),
        ]

        async def fake_video_download(cmd, output_dir, platform, cb=None):
            video = output_dir / "2-video [two].mp4"
            video.write_bytes(b"video")
            return DownloadResult(success=True, output_path=video, platform=platform)

        dl._gallery_dl_available = True
        monkeypatch.setattr(
            dl, "_inspect_twitter_media", AsyncMock(return_value=manifest), raising=False
        )
        monkeypatch.setattr(
            dl, "_download_twitter_photos", AsyncMock(return_value=photos), raising=False
        )
        monkeypatch.setattr(dl, "_run_download", fake_video_download)

        results = await dl.download_many(
            "https://x.com/user/status/123", tmp_path, MediaFormat.VIDEO
        )

        assert [result.media_kind for result in results] == ["photo", "video", "photo"]
        assert [result.source_order for result in results] == [1, 2, 3]


class TestFormatsList:
    def test_empty(self, dl):
        assert dl.format_formats_list([]) == "No formats available."

    def test_lists_entries(self, dl):
        formats = [{"format_id": "18", "ext": "mp4", "type": "video+audio",
                    "resolution": "360p", "filesize": 6_500_000}]
        out = dl.format_formats_list(formats)
        assert "18" in out and "mp4" in out and "6.2MB" in out


class TestProgressParsing:
    def test_parses_full_line(self):
        info = parse_progress_line("PROG| 42.3%|1.20MiB/s|00:05")
        assert info["percent"] == 42.3
        assert info["percent_str"] == "42.3%"
        assert info["speed"] == "1.20MiB/s"
        assert info["eta"] == "00:05"

    def test_non_progress_line_is_none(self):
        assert parse_progress_line("[download] Destination: x.mp4") is None
        assert parse_progress_line("") is None

    def test_unknown_percent(self):
        info = parse_progress_line("PROG|   N/A|   N/A|   N/A")
        assert info is not None and info["percent"] is None

    @pytest.mark.parametrize("pct,filled", [(0, 0), (50, 5), (100, 10), (None, 0)])
    def test_bar_fill(self, pct, filled):
        bar = render_progress_bar(pct)
        assert bar.count("█") == filled
        assert len(bar) == 10

    def test_bar_clamps_over_100(self):
        assert render_progress_bar(150).count("█") == 10


class _FakeStream:
    def __init__(self, lines):
        self._lines = list(lines)

    async def readline(self):
        return self._lines.pop(0) if self._lines else b""


class _FakeProc:
    def __init__(self, stdout_lines, stderr_lines=None, returncode=0):
        self.stdout = _FakeStream(stdout_lines)
        self.stderr = _FakeStream(stderr_lines or [])
        self._rc = returncode
        self.returncode = None

    async def wait(self):
        self.returncode = self._rc
        return self._rc


class TestProgressStreaming:
    async def test_throttles_but_always_emits_completion(self, dl):
        # Three updates arrive back-to-back; the throttle should let the first
        # through and suppress the mid one, but 100% always fires.
        proc = _FakeProc([
            b"[download] Destination: x.mp4\n",   # ignored
            b"PROG| 10.0%|1.0MiB/s|00:10\n",      # first -> emit
            b"PROG| 50.0%|1.0MiB/s|00:05\n",      # within 3s -> suppressed
            b"PROG|100.0%|1.0MiB/s|00:00\n",      # done -> emit
        ])
        seen = []

        async def cb(info):
            seen.append(info["percent"])

        stderr = await dl._stream(proc, cb)
        assert seen == [10.0, 100.0]
        assert proc.returncode == 0
        assert stderr == ""

    async def test_no_callback_is_fine(self, dl):
        proc = _FakeProc([b"PROG| 50.0%|1.0MiB/s|00:05\n"], stderr_lines=[b"oops\n"])
        stderr = await dl._stream(proc, None)
        assert stderr == "oops\n"

    async def test_processing_stage_emitted_from_stderr(self, dl):
        proc = _FakeProc(
            stdout_lines=[b"PROG|100.0%|1.0MiB/s|00:00\n"],
            stderr_lines=[b"[Merger] Merging formats into \"x.mp4\"\n"],
        )
        stages = []

        async def cb(info):
            stages.append(info.get("stage"))

        await dl._stream(proc, cb)
        assert "download" in stages
        assert "process" in stages


class TestDownloadTimeout:
    async def test_timeout_kills_process_and_fails(self, dl, tmp_path, monkeypatch):
        import asyncio

        dl.settings.download_timeout = 0.01

        class BlockingStream:
            async def readline(self):
                await asyncio.sleep(10)  # never returns before the timeout
                return b""

        class FakeProc:
            def __init__(self):
                self.returncode = None
                self.killed = False
                self.stdout = BlockingStream()
                self.stderr = BlockingStream()

            def kill(self):
                self.killed = True
                self.returncode = -9

            async def wait(self):
                return self.returncode

        proc = FakeProc()

        async def fake_exec(*args, **kwargs):
            return proc

        monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

        result = await dl._run_download(["yt-dlp", "x"], tmp_path, "youtube")
        assert result.success is False
        assert "timed out" in result.error.lower()
        assert proc.killed is True


class TestGetInfo:
    async def test_includes_user_agent(self, dl, monkeypatch):
        captured = {}

        class FakeProc:
            returncode = 0

            async def communicate(self):
                return json.dumps({"title": "x"}).encode(), b""

        async def fake_exec(*args, **kwargs):
            captured["cmd"] = args
            return FakeProc()

        monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

        info = await dl.get_info("https://x")
        assert info == {"title": "x"}
        assert "--user-agent" in captured["cmd"]


class TestCookieFallback:
    async def test_retries_without_cookies_on_format_error(self, dl, tmp_path, monkeypatch):
        from src.downloaders.ytdlp import DownloadResult
        cookies = tmp_path / "c.txt"
        cookies.write_text("# Netscape HTTP Cookie File\n")
        dl.settings.cookies_file = str(cookies)
        dl.settings.use_browser_cookies = False

        calls = []

        async def fake_run(cmd, output_dir, platform, cb=None):
            calls.append(cmd)
            if len(calls) == 1:
                return DownloadResult(success=False, platform=platform,
                                      error="ERROR: Requested format is not available")
            return DownloadResult(success=True, output_path=tmp_path / "x.mp4", platform=platform)

        monkeypatch.setattr(dl, "_run_download", fake_run)
        res = await dl.download("https://youtu.be/x", tmp_path, MediaFormat.AUTO)
        assert res.success is True
        assert len(calls) == 2
        assert "--cookies" in calls[0]       # first try used cookies
        assert "--cookies" not in calls[1]   # retry dropped them

    async def test_cookie_retry_failure_surfaces_retry_error_not_original(
        self, dl, tmp_path, monkeypatch
    ):
        """If the no-cookies retry also fails, the *retry's* error should be
        reported — not the original cookie attempt's error. Otherwise a real
        DNS/connectivity failure surfaced by the retry gets masked by the
        stale "format not available" message and never reaches the
        connectivity/proxy fallback stages, which key off result.error."""
        from src.downloaders.ytdlp import DownloadResult
        cookies = tmp_path / "c.txt"
        cookies.write_text("# Netscape HTTP Cookie File\n")
        dl.settings.cookies_file = str(cookies)
        dl.settings.use_browser_cookies = False
        dl.settings.proxy_url = None

        calls = []

        async def fake_run(cmd, output_dir, platform, cb=None):
            calls.append(cmd)
            if len(calls) == 1:
                return DownloadResult(success=False, platform=platform,
                                      error="ERROR: Requested format is not available")
            return DownloadResult(
                success=False, platform=platform,
                error="ERROR: [download] Got error: [Errno -2] Name or service not known.",
            )

        monkeypatch.setattr(dl, "_run_download", fake_run)
        res = await dl.download("https://youtu.be/x", tmp_path, MediaFormat.AUTO)
        assert res.success is False
        assert "name or service not known" in res.error.lower()

    async def test_no_retry_without_cookies_configured(self, dl, tmp_path, monkeypatch):
        from src.downloaders.ytdlp import DownloadResult
        dl.settings.cookies_file = ""
        dl.settings.use_browser_cookies = False
        calls = []

        async def fake_run(cmd, output_dir, platform, cb=None):
            calls.append(cmd)
            return DownloadResult(success=False, platform=platform,
                                  error="ERROR: Requested format is not available")

        monkeypatch.setattr(dl, "_run_download", fake_run)
        res = await dl.download("https://youtu.be/x", tmp_path, MediaFormat.AUTO)
        assert res.success is False
        assert len(calls) == 1  # nothing to retry without


class TestProxyFallback:
    async def test_bare_retry_recovers_from_transient_connectivity_error(
        self, dl, tmp_path, monkeypatch
    ):
        """A handshake stall etc. often clears up immediately — no proxy needed."""
        from src.downloaders.ytdlp import DownloadResult
        dl.settings.proxy_url = None
        calls = []

        async def fake_run(cmd, output_dir, platform, cb=None):
            calls.append(cmd)
            if len(calls) == 1:
                return DownloadResult(
                    success=False, platform=platform,
                    error="_ssl.c:993: The handshake operation timed out",
                )
            return DownloadResult(success=True, output_path=tmp_path / "x.mp4", platform=platform)

        monkeypatch.setattr(dl, "_run_download", fake_run)
        res = await dl.download("https://example.com/x", tmp_path, MediaFormat.AUTO)
        assert res.success is True
        assert len(calls) == 2
        assert "--proxy" not in calls[1]

    async def test_retries_via_proxy_when_bare_retries_also_fail(self, dl, tmp_path, monkeypatch):
        from src.downloaders.ytdlp import DownloadResult
        dl.settings.proxy_url = "socks5h://127.0.0.1:9999"

        calls = []
        # initial attempt + _CONNECTIVITY_RETRY_ATTEMPTS bare retries all fail,
        # only the proxied attempt after that succeeds.
        bare_attempts = 1 + ytdlp_module._CONNECTIVITY_RETRY_ATTEMPTS

        async def fake_run(cmd, output_dir, platform, cb=None):
            calls.append(cmd)
            if len(calls) <= bare_attempts:
                return DownloadResult(
                    success=False, platform=platform,
                    error="_ssl.c:993: The handshake operation timed out",
                )
            return DownloadResult(success=True, output_path=tmp_path / "x.mp4", platform=platform)

        monkeypatch.setattr(dl, "_run_download", fake_run)
        res = await dl.download("https://example.com/x", tmp_path, MediaFormat.AUTO)
        assert res.success is True
        assert len(calls) == bare_attempts + 1
        for c in calls[:bare_attempts]:
            assert "--proxy" not in c
        assert "--proxy" in calls[-1]
        assert dl.settings.proxy_url in calls[-1]

    async def test_proxy_retry_drops_cookies_on_format_error(self, dl, tmp_path, monkeypatch):
        """Cookies captured on the normal path can get flagged when replayed
        from the proxy's exit IP, producing the same degraded "format not
        available" response as the non-proxied cookie fallback — the proxy
        branch should retry once more without cookies rather than giving up."""
        from src.downloaders.ytdlp import DownloadResult
        cookies = tmp_path / "c.txt"
        cookies.write_text("# Netscape HTTP Cookie File\n")
        dl.settings.cookies_file = str(cookies)
        dl.settings.use_browser_cookies = False
        dl.settings.proxy_url = "socks5h://127.0.0.1:9999"

        calls = []
        bare_attempts = 1 + ytdlp_module._CONNECTIVITY_RETRY_ATTEMPTS

        async def fake_run(cmd, output_dir, platform, cb=None):
            calls.append(cmd)
            if len(calls) <= bare_attempts:
                return DownloadResult(
                    success=False, platform=platform,
                    error="_ssl.c:993: The handshake operation timed out",
                )
            if len(calls) == bare_attempts + 1:
                return DownloadResult(
                    success=False, platform=platform,
                    error="ERROR: Requested format is not available",
                )
            return DownloadResult(success=True, output_path=tmp_path / "x.mp4", platform=platform)

        monkeypatch.setattr(dl, "_run_download", fake_run)
        res = await dl.download("https://example.com/x", tmp_path, MediaFormat.AUTO)
        assert res.success is True
        assert len(calls) == bare_attempts + 2
        assert "--proxy" in calls[-2] and "--cookies" in calls[-2]     # first proxied attempt, with cookies
        assert "--proxy" in calls[-1] and "--cookies" not in calls[-1]  # retry dropped them

    async def test_no_proxy_retry_without_proxy_configured(self, dl, tmp_path, monkeypatch):
        from src.downloaders.ytdlp import DownloadResult
        dl.settings.proxy_url = None
        calls = []

        async def fake_run(cmd, output_dir, platform, cb=None):
            calls.append(cmd)
            return DownloadResult(
                success=False, platform=platform,
                error="_ssl.c:993: The handshake operation timed out",
            )

        monkeypatch.setattr(dl, "_run_download", fake_run)
        res = await dl.download("https://example.com/x", tmp_path, MediaFormat.AUTO)
        assert res.success is False
        # initial attempt + all bare retries exhausted, no proxy to fall back to
        assert len(calls) == 1 + ytdlp_module._CONNECTIVITY_RETRY_ATTEMPTS

    async def test_no_retry_on_unrelated_error(self, dl, tmp_path, monkeypatch):
        from src.downloaders.ytdlp import DownloadResult
        dl.settings.proxy_url = "socks5h://127.0.0.1:9999"
        calls = []

        async def fake_run(cmd, output_dir, platform, cb=None):
            calls.append(cmd)
            return DownloadResult(success=False, platform=platform, error="ERROR: Video unavailable")

        monkeypatch.setattr(dl, "_run_download", fake_run)
        res = await dl.download("https://example.com/x", tmp_path, MediaFormat.AUTO)
        assert res.success is False
        assert len(calls) == 1  # unrelated failure shouldn't trigger any retry


class TestGetFormats:
    async def test_parses_info(self, dl, monkeypatch):
        async def fake_info(url):
            return {"formats": [
                {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a"},
                {"format_id": "137", "ext": "mp4", "vcodec": "avc1", "acodec": "none"},
            ]}
        monkeypatch.setattr(dl, "get_info", fake_info)
        formats = await dl.get_formats("https://x")
        types = {f["format_id"]: f["type"] for f in formats}
        assert types["140"] == "audio"
        assert types["137"] == "video"

    async def test_empty_when_no_info(self, dl, monkeypatch):
        async def fake_info(url):
            return None
        monkeypatch.setattr(dl, "get_info", fake_info)
        assert await dl.get_formats("https://x") == []
