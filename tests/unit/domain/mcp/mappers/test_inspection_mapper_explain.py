"""explain_plan / enrich_explain_text 单元测试。"""

from dm_mcp.domain.mcp.mappers import inspection_mapper as mapper


def test_enrich_explain_text_adds_mem_used():
    text = "3       #HASH2 INNER JOIN: [1, 856, 325]; KEY_NUM(1)"
    nodes = [{"SEQ_NO": 3, "MEM_USED": 19584, "DISK_USED": 0}]
    out = mapper.enrich_explain_text(text, nodes)
    assert "MEM_USED(19584KB)" in out
    assert "KEY_NUM(1)" in out


def test_merge_runtime_statistics_prefers_stat_history():
    stats = mapper.merge_runtime_statistics(
        None,
        {"LOGICAL_READS": 1, "EXEC_TIME_MS": 0.5},
        {
            "LOGICAL_READS": 33,
            "BYTES_SENT_TO_CLIENT": 2483,
            "DATA_PAGES_CHANGED": 0,
            "EXEC_TIME_MS": 2,
        },
    )
    assert stats["logical_reads"] == 33
    assert stats["bytes_sent_to_client"] == 2483


def test_explain_plan_returns_origin_plan_and_statistics():
    result = mapper.explain_plan(
        explain_text="1   #NSET2: [1, 1, 0]",
        statistics={"logical_reads": 10, "physical_reads": 2},
        exec_id=100,
        et_rows=[{"SEQ": 1, "OP": "NSET2", "TIME(US)": 10, "PERCENT": "100%", "RANK": 1}],
        node_rows=[{"SEQ_NO": 1, "MEM_USED": 1024, "DISK_USED": 0, "TIME_USED": 10}],
    )
    assert result["origin_plan"] == "1   #NSET2: [1, 1, 0]"
    assert result["exec_id"] == 100
    assert result["statistics"]["statement"]["logical_reads"] == 10
    assert result["statistics"]["statement"]["physical_reads"] == 2
    op = result["statistics"]["operators"]["1"]
    assert op["memory_kb"] == 1024
    assert op["time_us"] == 10
    assert "logical_reads" not in op


def test_merge_runtime_statistics_preserves_zero_physical_reads():
    stats = mapper.merge_runtime_statistics(
        {"LOGICAL_READS": 104, "PHYSICAL_READS": 0},
        None,
        None,
    )
    assert stats["logical_reads"] == 104
    assert stats["physical_reads"] == 0


def test_explain_plan_operator_outputs_zero_disk_kb():
    result = mapper.explain_plan(
        explain_text="plan",
        statistics={"logical_reads": 10, "physical_reads": 0},
        exec_id=1,
        node_rows=[{"SEQ_NO": 5, "MEM_USED": 19584, "DISK_USED": 0}],
        et_rows=[{"SEQ": 5, "OP": "HI3", "MEM_USED(KB)": 19584}],
    )
    op = result["statistics"]["operators"]["5"]
    assert op["memory_kb"] == 19584
    assert op["disk_kb"] == 0
    assert result["statistics"]["statement"]["physical_reads"] == 0


def test_group_ini_params_by_operator():
    plan = (
        "3       #SORT3: [2, 1, 202]\n"
        "5           #HASH2 INNER JOIN: [1, 1, 202]\n"
    )
    grouped = mapper.group_ini_params_by_operator(
        plan,
        [
            {"NAME": "HJ_BUF_SIZE", "VALUE": "500"},
            {"NAME": "SORT_BUF_SIZE", "VALUE": "200"},
            {"NAME": "HAGR_HASH_SIZE", "VALUE": "100000"},
        ],
        et_rows=[{"SEQ": 5, "OP": "HI3"}],
    )
    assert grouped["SORT3"]["SORT_BUF_SIZE"] == "200"
    assert grouped["HASH2 INNER JOIN"]["HJ_BUF_SIZE"] == "500"
    assert grouped["HI3"]["HJ_BUF_SIZE"] == "500"
    assert "HAGR_HASH_SIZE" not in grouped["SORT3"]


def test_explain_plan_merges_ini_into_operator_by_seq():
    result = mapper.explain_plan(
        explain_text="3       #SORT3: [1, 1, 0]\n5           #HI3: [1, 1, 0]",
        statistics={"logical_reads": 1},
        session_parameter_rows=[
            {"NAME": "SORT_BUF_SIZE", "VALUE": "200"},
            {"NAME": "HJ_BUF_SIZE", "VALUE": "500"},
        ],
        node_rows=[
            {"SEQ_NO": 3, "MEM_USED": 2048, "DISK_USED": 0},
            {"SEQ_NO": 5, "MEM_USED": 1024, "DISK_USED": 0},
        ],
        et_rows=[
            {"SEQ": 3, "OP": "SORT3", "TIME(US)": 50, "PERCENT": "10%", "RANK": 2},
            {"SEQ": 5, "OP": "HI3", "TIME(US)": 380, "PERCENT": "38%", "RANK": 1},
        ],
    )
    ops = result["statistics"]["operators"]
    assert ops["3"]["ini"]["SORT_BUF_SIZE"] == "200"
    assert ops["3"]["time_us"] == 50
    assert ops["5"]["ini"]["HJ_BUF_SIZE"] == "500"
    assert ops["5"]["rank"] == 1
    assert "ini_params" not in result["statistics"]


