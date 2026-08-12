"""Tests for services/mp4_maker.py pure helper functions."""

import subprocess
import threading
import types

import pytest
from services.mp4_maker import (
    clamp_frame_range,
    get_crf_value,
    get_output_filename,
    get_quality_description,
    _find_missing_frames,
    _scan_sequence_frames,
    _stderr_tail,
)


class TestGetCrfValue:
    def test_high_quality(self):
        assert get_crf_value(0) == 18

    def test_medium_quality(self):
        assert get_crf_value(1) == 23

    def test_low_quality(self):
        assert get_crf_value(2) == 28

    def test_invalid_index_defaults_to_medium(self):
        assert get_crf_value(99) == 23
        assert get_crf_value(-1) == 23


class TestGetOutputFilename:
    def test_standard(self):
        assert get_output_filename("main", "sh0010") == "sh0010_main.mp4"

    def test_empty_shot(self):
        assert get_output_filename("render", "") == "_render.mp4"

    def test_empty_render(self):
        assert get_output_filename("", "sh0010") == "sh0010_.mp4"


class TestGetQualityDescription:
    def test_high(self):
        assert get_quality_description(0) == "High (CRF 18)"

    def test_medium(self):
        assert get_quality_description(1) == "Medium (CRF 23)"

    def test_low(self):
        assert get_quality_description(2) == "Low (CRF 28)"

    def test_invalid_defaults_to_medium(self):
        assert get_quality_description(99) == "Medium (CRF 23)"


class TestCopyMp4ToGallery:
    def _copy(self, tmp_path, monkeypatch, user):
        """Run copy_mp4_to_gallery against a temp gallery base."""
        import services.mp4_maker as mp4_mod

        gallery_base = tmp_path / "gallery"
        gallery_base.mkdir()
        monkeypatch.setattr(
            "core.settings_manager.get_setting",
            lambda key: str(gallery_base) if key == "network_output_path" else None,
        )

        mp4_path = tmp_path / "sh0010_main.mp4"
        mp4_path.write_bytes(b"fake mp4")

        success, result = mp4_mod.copy_mp4_to_gallery(
            mp4_path=str(mp4_path),
            user=user,
            shot="sh0010",
            source_path="X:/renders/main.%04d.exr",
            frame_range=(1001, 1050),
            quality_index=0,
            burn_in_timecode=False,
        )
        return success, result, gallery_base

    def test_dotted_username_keeps_dot(self, tmp_path, monkeypatch):
        """Regression: 'christophe.leyder' MP4s landed in 'christophe_leyder'
        — a folder the gallery (which allows dots in usernames) never shows,
        while the log still reported success."""
        success, result, gallery_base = self._copy(tmp_path, monkeypatch, "christophe.leyder")
        assert success, result
        assert (gallery_base / "christophe.leyder" / "sh0010_main.mp4").is_file()
        assert not (gallery_base / "christophe_leyder").exists()

    def test_unsafe_username_is_sanitized(self, tmp_path, monkeypatch):
        """Traversal-style names still get sanitized to a safe folder."""
        success, result, gallery_base = self._copy(tmp_path, monkeypatch, "../evil")
        assert success, result
        # Must NOT escape the gallery base
        assert not (tmp_path / "evil").exists()
        assert (gallery_base / ".._evil" / "sh0010_main.mp4").is_file()

    def test_empty_username_uses_standalone(self, tmp_path, monkeypatch):
        success, result, gallery_base = self._copy(tmp_path, monkeypatch, "")
        assert success, result
        assert (gallery_base / "standalone" / "sh0010_main.mp4").is_file()


