"""Unit tests for the post-run status classifier."""

from __future__ import annotations

from app.orchestrator.pipeline import classify_run


class TestClassifyRun:
    def test_clean_exit_is_success(self):
        out = classify_run(
            returncode=0,
            stats_complete_ranks=64,
            total_npus=64,
            crash_pattern_seen=False,
        )
        assert out.status == "succeeded"
        assert out.ok is True
        assert out.warning is None

    def test_sigterm_is_cancel(self):
        # Real user cancellation via POST /runs/{id}/cancel sends SIGTERM.
        out = classify_run(
            returncode=-15,
            stats_complete_ranks=10,
            total_npus=64,
            crash_pattern_seen=False,
        )
        assert out.status == "cancelled"
        assert out.ok is False

    def test_sigabrt_after_full_stats_is_teardown_crash(self):
        # Astra-sim finished every NPU's stats, then glibc aborted during
        # destruction. Results on disk are valid.
        out = classify_run(
            returncode=-6,
            stats_complete_ranks=64,
            total_npus=64,
            crash_pattern_seen=True,
        )
        assert out.status == "succeeded"
        assert out.ok is True
        assert out.warning is not None
        assert "teardown" in out.warning.lower()

    def test_sigabrt_before_stats_is_failure(self):
        # Genuine crash mid-simulation before any stats were flushed.
        out = classify_run(
            returncode=-6,
            stats_complete_ranks=0,
            total_npus=64,
            crash_pattern_seen=True,
        )
        assert out.status == "failed"
        assert out.ok is False
        assert out.warning is None

    def test_sigabrt_partial_stats_is_failure(self):
        # Crashed midway — some ranks finished, but not all.
        out = classify_run(
            returncode=-6,
            stats_complete_ranks=40,
            total_npus=64,
            crash_pattern_seen=True,
        )
        assert out.status == "failed"

    def test_nonzero_returncode_without_signal_is_failure(self):
        out = classify_run(
            returncode=1,
            stats_complete_ranks=64,
            total_npus=64,
            crash_pattern_seen=False,
        )
        assert out.status == "failed"

    def test_other_signal_is_failure_not_cancel(self):
        # Historically any negative returncode was marked 'cancelled', which
        # hid real crashes (SIGABRT, SIGSEGV). Only SIGTERM is cancel now.
        out = classify_run(
            returncode=-11,  # SIGSEGV
            stats_complete_ranks=0,
            total_npus=64,
            crash_pattern_seen=False,
        )
        assert out.status == "failed"

    def test_abort_without_pattern_not_classified_as_teardown_crash(self):
        # Without a detected crash-pattern in the logs, we refuse to
        # optimistically salvage the run even if rank counts match.
        out = classify_run(
            returncode=-6,
            stats_complete_ranks=64,
            total_npus=64,
            crash_pattern_seen=False,
        )
        assert out.status == "failed"

    def test_zero_total_npus_refuses_teardown_salvage(self):
        # If the bundle claimed zero NPUs, we cannot prove completion.
        out = classify_run(
            returncode=-6,
            stats_complete_ranks=0,
            total_npus=0,
            crash_pattern_seen=True,
        )
        assert out.status == "failed"

    def test_none_returncode_maps_to_failure(self):
        # If stream_run never yielded a parseable 'done' event, the caller
        # may pass returncode=None. We must not silently succeed — map to
        # failure so the operator sees that something is off.
        out = classify_run(
            returncode=None,
            stats_complete_ranks=64,
            total_npus=64,
            crash_pattern_seen=True,
        )
        assert out.status == "failed"
        assert out.ok is False
        assert out.warning is None