def test_explain_plan_includes_et_operators_with_time_only():
    result = mapper.explain_plan(
        explain_text="plan",
        statistics={"logical_reads": 10},
        exec_id=1,
        et_rows=[
            {"SEQ": 1, "OP": "NSET2", "TIME(US)": 10, "PERCENT": "100%", "RANK": 1},
            {"SEQ": 2, "OP": "SORT3", "TIME(US)": 5, "MEM_USED(KB)": 2048},
        ],
        node_rows=[
            {"SEQ_NO": 1, "MEM_USED": 0, "DISK_USED": 0, "N_ENTER": 3},
            {"SEQ_NO": 2, "MEM_USED": 2048, "DISK_USED": 0, "N_ENTER": 5},
        ],
    )
    ops = result["statistics"]["operators"]
    assert len(ops) == 2
    assert ops["1"]["time_us"] == 10
    assert ops["1"]["n_enter"] == 3
    assert ops["2"]["memory_kb"] == 2048
    assert ops["2"]["n_enter"] == 5


def test_operator_outputs_n_enter_zero():
    result = mapper.explain_plan(
        explain_text="8             #CSCN2: [1, 4703, 54]",
        statistics={"logical_reads": 1},
        et_rows=[
            {
                "SEQ": 8,
                "OP": "CSCN2",
                "TIME(US)": 244,
                "PERCENT": "36.53%",
                "RANK": 1,
                "N_ENTER": 0,
            }
        ],
        node_rows=[{"SEQ_NO": 8, "MEM_USED": 0, "DISK_USED": 0, "N_ENTER": 0}],
    )
    op = result["statistics"]["operators"]["8"]
    assert op["n_enter"] == 0
    assert op["time_us"] == 244


def test_build_operators_summary_merges_et_and_node():
    ops = mapper.build_operators_summary(
        [{"SEQ_NO": 8, "MEM_USED": 0, "DISK_USED": 0, "TIME_USED": 380, "TYPE$": 200}],
        [
            {
                "OP": "CSCN2",
                "SEQ": 8,
                "TIME(US)": 380,
                "PERCENT": "38.19%",
                "RANK": 1,
                "MEM_USED(KB)": 0,
            }
        ],
    )
    assert ops[0]["seq"] == 8
    assert ops[0]["operator"] == "CSCN2"
    assert ops[0]["time_us"] == 380


def test_explain_plan_et_only_without_node_history():
    """ET 成功时无需 V$SQL_NODE_HISTORY。"""
    result = mapper.explain_plan(
        explain_text="5           #HI3: [1, 1, 202]",
        statistics={"logical_reads": 1},
        et_rows=[
            {
                "SEQ": 5,
                "OP": "HI3",
                "TIME(US)": 109,
                "PERCENT": "16%",
                "RANK": 1,
                "N_ENTER": 12,
                "MEM_USED(KB)": 19584,
                "DISK_USED(KB)": 0,
                "HASH_USED_CELLS": 4,
                "HASH_CONFLICT": 0,
                "HASH_SAME_VALUE": 2,
            }
        ],
        node_rows=None,
    )
    op = result["statistics"]["operators"]["5"]
    assert op["memory_kb"] == 19584
    assert op["hash_used_cells"] == 4
    assert op["time_us"] == 109


def test_operator_outputs_hash_statistics():
    result = mapper.explain_plan(
        explain_text="5           #HI3: [1, 1, 202]",
        statistics={"logical_reads": 1},
        et_rows=[
            {
                "SEQ": 5,
                "OP": "HI3",
                "TIME(US)": 109,
                "PERCENT": "16%",
                "RANK": 1,
                "N_ENTER": 12,
                "HASH_USED_CELLS": 4,
                "HASH_CONFLICT": 0,
                "DHASH3_USED_CELLS": 0,
                "DHASH3_CONFLICT": 0,
                "HASH_SAME_VALUE": 2,
            }
        ],
        node_rows=[
            {
                "SEQ_NO": 5,
                "MEM_USED": 19584,
                "DISK_USED": 0,
                "N_ENTER": 12,
                "HASH_USED_CELLS": 4,
                "HASH_CONFLICT": 0,
            }
        ],
    )
    op = result["statistics"]["operators"]["5"]
    assert op["hash_used_cells"] == 4
    assert op["hash_conflict"] == 0
    assert op["hash_same_value"] == 2