class TestClampFrameRange:
    def test_none_uses_sequence_range(self):
        assert clamp_frame_range(None, None, 1001, 1100) == (1001, 1100)

    def test_none_start_only(self):
        assert clamp_frame_range(None, 1050, 1001, 1100) == (1001, 1050)

    def test_none_end_only(self):
        assert clamp_frame_range(1010, None, 1001, 1100) == (1010, 1100)

    def test_subrange_inside_sequence_is_kept(self):
        assert clamp_frame_range(1010, 1020, 1001, 1100) == (1010, 1020)

    def test_start_below_sequence_is_clamped(self):
        assert clamp_frame_range(1, 1020, 1001, 1100) == (1001, 1020)

    def test_end_above_sequence_is_clamped(self):
        assert clamp_frame_range(1010, 9999, 1001, 1100) == (1010, 1100)

    def test_both_out_of_range(self):
        assert clamp_frame_range(-5, 9999, 1001, 1100) == (1001, 1100)

    def test_inverted_range_is_swapped(self):
        assert clamp_frame_range(1050, 1010, 1001, 1100) == (1010, 1050)

    def test_range_entirely_above_sequence(self):
        assert clamp_frame_range(5000, 6000, 1001, 1100) == (1100, 1100)

    def test_range_entirely_below_sequence(self):
        assert clamp_frame_range(1, 10, 1001, 1100) == (1001, 1001)

    def test_single_frame_sequence(self):
        assert clamp_frame_range(None, None, 7, 7) == (7, 7)

    def test_string_inputs_are_coerced(self):
        assert clamp_frame_range("1010", "1020", 1001, 1100) == (1010, 1020)


class TestScanSequenceFrames:
    def _make_seq(self, tmp_path, frames, ext="exr"):
        for frame in frames:
            (tmp_path / f"shot.{frame:04d}.{ext}").write_bytes(b"x")
        return str(tmp_path / f"shot.%04d.{ext}")

    def test_returns_sorted_frames(self, tmp_path):
        pattern = self._make_seq(tmp_path, [1003, 1001, 1002])
        assert _scan_sequence_frames(pattern) == [1001, 1002, 1003]

    def test_ignores_unrelated_files(self, tmp_path):
        pattern = self._make_seq(tmp_path, [1001, 1002])
        (tmp_path / "other.1005.exr").write_bytes(b"x")
        (tmp_path / "shot.1003.png").write_bytes(b"x")
        assert _scan_sequence_frames(pattern) == [1001, 1002]

    def test_no_frame_token_returns_none(self, tmp_path):
        assert _scan_sequence_frames(str(tmp_path / "shot.exr")) is None

    def test_missing_directory_returns_none(self, tmp_path):
        assert _scan_sequence_frames(str(tmp_path / "nope" / "shot.%04d.exr")) is None

    def test_empty_directory_returns_none(self, tmp_path):
        assert _scan_sequence_frames(str(tmp_path / "shot.%04d.exr")) is None


class TestFindMissingFrames:
    def test_uses_supplied_existing_set(self):
        assert _find_missing_frames("x.%04d.exr", 1, 5, existing_frames={1, 2, 5}) == [3, 4]

    def test_no_missing_with_supplied_set(self):
        assert _find_missing_frames("x.%04d.exr", 1, 3, existing_frames={1, 2, 3}) == []

    def test_falls_back_to_disk_check(self, tmp_path):
        for frame in (1, 3):
            (tmp_path / f"shot.{frame:04d}.exr").write_bytes(b"x")
        pattern = str(tmp_path / "shot.%04d.exr")
        assert _find_missing_frames(pattern, 1, 3) == [2]


class TestStderrTail:
    def test_empty(self):
        assert _stderr_tail("") == ""
        assert _stderr_tail(None) == ""

    def test_string_tail(self):
        text = "\n".join(f"line {i}" for i in range(30))
        assert _stderr_tail(text, max_lines=3) == "line 27\nline 28\nline 29"

    def test_iterable_of_raw_lines(self):
        lines = [f"line {i}\n" for i in range(10)]
        assert _stderr_tail(lines, max_lines=2) == "line 8\nline 9"


