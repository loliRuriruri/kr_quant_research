import pandas as pd
from kr_quant.sector.ranking import _pct_rank, _state, rank_sectors


def test_sector_state_and_pct_rank():
    ranks = _pct_rank([10.0, 20.0, 50.0])
    assert len(ranks) == 3
    assert ranks[0] < ranks[1] < ranks[2]

    assert _state(85.0, 1.0) == "LEADING"
    assert _state(70.0, 4.0) == "IMPROVING"
    assert _state(50.0, 0.0) == "NEUTRAL"
    assert _state(30.0, -6.0) == "LAGGING"


def test_sector_ranking_output(tmp_path):
    output = tmp_path / "output"
    output.mkdir()

    class S:
        output_dir = output
        root = tmp_path

    res = rank_sectors(S())
    assert res["used_in_quant"] is False
    assert "rows" in res
