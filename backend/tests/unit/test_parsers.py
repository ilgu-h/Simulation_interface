"""Unit tests for log + .et parsers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers.astra_logs import NpuStats, parse_log_file, to_dataframe, write_parquet

SAMPLE_LOG = """\
[2026-04-15 18:25:12.340] [system::topology] [info] ring info
[2026-04-15 18:25:12.341] [workload] [info] sys[0] finished, 43000 cycles, exposed communication 43000 cycles.
[2026-04-15 18:25:12.341] [statistics] [info] sys[0], Wall time: 43000
[2026-04-15 18:25:12.341] [statistics] [info] sys[0], Comm time: 43000
[2026-04-15 18:25:12.341] [workload] [info] sys[1] finished, 43000 cycles, exposed communication 43000 cycles.
[2026-04-15 18:25:12.341] [statistics] [info] sys[1], Wall time: 43000
[2026-04-15 18:25:12.341] [statistics] [info] sys[1], Comm time: 43000
"""


class TestAstraLogParser:
    def test_parse_sample_log(self, tmp_path):
        f = tmp_path / "log.log"
        f.write_text(SAMPLE_LOG)
        stats = parse_log_file(f)
        assert len(stats) == 2
        assert stats[0].npu_id == 0
        assert stats[0].wall_cycles == 43000
        assert stats[0].comm_cycles == 43000
        assert stats[0].compute_cycles == 0
        assert stats[0].comm_fraction == 1.0

    def test_empty_log(self, tmp_path):
        f = tmp_path / "empty.log"
        f.write_text("")
        assert parse_log_file(f) == []

    def test_missing_file(self, tmp_path):
        assert parse_log_file(tmp_path / "nope.log") == []

    def test_to_dataframe(self):
        stats = [
            NpuStats(npu_id=0, wall_cycles=100, comm_cycles=60, exposed_comm_cycles=60),
            NpuStats(npu_id=1, wall_cycles=100, comm_cycles=40, exposed_comm_cycles=40),
        ]
        df = to_dataframe(stats)
        assert list(df.columns) == [
            "npu_id",
            "wall_cycles",
            "comm_cycles",
            "compute_cycles",
            "exposed_comm_cycles",
            "comm_fraction",
        ]
        assert df.iloc[0]["compute_cycles"] == 40
        assert df.iloc[1]["comm_fraction"] == pytest.approx(0.4)

    def test_write_parquet(self, tmp_path):
        stats = [NpuStats(npu_id=0, wall_cycles=10, comm_cycles=5, exposed_comm_cycles=5)]
        out = write_parquet(stats, tmp_path / "stats.parquet")
        assert out.exists()
        import pandas as pd

        df = pd.read_parquet(out)
        assert len(df) == 1
        assert df.iloc[0]["wall_cycles"] == 10


class TestEtTraceParser:
    def test_parse_microbenchmark(self):
        et_dir = Path("frameworks/astra-sim/examples/workload/microbenchmarks/all_reduce/4npus_1MB")
        if not et_dir.exists():
            pytest.skip("astra-sim submodule not checked out")
        from app.parsers.et_traces import aggregate_by_type, parse_run_traces

        ops = parse_run_traces(et_dir)
        assert len(ops) == 4
        assert all(o.comm_type == "ALL_REDUCE" for o in ops)
        agg = aggregate_by_type(ops)
        assert agg.iloc[0]["count"] == 4
        assert agg.iloc[0]["total_bytes"] == 4 * 1048576