class _FakeResult:
    """Minimal stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stdout = ""
        self.stderr = stderr


class TestConvertExrToPngWithOiio:
    @pytest.fixture
    def oiio_env(self, tmp_path, monkeypatch):
        """Make OIIO look available and stub out get_ocio_config."""
        import services.mp4_maker as mp4_mod

        fake_oiio = tmp_path / "oiiotool.exe"
        fake_oiio.write_bytes(b"x")
        monkeypatch.setattr(mp4_mod, "OIIO_PATH", str(fake_oiio))
        monkeypatch.setattr(mp4_mod, "get_ocio_config", lambda: None)
        return mp4_mod

    def test_success_returns_true_and_empty_detail(self, oiio_env, tmp_path, monkeypatch):
        calls = []

        def fake_run(cmd, timeout=None):
            calls.append((cmd, timeout))
            return _FakeResult(0)

        monkeypatch.setattr(oiio_env, "run_command", fake_run)
        ok, detail = oiio_env.convert_exr_to_png_with_oiio(
            "X:/r/shot.%04d.exr", str(tmp_path), 1, 8
        )
        assert (ok, detail) == (True, "")
        assert len(calls) == 8
        # Fix #2: every per-frame oiiotool call carries a timeout
        assert all(timeout == oiio_env.OIIO_FRAME_TIMEOUT for _, timeout in calls)

    def test_runs_in_parallel(self, oiio_env, tmp_path, monkeypatch):
        """Frames must not be serialized one oiiotool at a time."""
        import time

        concurrent_now = 0
        peak = 0
        lock = threading.Lock()

        def fake_run(cmd, timeout=None):
            nonlocal concurrent_now, peak
            with lock:
                concurrent_now += 1
                peak = max(peak, concurrent_now)
            time.sleep(0.05)
            with lock:
                concurrent_now -= 1
            return _FakeResult(0)

        monkeypatch.setattr(oiio_env, "run_command", fake_run)
        ok, _ = oiio_env.convert_exr_to_png_with_oiio(
            "X:/r/shot.%04d.exr", str(tmp_path), 1, 12, max_workers=4
        )
        assert ok
        assert peak > 1

    def test_progress_is_monotonic_and_complete(self, oiio_env, tmp_path, monkeypatch):
        monkeypatch.setattr(
            oiio_env, "run_command", lambda cmd, timeout=None: _FakeResult(0)
        )
        seen = []
        lock = threading.Lock()

        def progress(pct, msg):
            with lock:
                seen.append(pct)

        ok, _ = oiio_env.convert_exr_to_png_with_oiio(
            "X:/r/shot.%04d.exr", str(tmp_path), 1, 10, progress
        )
        assert ok
        assert len(seen) == 10
        assert seen == sorted(seen)  # thread-safe counter => never goes backwards
        assert min(seen) >= 10 and max(seen) <= 50

    def test_failure_reports_frame_and_stderr_tail(self, oiio_env, tmp_path, monkeypatch):
        def fake_run(cmd, timeout=None):
            # cmd[1] is the input file; fail only on frame 0003
            if "0003" in cmd[1]:
                return _FakeResult(1, "boom line A\nboom line B")
            return _FakeResult(0)

        monkeypatch.setattr(oiio_env, "run_command", fake_run)
        ok, detail = oiio_env.convert_exr_to_png_with_oiio(
            "X:/r/shot.%04d.exr", str(tmp_path), 1, 6
        )
        assert ok is False
        assert "frame 3" in detail
        assert "boom line B" in detail

    def test_timeout_is_a_frame_failure(self, oiio_env, tmp_path, monkeypatch):
        def fake_run(cmd, timeout=None):
            raise subprocess.TimeoutExpired(cmd, timeout or 0)

        monkeypatch.setattr(oiio_env, "run_command", fake_run)
        ok, detail = oiio_env.convert_exr_to_png_with_oiio(
            "X:/r/shot.%04d.exr", str(tmp_path), 1, 2
        )
        assert ok is False
        assert "timed out" in detail

    def test_missing_frame_token_returns_detail(self, oiio_env, tmp_path):
        ok, detail = oiio_env.convert_exr_to_png_with_oiio(
            "X:/r/shot.exr", str(tmp_path), 1, 2
        )
        assert ok is False
        assert "frame token" in detail

    def test_cancel_raises(self, oiio_env, tmp_path, monkeypatch):
        from core.error_handling import CancellationError

        monkeypatch.setattr(
            oiio_env, "run_command", lambda cmd, timeout=None: _FakeResult(0)
        )
        cancel = threading.Event()
        cancel.set()
        with pytest.raises(CancellationError):
            oiio_env.convert_exr_to_png_with_oiio(
                "X:/r/shot.%04d.exr", str(tmp_path), 1, 20, cancel_event=cancel
            )


class _FakeProcess:
    """Minimal stand-in for the FFmpeg Popen object."""

    def __init__(self, returncode=0, stderr_lines=()):
        self.returncode = returncode
        self.stderr = iter(list(stderr_lines))
        self.killed = False
        self.terminated = False

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class TestGenerateMp4:
    @pytest.fixture
    def mp4_env(self, tmp_path, monkeypatch):
        """PNG sequence 1001-1010 plus a stubbed FFmpeg; yields (module, ctx)."""
        import os as _os

        import services.mp4_maker as mp4_mod

        seq_dir = tmp_path / "seq"
        seq_dir.mkdir()
        for frame in range(1001, 1011):
            (seq_dir / f"shot.{frame:04d}.png").write_bytes(b"x")

        ctx = types.SimpleNamespace(
            pattern=str(seq_dir / "shot.%04d.png"),
            output=str(tmp_path / "out" / "shot.mp4"),
            seq_dir=seq_dir,
            cmd=None,
            process=None,
            write_output=True,
            output_bytes=b"mp4 data",
        )

        monkeypatch.setattr(mp4_mod, "FFMPEG_PATH", "ffmpeg.exe")

        def fake_start_process(cmd, **kwargs):
            ctx.cmd = cmd
            if ctx.process is None:
                ctx.process = _FakeProcess(0, ["frame=  5 fps=10\n"])
            if ctx.write_output:
                _os.makedirs(_os.path.dirname(ctx.output), exist_ok=True)
                with open(ctx.output, "wb") as fh:
                    fh.write(ctx.output_bytes)
            return ctx.process

        monkeypatch.setattr(mp4_mod, "start_process", fake_start_process)
        return mp4_mod, ctx

    def test_success_returns_true_and_empty_detail(self, mp4_env):
        mp4_mod, ctx = mp4_env
        assert mp4_mod.generate_mp4(ctx.pattern, ctx.output) == (True, "")

    def test_defaults_to_full_detected_range(self, mp4_env):
        mp4_mod, ctx = mp4_env
        ok, _ = mp4_mod.generate_mp4(ctx.pattern, ctx.output)
        assert ok
        assert ctx.cmd[ctx.cmd.index("-start_number") + 1] == "1001"
        assert ctx.cmd[ctx.cmd.index("-frames:v") + 1] == "10"

    def test_subrange_is_applied_to_ffmpeg(self, mp4_env):
        mp4_mod, ctx = mp4_env
        ok, _ = mp4_mod.generate_mp4(
            ctx.pattern, ctx.output, start_frame=1003, end_frame=1006
        )
        assert ok
        assert ctx.cmd[ctx.cmd.index("-start_number") + 1] == "1003"
        assert ctx.cmd[ctx.cmd.index("-frames:v") + 1] == "4"

    def test_subrange_is_clamped_to_sequence(self, mp4_env):
        mp4_mod, ctx = mp4_env
        ok, _ = mp4_mod.generate_mp4(
            ctx.pattern, ctx.output, start_frame=1, end_frame=99999
        )
        assert ok
        assert ctx.cmd[ctx.cmd.index("-start_number") + 1] == "1001"
        assert ctx.cmd[ctx.cmd.index("-frames:v") + 1] == "10"

    def test_missing_frames_reported(self, mp4_env):
        mp4_mod, ctx = mp4_env
        (ctx.seq_dir / "shot.1005.png").unlink()
        ok, detail = mp4_mod.generate_mp4(
            ctx.pattern, ctx.output, start_frame=1001, end_frame=1010
        )
        assert ok is False
        assert "missing" in detail.lower()
        assert "1005" in detail
        # Bailed out before ever launching FFmpeg
        assert ctx.cmd is None

    def test_ffmpeg_nonzero_exit_includes_stderr_tail(self, mp4_env):
        mp4_mod, ctx = mp4_env
        ctx.process = _FakeProcess(
            1, [f"noise {i}\n" for i in range(50)] + ["Invalid data found\n"]
        )
        ctx.write_output = False
        ok, detail = mp4_mod.generate_mp4(ctx.pattern, ctx.output)
        assert ok is False
        assert "exit code 1" in detail
        assert "Invalid data found" in detail
        assert "noise 0" not in detail  # only the tail is included

    def test_missing_output_file_reported(self, mp4_env):
        mp4_mod, ctx = mp4_env
        ctx.write_output = False
        ok, detail = mp4_mod.generate_mp4(ctx.pattern, ctx.output)
        assert ok is False
        assert "no output file" in detail.lower()

    def test_zero_size_output_reported(self, mp4_env):
        mp4_mod, ctx = mp4_env
        ctx.output_bytes = b""
        ok, detail = mp4_mod.generate_mp4(ctx.pattern, ctx.output)
        assert ok is False
        assert "zero-byte" in detail

    def test_no_ffmpeg_returns_detail(self, mp4_env, monkeypatch):
        mp4_mod, ctx = mp4_env
        monkeypatch.setattr(mp4_mod, "FFMPEG_PATH", "")
        ok, detail = mp4_mod.generate_mp4(ctx.pattern, ctx.output)
        assert ok is False
        assert "FFmpeg" in detail

    def test_unresolvable_range_returns_detail(self, mp4_env, tmp_path):
        mp4_mod, ctx = mp4_env
        empty = tmp_path / "empty"
        empty.mkdir()
        ok, detail = mp4_mod.generate_mp4(str(empty / "shot.%04d.png"), ctx.output)
        assert ok is False
        assert "frame range" in detail

    def test_cancel_during_encode_raises(self, mp4_env):
        from core.error_handling import CancellationError

        mp4_mod, ctx = mp4_env
        cancel = threading.Event()
        hung = _FakeProcess(0, [])

        def _wait(timeout=None):
            cancel.set()
            raise subprocess.TimeoutExpired("ffmpeg", timeout or 0)

        hung.wait = _wait
        ctx.process = hung
        ctx.write_output = False

        with pytest.raises(CancellationError):
            mp4_mod.generate_mp4(ctx.pattern, ctx.output, cancel_event=cancel)
        assert hung.terminated or hung.killed

    def test_ffmpeg_deadline_returns_timeout_detail(self, mp4_env, monkeypatch):
        mp4_mod, ctx = mp4_env
        monkeypatch.setattr(mp4_mod, "FFMPEG_MIN_TIMEOUT", 0)
        monkeypatch.setattr(mp4_mod, "FFMPEG_PER_FRAME_TIMEOUT", 0)

        hung = _FakeProcess(0, ["stuck on frame 3\n"])

        def _wait(timeout=None):
            if hung.killed:
                return 0
            raise subprocess.TimeoutExpired("ffmpeg", timeout or 0)

        hung.wait = _wait
        ctx.process = hung
        ctx.write_output = False

        ok, detail = mp4_mod.generate_mp4(ctx.pattern, ctx.output)
        assert ok is False
        assert "timed out" in detail
        assert hung.killed
        assert "stuck on frame 3" in detail
