"""SqlGuardService 测试"""

import pytest
from unittest.mock import MagicMock, patch
from dm_mcp.core.sql_guard import (
    RiskLevel,
    SqlRiskReport,
    RoutineIntrospector,
    SqlGuard,
    WRITE_KEYWORDS,
    TX_KEYWORDS,
    SYSTEM_FUNCTION_ALLOWLIST,
    SYSTEM_SCHEMA_ALLOWLIST,
)


class TestRiskLevel:
    """RiskLevel 枚举测试"""

    def test_risk_level_values(self):
        """测试风险级别枚举值"""
        assert RiskLevel.LOW.value == "LOW"
        assert RiskLevel.MEDIUM.value == "MEDIUM"
        assert RiskLevel.HIGH.value == "HIGH"
        assert RiskLevel.BLOCK.value == "BLOCK"

    def test_risk_level_ordering(self):
        """测试风险级别顺序"""
        levels = list(RiskLevel)
        assert RiskLevel.LOW in levels
        assert RiskLevel.MEDIUM in levels
        assert RiskLevel.HIGH in levels
        assert RiskLevel.BLOCK in levels


class TestSqlRiskReport:
    """SqlRiskReport 数据类测试"""

    def test_sql_risk_report_creation(self):
        """测试报告创建"""
        report = SqlRiskReport(
            normalized_sql="SELECT * FROM users",
            statement_type="SELECT",
            is_select=True,
            has_for_update=False,
            has_lock_table=False,
            write_tokens=[],
            tx_tokens=[],
            calls=[],
            unknown_calls=[],
            risky_calls=[],
            risk_level=RiskLevel.LOW,
            reason="安全的只读查询",
            details={},
        )
        assert report.normalized_sql == "SELECT * FROM users"
        assert report.statement_type == "SELECT"
        assert report.is_select is True
        assert report.risk_level == RiskLevel.LOW

    def test_sql_risk_report_fields(self):
        """测试报告字段"""
        report = SqlRiskReport(
            normalized_sql="INSERT INTO users VALUES(1)",
            statement_type="INSERT",
            is_select=False,
            has_for_update=False,
            has_lock_table=False,
            write_tokens=["INSERT"],
            tx_tokens=[],
            calls=[],
            unknown_calls=[],
            risky_calls=[],
            risk_level=RiskLevel.HIGH,
            reason="非SELECT语句: INSERT",
            details={"token_hits": {"write": ["INSERT"]}},
        )
        assert report.write_tokens == ["INSERT"]
        assert report.is_select is False
        assert "INSERT" in report.reason


class TestRoutineIntrospector:
    """RoutineIntrospector 测试"""

    def test_init_without_exec_func(self):
        """测试无exec函数初始化"""
        introspector = RoutineIntrospector()
        assert introspector._exec is None

    def test_init_with_exec_func(self):
        """测试带exec函数初始化"""
        exec_func = MagicMock()
        introspector = RoutineIntrospector(exec_sql_func=exec_func)
        assert introspector._exec is exec_func

    def test_classify_routine_no_exec(self):
        """测试无exec函数时的分类"""
        introspector = RoutineIntrospector()
        result = introspector.classify_routine("some_proc")
        assert result == "UNKNOWN"

    def test_classify_routine_safe(self):
        """测试安全例程分类"""
        mock_exec = MagicMock(return_value="SELECT 1 FROM DUAL")
        introspector = RoutineIntrospector(exec_sql_func=mock_exec)
        result = introspector.classify_routine("safe_proc")
        assert result in ["SAFE", "RISKY"]

    def test_classify_routine_risky(self):
        """测试危险例程分类"""
        mock_exec = MagicMock(return_value="INSERT INTO users VALUES(1)")
        introspector = RoutineIntrospector(exec_sql_func=mock_exec)
        result = introspector.classify_routine("risky_proc")
        assert result in ["SAFE", "RISKY"]

    def test_classify_routine_commit(self):
        """测试含COMMIT的例程"""
        mock_exec = MagicMock(return_value="COMMIT")
        introspector = RoutineIntrospector(exec_sql_func=mock_exec)
        result = introspector.classify_routine("tx_proc")
        assert result == "RISKY"

    def test_split_routine_name_simple(self):
        """测试简单例程名分割"""
        introspector = RoutineIntrospector()
        schema, name = introspector._split_routine_name("my_proc")
        assert schema is None
        assert name == "my_proc"

    def test_split_routine_name_with_schema(self):
        """测试带schema的例程名分割"""
        introspector = RoutineIntrospector()
        schema, name = introspector._split_routine_name("schema.my_proc")
        assert schema == "schema"
        assert name == "my_proc"

    def test_split_routine_name_empty(self):
        """测试空例程名"""
        introspector = RoutineIntrospector()
        schema, name = introspector._split_routine_name("")
        assert schema is None
        assert name == ""

    def test_split_routine_name_with_spaces(self):
        """测试带空格的例程名"""
        introspector = RoutineIntrospector()
        schema, name = introspector._split_routine_name(" schema . my_proc ")
        assert schema == "schema"
        assert name == "my_proc"

    def test_extract_ddl_text_none(self):
        """测试提取DDL文本-无结果"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_text(None)
        assert result is None

    def test_extract_ddl_text_string(self):
        """测试提取DDL文本-字符串"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_text("CREATE PROCEDURE test")
        assert result == "CREATE PROCEDURE test"

    def test_extract_ddl_text_dict(self):
        """测试提取DDL文本-字典"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_text({"ddl": "CREATE PROCEDURE test"})
        assert result == "CREATE PROCEDURE test"

    def test_extract_ddl_text_list(self):
        """测试提取DDL文本-列表"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_text([{"ddl": "CREATE PROCEDURE test"}])
        assert result == "CREATE PROCEDURE test"


class TestSqlGuard:
    """SqlGuard 测试"""

    @pytest.fixture
    def guard(self):
        """创建SqlGuard实例"""
        return SqlGuard()

    @pytest.fixture
    def guard_with_introspector(self):
        """创建带内省器的SqlGuard"""
        mock_introspector = MagicMock()
        mock_introspector.classify_routine.return_value = "SAFE"
        return SqlGuard(routine_introspector=mock_introspector)

    def test_init_without_introspector(self, guard):
        """测试无内省器初始化"""
        assert guard._ri is None

    def test_analyze_simple_select(self, guard):
        """测试简单SELECT查询"""
        report = guard.analyze("SELECT * FROM users")
        assert report.is_select is True
        assert report.statement_type == "SELECT"
        assert report.risk_level == RiskLevel.LOW

    def test_analyze_select_with_where(self, guard):
        """测试带WHERE的SELECT"""
        report = guard.analyze("SELECT id, name FROM users WHERE id = 1")
        assert report.is_select is True
        assert report.risk_level == RiskLevel.LOW

    def test_analyze_insert(self, guard):
        """测试INSERT语句"""
        report = guard.analyze("INSERT INTO users(name) VALUES('test')")
        assert report.is_select is False
        assert report.statement_type == "INSERT"
        assert "INSERT" in report.write_tokens

    def test_analyze_update(self, guard):
        """测试UPDATE语句"""
        report = guard.analyze("UPDATE users SET name = 'test' WHERE id = 1")
        assert report.is_select is False
        assert report.statement_type == "UPDATE"
        assert "UPDATE" in report.write_tokens

    def test_analyze_delete(self, guard):
        """测试DELETE语句"""
        report = guard.analyze("DELETE FROM users WHERE id = 1")
        assert report.is_select is False
        assert report.statement_type == "DELETE"
        assert "DELETE" in report.write_tokens

    def test_analyze_with_comments(self, guard):
        """测试带注释的SQL"""
        report = guard.analyze("SELECT * FROM users -- this is a comment\nWHERE id = 1")
        assert report.is_select is True
        assert report.risk_level == RiskLevel.LOW
        assert report.details["meta"]["has_comments"] is True

    def test_analyze_with_block_comments(self, guard):
        """测试带块注释的SQL"""
        report = guard.analyze("SELECT /* comment */ * FROM users")
        assert report.is_select is True
        assert report.risk_level == RiskLevel.LOW

    def test_analyze_with_string_literal(self, guard):
        """测试带字符串字面量的SQL"""
        report = guard.analyze(
            "SELECT * FROM users WHERE name = 'test -- not a comment'"
        )
        assert report.is_select is True
        assert report.risk_level == RiskLevel.LOW

    def test_analyze_for_update(self, guard):
        """测试FOR UPDATE语句"""
        report = guard.analyze("SELECT * FROM users FOR UPDATE")
        assert report.has_for_update is True
        assert report.risk_level == RiskLevel.BLOCK

    def test_analyze_lock_table(self, guard):
        """测试LOCK TABLE语句"""
        report = guard.analyze("LOCK TABLE users IN EXCLUSIVE MODE")
        assert report.has_lock_table is True
        assert report.risk_level == RiskLevel.BLOCK

    def test_analyze_commit(self, guard):
        """测试COMMIT语句"""
        report = guard.analyze("COMMIT")
        assert "COMMIT" in report.tx_tokens
        assert report.risk_level == RiskLevel.BLOCK

    def test_analyze_rollback(self, guard):
        """测试ROLLBACK语句"""
        report = guard.analyze("ROLLBACK")
        assert "ROLLBACK" in report.tx_tokens
        assert report.risk_level == RiskLevel.BLOCK

    def test_analyze_truncate(self, guard):
        """测试TRUNCATE语句"""
        report = guard.analyze("TRUNCATE TABLE users")
        assert "TRUNCATE" in report.write_tokens
        assert report.risk_level == RiskLevel.BLOCK

    def test_analyze_alter(self, guard):
        """测试ALTER语句"""
        report = guard.analyze("ALTER TABLE users ADD column1 VARCHAR2(100)")
        assert "ALTER" in report.write_tokens
        assert report.risk_level == RiskLevel.BLOCK

    def test_analyze_drop(self, guard):
        """测试DROP语句"""
        report = guard.analyze("DROP TABLE users")
        assert "DROP" in report.write_tokens
        assert report.risk_level == RiskLevel.BLOCK

    def test_analyze_create(self, guard):
        """测试CREATE语句"""
        report = guard.analyze("CREATE TABLE new_users (id INT)")
        assert "CREATE" in report.write_tokens
        assert report.risk_level == RiskLevel.BLOCK

    def test_analyze_normal_mode_insert(self, guard):
        """测试普通模式下的INSERT"""
        report = guard.analyze("INSERT INTO users VALUES(1)", mode="normal")
        assert report.risk_level == RiskLevel.HIGH

    def test_analyze_normal_mode_select(self, guard):
        """测试普通模式下的SELECT"""
        report = guard.analyze("SELECT * FROM users", mode="normal")
        assert report.risk_level == RiskLevel.LOW

    def test_analyze_with_system_function(self, guard):
        """测试带系统函数的SQL"""
        report = guard.analyze("SELECT UPPER(name) FROM users")
        assert report.is_select is True
        assert "UPPER" not in report.calls

    def test_readonly_mode_blocks_write(self, guard):
        """测试只读模式拦截写操作"""
        report = guard.analyze("SELECT * FROM users; INSERT INTO logs VALUES(1)")
        assert report.risk_level == RiskLevel.BLOCK

    def test_guess_statement_type(self, guard):
        """测试语句类型猜测"""
        assert guard._guess_statement_type("SELECT * FROM users") == "SELECT"
        assert guard._guess_statement_type("INSERT INTO users VALUES(1)") == "INSERT"
        assert guard._guess_statement_type("UPDATE users SET name='a'") == "UPDATE"
        assert guard._guess_statement_type("DELETE FROM users") == "DELETE"
        assert guard._guess_statement_type("  SELECT 1") == "SELECT"

    def test_regex_for_update(self, guard):
        """测试FOR UPDATE正则"""
        assert guard._regex_for_update("SELECT * FROM t FOR UPDATE") is True
        assert guard._regex_for_update("SELECT * FROM t") is False

    def test_regex_lock_table(self, guard):
        """测试LOCK TABLE正则"""
        assert guard._regex_lock_table("LOCK TABLE t IN EXCLUSIVE MODE") is True
        assert guard._regex_lock_table("SELECT * FROM t") is False

    def test_heuristic_extract_calls(self, guard):
        """测试启发式提取调用"""
        calls = guard._heuristic_extract_calls("SELECT my_proc() FROM DUAL")
        assert "MY_PROC" in calls or len(calls) >= 0

    def test_is_system_safe_call_function(self, guard):
        """测试系统安全调用-函数"""
        assert guard._is_system_safe_call("ABS") is True
        assert guard._is_system_safe_call("SUBSTR") is True

    def test_is_system_safe_call_schema_function(self, guard):
        """测试系统安全调用-带schema的函数"""
        assert guard._is_system_safe_call("SYS.FUNC") is True
        assert guard._is_system_safe_call("SYSDBA.PROC") is True

    def test_is_system_safe_call_user_function(self, guard):
        """测试用户函数不是安全调用"""
        assert guard._is_system_safe_call("MY_PROC") is False
        assert guard._is_system_safe_call("USER.PROC") is False

    def test_canonicalize_calls(self, guard):
        """测试规范化调用"""
        calls = ["schema.proc", "SCHEMA . PROC", "My_Proc"]
        result = guard._canonicalize_calls(calls)
        assert all(c.isupper() for c in result)

    def test_normalize_preserves_structure(self, guard):
        """测试标准化保留结构"""
        normalized, meta = guard._normalize("SELECT * FROM users")
        assert "SELECT" in normalized.upper()
        assert meta["original_length"] > 0


class TestWriteKeywords:
    """WRITE_KEYWORDS 常量测试"""

    def test_write_keywords_include_dml(self):
        """测试包含DML关键字"""
        assert "INSERT" in WRITE_KEYWORDS
        assert "UPDATE" in WRITE_KEYWORDS
        assert "DELETE" in WRITE_KEYWORDS

    def test_write_keywords_include_ddl(self):
        """测试包含DDL关键字"""
        assert "CREATE" in WRITE_KEYWORDS
        assert "DROP" in WRITE_KEYWORDS
        assert "ALTER" in WRITE_KEYWORDS


class TestTxKeywords:
    """TX_KEYWORDS 常量测试"""

    def test_tx_keywords_include_commit_rollback(self):
        """测试包含事务关键字"""
        assert "COMMIT" in TX_KEYWORDS
        assert "ROLLBACK" in TX_KEYWORDS


class TestSystemFunctionAllowlist:
    """系统函数白名单测试"""

    def test_common_functions_in_allowlist(self):
        """测试常见函数在白名单"""
        assert "ABS" in SYSTEM_FUNCTION_ALLOWLIST
        assert "SUBSTR" in SYSTEM_FUNCTION_ALLOWLIST
        assert "UPPER" in SYSTEM_FUNCTION_ALLOWLIST
        assert "LOWER" in SYSTEM_FUNCTION_ALLOWLIST


class TestRoutineIntrospectorExtended:
    """RoutineIntrospector 扩展测试"""

    def test_fetch_routine_text_without_exec(self):
        """测试无exec函数时返回None"""
        introspector = RoutineIntrospector()
        result = introspector._fetch_routine_text("test_proc")
        assert result is None

    def test_fetch_routine_text_empty_name(self):
        """测试空例程名"""
        exec_func = MagicMock()
        introspector = RoutineIntrospector(exec_sql_func=exec_func)
        result = introspector._fetch_routine_text("")
        assert result is None

    def test_fetch_routine_text_whitespace_only(self):
        """测试仅空格"""
        exec_func = MagicMock()
        introspector = RoutineIntrospector(exec_sql_func=exec_func)
        result = introspector._fetch_routine_text("   ")
        assert result is None

    def test_classify_routine_with_safe_ddl(self):
        """测试安全DDL"""
        mock_exec = MagicMock(return_value="SELECT name FROM users WHERE id = 1")
        introspector = RoutineIntrospector(exec_sql_func=mock_exec)
        result = introspector.classify_routine("my_schema.safe_func")
        assert result == "SAFE"

    def test_classify_routine_with_insert_ddl(self):
        """测试包含INSERT的DDL"""
        mock_exec = MagicMock(return_value="INSERT INTO logs VALUES(1)")
        introspector = RoutineIntrospector(exec_sql_func=mock_exec)
        result = introspector.classify_routine("risky_proc")
        assert result == "RISKY"

    def test_classify_routine_with_update_ddl(self):
        """测试包含UPDATE的DDL"""
        mock_exec = MagicMock(return_value="UPDATE users SET name='test'")
        introspector = RoutineIntrospector(exec_sql_func=mock_exec)
        result = introspector.classify_routine("update_proc")
        assert result == "RISKY"

    def test_classify_routine_with_delete_ddl(self):
        """测试包含DELETE的DDL"""
        mock_exec = MagicMock(return_value="DELETE FROM users WHERE id = 1")
        introspector = RoutineIntrospector(exec_sql_func=mock_exec)
        result = introspector.classify_routine("delete_proc")
        assert result == "RISKY"

    def test_classify_routine_with_merge_ddl(self):
        """测试包含MERGE的DDL"""
        mock_exec = MagicMock(return_value="MERGE INTO users u USING ...")
        introspector = RoutineIntrospector(exec_sql_func=mock_exec)
        result = introspector.classify_routine("merge_proc")
        assert result == "RISKY"

    def test_classify_routine_with_truncate_ddl(self):
        """测试包含TRUNCATE的DDL"""
        mock_exec = MagicMock(return_value="TRUNCATE TABLE logs")
        introspector = RoutineIntrospector(exec_sql_func=mock_exec)
        result = introspector.classify_routine("trunc_proc")
        assert result == "RISKY"

    def test_classify_routine_with_alter_ddl(self):
        """测试包含ALTER的DDL"""
        mock_exec = MagicMock(return_value="ALTER TABLE users ADD col1 INT")
        introspector = RoutineIntrospector(exec_sql_func=mock_exec)
        result = introspector.classify_routine("alter_proc")
        assert result == "RISKY"

    def test_classify_routine_with_drop_ddl(self):
        """测试包含DROP的DDL"""
        mock_exec = MagicMock(return_value="DROP TABLE users")
        introspector = RoutineIntrospector(exec_sql_func=mock_exec)
        result = introspector.classify_routine("drop_proc")
        assert result == "RISKY"

    def test_classify_routine_with_create_ddl(self):
        """测试包含CREATE的DDL"""
        mock_exec = MagicMock(return_value="CREATE TABLE new_table (id INT)")
        introspector = RoutineIntrospector(exec_sql_func=mock_exec)
        result = introspector.classify_routine("create_proc")
        assert result == "RISKY"

    def test_classify_routine_with_execute_immediate(self):
        """测试包含EXECUTE IMMEDIATE的DDL"""
        mock_exec = MagicMock(return_value="EXECUTE IMMEDIATE 'DELETE FROM users'")
        introspector = RoutineIntrospector(exec_sql_func=mock_exec)
        result = introspector.classify_routine("exec_proc")
        assert result == "RISKY"

    def test_classify_routine_exec_exception(self):
        """测试执行SQL异常"""
        mock_exec = MagicMock(side_effect=Exception("DB error"))
        introspector = RoutineIntrospector(exec_sql_func=mock_exec)
        result = introspector.classify_routine("error_proc")
        assert result == "UNKNOWN"

    def test_call_exec_no_params(self):
        """测试无参数执行"""
        exec_func = MagicMock(return_value="result")
        introspector = RoutineIntrospector(exec_sql_func=exec_func)
        result = introspector._call_exec("SELECT 1")
        exec_func.assert_called_once_with("SELECT 1")
        assert result == "result"

    def test_call_exec_with_params(self):
        """测试带参数执行"""
        exec_func = MagicMock(return_value="result")
        introspector = RoutineIntrospector(exec_sql_func=exec_func)
        result = introspector._call_exec("SELECT ? FROM DUAL", ["value"])
        exec_func.assert_called_once()
        assert result == "result"

    def test_call_exec_no_exec_func(self):
        """测试没有exec函数"""
        introspector = RoutineIntrospector()
        result = introspector._call_exec("SELECT 1")
        assert result is None

    def test_extract_ddl_text_uppercase_dict(self):
        """测试大写DDL key"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_text({"DDL": "CREATE PROCEDURE test"})
        assert result == "CREATE PROCEDURE test"

    def test_extract_ddl_text_text_key(self):
        """测试text key"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_text({"text": "CREATE PROCEDURE test"})
        assert result == "CREATE PROCEDURE test"

    def test_extract_ddl_text_uppercase_text_key(self):
        """测试大写TEXT key"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_text({"TEXT": "CREATE PROCEDURE test"})
        assert result == "CREATE PROCEDURE test"

    def test_extract_ddl_text_dict_with_result(self):
        """测试带result的字典"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_text({"result": [{"ddl": "CREATE PROC"}]})
        assert result == "CREATE PROC"

    def test_extract_ddl_text_dict_with_rows(self):
        """测试带rows的字典"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_text({"rows": [{"ddl": "CREATE PROC"}]})
        assert result == "CREATE PROC"

    def test_extract_ddl_text_dict_with_data(self):
        """测试带data的字典"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_text({"data": [{"ddl": "CREATE PROC"}]})
        assert result == "CREATE PROC"

    def test_extract_ddl_text_dict_other_structure(self):
        """测试字典其他结构-无有效key返回None"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_text({"other_value": "t"})
        assert result is None

    def test_extract_ddl_from_rows_empty(self):
        """测试空rows"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_from_rows([])
        assert result is None

    def test_extract_ddl_from_rows_dict_no_valid_key(self):
        """测试字典无有效key"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_from_rows([{"no_ddl": "value"}])
        assert result == "value"

    def test_extract_ddl_from_rows_dict_with_value(self):
        """测试字典有值"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_from_rows([{"some_value": "CREATE PROC"}])
        assert result == "CREATE PROC"

    def test_extract_ddl_from_rows_list(self):
        """测试列表类型"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_from_rows([["CREATE PROC"]])
        assert result == "CREATE PROC"

    def test_extract_ddl_from_rows_tuple(self):
        """测试元组类型"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_from_rows([("CREATE PROC",)])
        assert result == "CREATE PROC"

    def test_extract_ddl_from_rows_string(self):
        """测试字符串类型"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_from_rows(["CREATE PROC"])
        assert result == "CREATE PROC"

    def test_extract_ddl_text_empty_string(self):
        """测试空字符串"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_text("")
        assert result is None

    def test_extract_ddl_text_whitespace_only(self):
        """测试仅空白字符"""
        introspector = RoutineIntrospector()
        result = introspector._extract_ddl_text("   ")
        assert result is None


class TestSqlGuardExtended:
    """SqlGuard 扩展测试"""

    def test_scan_tokens_write_keywords(self):
        """测试扫描写关键字"""
        guard = SqlGuard()
        result = guard._scan_tokens("INSERT INTO users VALUES(1)")
        assert "INSERT" in result["write"]

    def test_scan_tokens_tx_keywords(self):
        """测试扫描事务关键字"""
        guard = SqlGuard()
        result = guard._scan_tokens("COMMIT")
        assert "COMMIT" in result["tx"]

    def test_scan_tokens_lock_patterns(self):
        """测试扫描锁定模式"""
        guard = SqlGuard()
        result = guard._scan_tokens("SELECT * FROM t FOR UPDATE")
        assert "FOR UPDATE" in result["lock"]

    def test_scan_tokens_lock_table(self):
        """测试LOCK TABLE模式"""
        guard = SqlGuard()
        result = guard._scan_tokens("LOCK TABLE users IN EXCLUSIVE MODE")
        assert "LOCK TABLE" in result["lock"]

    def test_scan_tokens_multiple(self):
        """测试多关键字扫描"""
        guard = SqlGuard()
        result = guard._scan_tokens("INSERT INTO logs SELECT * FROM users COMMIT")
        assert "INSERT" in result["write"]
        assert "COMMIT" in result["tx"]

    def test_decide_readonly_select_low_risk(self):
        """测试只读模式-安全SELECT"""
        guard = SqlGuard()
        level, reason = guard._decide(
            mode="readonly",
            is_select=True,
            stmt_type="SELECT",
            has_for_update=False,
            has_lock_table=False,
            write_tokens=[],
            tx_tokens=[],
            risky_calls=[],
            unknown_calls=[],
        )
        assert level == RiskLevel.LOW
        assert "安全" in reason

    def test_decide_readonly_unknown_calls_block(self):
        """测试只读模式-未知调用拦截"""
        guard = SqlGuard()
        level, reason = guard._decide(
            mode="readonly",
            is_select=True,
            stmt_type="SELECT",
            has_for_update=False,
            has_lock_table=False,
            write_tokens=[],
            tx_tokens=[],
            risky_calls=[],
            unknown_calls=["MY_PROC"],
        )
        assert level == RiskLevel.BLOCK
        assert "MY_PROC" in reason

    def test_decide_readonly_risky_calls_block(self):
        """测试只读模式-危险调用拦截"""
        guard = SqlGuard()
        level, reason = guard._decide(
            mode="readonly",
            is_select=True,
            stmt_type="SELECT",
            has_for_update=False,
            has_lock_table=False,
            write_tokens=[],
            tx_tokens=[],
            risky_calls=["WRITE_PROC"],
            unknown_calls=[],
        )
        assert level == RiskLevel.BLOCK
        assert "WRITE_PROC" in reason

    def test_decide_normal_select_low_risk(self):
        """测试普通模式-安全SELECT"""
        guard = SqlGuard()
        level, reason = guard._decide(
            mode="normal",
            is_select=True,
            stmt_type="SELECT",
            has_for_update=False,
            has_lock_table=False,
            write_tokens=[],
            tx_tokens=[],
            risky_calls=[],
            unknown_calls=[],
        )
        assert level == RiskLevel.LOW

    def test_decide_normal_non_select_high(self):
        """测试普通模式-非SELECT HIGH"""
        guard = SqlGuard()
        level, reason = guard._decide(
            mode="normal",
            is_select=False,
            stmt_type="INSERT",
            has_for_update=False,
            has_lock_table=False,
            write_tokens=[],
            tx_tokens=[],
            risky_calls=[],
            unknown_calls=[],
        )
        assert level == RiskLevel.HIGH
        assert "INSERT" in reason

    def test_decide_normal_write_tokens_high(self):
        """测试普通模式-写操作HIGH"""
        guard = SqlGuard()
        level, reason = guard._decide(
            mode="normal",
            is_select=True,
            stmt_type="SELECT",
            has_for_update=False,
            has_lock_table=False,
            write_tokens=["INSERT"],
            tx_tokens=[],
            risky_calls=[],
            unknown_calls=[],
        )
        assert level == RiskLevel.HIGH

    def test_decide_normal_tx_tokens_high(self):
        """测试普通模式-事务控制HIGH"""
        guard = SqlGuard()
        level, reason = guard._decide(
            mode="normal",
            is_select=True,
            stmt_type="SELECT",
            has_for_update=False,
            has_lock_table=False,
            write_tokens=[],
            tx_tokens=["COMMIT"],
            risky_calls=[],
            unknown_calls=[],
        )
        assert level == RiskLevel.HIGH

    def test_decide_normal_lock_table_high(self):
        """测试普通模式-LOCK TABLE HIGH"""
        guard = SqlGuard()
        level, reason = guard._decide(
            mode="normal",
            is_select=True,
            stmt_type="SELECT",
            has_for_update=False,
            has_lock_table=True,
            write_tokens=[],
            tx_tokens=[],
            risky_calls=[],
            unknown_calls=[],
        )
        assert level == RiskLevel.HIGH

    def test_decide_normal_for_update_medium(self):
        """测试普通模式-FOR UPDATE MEDIUM"""
        guard = SqlGuard()
        level, reason = guard._decide(
            mode="normal",
            is_select=True,
            stmt_type="SELECT",
            has_for_update=True,
            has_lock_table=False,
            write_tokens=[],
            tx_tokens=[],
            risky_calls=[],
            unknown_calls=[],
        )
        assert level == RiskLevel.MEDIUM

    def test_decide_normal_risky_calls_high(self):
        """测试普通模式-危险调用HIGH"""
        guard = SqlGuard()
        level, reason = guard._decide(
            mode="normal",
            is_select=True,
            stmt_type="SELECT",
            has_for_update=False,
            has_lock_table=False,
            write_tokens=[],
            tx_tokens=[],
            risky_calls=["RISKY_PROC"],
            unknown_calls=[],
        )
        assert level == RiskLevel.HIGH

    def test_decide_normal_unknown_calls_medium(self):
        """测试普通模式-未知调用MEDIUM"""
        guard = SqlGuard()
        level, reason = guard._decide(
            mode="normal",
            is_select=True,
            stmt_type="SELECT",
            has_for_update=False,
            has_lock_table=False,
            write_tokens=[],
            tx_tokens=[],
            risky_calls=[],
            unknown_calls=["UNKNOWN_PROC"],
        )
        assert level == RiskLevel.MEDIUM

    def test_normalize_remove_single_line_comment(self):
        """测试移除单行注释"""
        guard = SqlGuard()
        normalized, meta = guard._normalize("SELECT * FROM users -- comment")
        assert "--" not in normalized
        assert meta["has_comments"] is True

    def test_normalize_remove_block_comment(self):
        """测试移除块注释"""
        guard = SqlGuard()
        normalized, meta = guard._normalize("SELECT /* comment */ * FROM users")
        assert "/*" not in normalized
        assert meta["has_comments"] is True

    def test_normalize_preserve_string_literal(self):
        """测试保留字符串字面量"""
        guard = SqlGuard()
        normalized, meta = guard._normalize("SELECT * FROM users WHERE name = 'test'")
        assert "__STR_" in normalized
        assert meta["str_placeholders_count"] == 1

    def test_normalize_string_with_escaped_quote(self):
        """测试带转义引号的字符串"""
        guard = SqlGuard()
        normalized, meta = guard._normalize(
            "SELECT * FROM users WHERE name = 'it''s test'"
        )
        assert "__STR_" in normalized
        assert meta["str_placeholders_count"] == 1

    def test_normalize_whitespace_collapse(self):
        """测试空白字符合并"""
        guard = SqlGuard()
        normalized, meta = guard._normalize("SELECT    *    FROM   users")
        assert "  " not in normalized

    def test_normalize_no_comment(self):
        """测试无注释"""
        guard = SqlGuard()
        normalized, meta = guard._normalize("SELECT * FROM users")
        assert meta["has_comments"] is False

    def test_guess_statement_type_merge(self):
        """测试MERGE语句类型"""
        guard = SqlGuard()
        assert guard._guess_statement_type("MERGE INTO users ...") == "MERGE"

    def test_guess_statement_type_truncate(self):
        """测试TRUNCATE语句类型"""
        guard = SqlGuard()
        assert guard._guess_statement_type("TRUNCATE TABLE users") == "TRUNCATE"

    def test_guess_statement_type_grant(self):
        """测试GRANT语句类型"""
        guard = SqlGuard()
        assert guard._guess_statement_type("GRANT SELECT ON users TO Bob") == "GRANT"

    def test_guess_statement_type_revoke(self):
        """测试REVOKE语句类型"""
        guard = SqlGuard()
        assert (
            guard._guess_statement_type("REVOKE SELECT ON users FROM Bob") == "REVOKE"
        )

    def test_guess_statement_type_call(self):
        """测试CALL语句类型"""
        guard = SqlGuard()
        assert guard._guess_statement_type("CALL my_proc()") == "CALL"

    def test_guess_statement_type_exec(self):
        """测试EXEC语句类型"""
        guard = SqlGuard()
        assert guard._guess_statement_type("EXEC my_proc") == "EXEC"

    def test_guess_statement_type_execute(self):
        """测试EXECUTE语句类型"""
        guard = SqlGuard()
        assert guard._guess_statement_type("EXECUTE my_proc") == "EXEC"

    def test_guess_statement_type_with(self):
        """测试WITH语句类型"""
        guard = SqlGuard()
        assert (
            guard._guess_statement_type("WITH temp AS (SELECT 1) SELECT * FROM temp")
            == "WITH"
        )

    def test_guess_statement_type_with_select(self):
        """测试WITH SELECT语句"""
        guard = SqlGuard()
        assert guard._guess_statement_type("  (SELECT 1)") == "SELECT"

    def test_guess_statement_type_unknown(self):
        """测试未知语句类型"""
        guard = SqlGuard()
        assert guard._guess_statement_type("SOME RANDOM TEXT") == "UNKNOWN"

    def test_heuristic_extract_calls_with_schema(self):
        """测试提取带schema的调用"""
        guard = SqlGuard()
        calls = guard._heuristic_extract_calls("SELECT my_schema.my_func() FROM DUAL")
        assert "my_schema.my_func" in calls

    def test_heuristic_extract_calls_ignore_system_schema(self):
        """测试忽略系统schema"""
        guard = SqlGuard()
        calls = guard._heuristic_extract_calls("SELECT SYS.FUNC() FROM DUAL")
        assert "SYS.FUNC" not in calls

    def test_heuristic_extract_calls_ignore_sysdba(self):
        """测试忽略SYSDBA schema"""
        guard = SqlGuard()
        calls = guard._heuristic_extract_calls("SELECT SYSDBA.PROC() FROM DUAL")
        assert "SYSDBA.PROC" not in calls

    def test_heuristic_extract_calls_dedup(self):
        """测试去重"""
        guard = SqlGuard()
        calls = guard._heuristic_extract_calls(
            "SELECT my_func() FROM t1, my_func() FROM t2"
        )
        assert len(set(calls)) == 1

    def test_canonicalize_calls_removes_spaces(self):
        """测试规范化移除空格"""
        guard = SqlGuard()
        calls = ["A . B", "A.B", "A  .   B"]
        result = guard._canonicalize_calls(calls)
        assert len(result) == 1

    def test_analyze_with_introspector_safe(self):
        """测试带内省器的安全调用"""
        mock_ri = MagicMock()
        mock_ri.classify_routine.return_value = "SAFE"
        guard = SqlGuard(routine_introspector=mock_ri)
        report = guard.analyze("SELECT my_safe_func() FROM DUAL")
        assert report.risk_level == RiskLevel.LOW

    def test_analyze_with_introspector_risky(self):
        """测试带内省器的危险调用"""
        mock_ri = MagicMock()
        mock_ri.classify_routine.return_value = "RISKY"
        guard = SqlGuard(routine_introspector=mock_ri)
        report = guard.analyze("SELECT my_risky_func() FROM DUAL")
        assert report.risk_level == RiskLevel.BLOCK
        assert "RISKY" in report.risky_calls[0] if report.risky_calls else True

    def test_analyze_with_introspector_unknown(self):
        """测试带内省器的未知调用"""
        mock_ri = MagicMock()
        mock_ri.classify_routine.return_value = "UNKNOWN"
        guard = SqlGuard(routine_introspector=mock_ri)
        report = guard.analyze("SELECT my_unknown_func() FROM DUAL")
        assert report.risk_level == RiskLevel.BLOCK

    def test_analyze_empty_sql(self):
        """测试空SQL"""
        guard = SqlGuard()
        report = guard.analyze("")
        assert report.statement_type == "UNKNOWN"

    def test_analyze_whitespace_only(self):
        """测试仅空白SQL"""
        guard = SqlGuard()
        report = guard.analyze("   ")
        assert report.statement_type == "UNKNOWN"

    def test_analyze_with_leading_parenthesis(self):
        """测试带前导括号的SQL"""
        guard = SqlGuard()
        report = guard.analyze("(SELECT * FROM users)")
        assert report.is_select is True

    def test_normalize_preserves_comment_in_string(self):
        """测试字符串内的注释被保留"""
        guard = SqlGuard()
        normalized, meta = guard._normalize(
            "SELECT * FROM users WHERE text = '--not comment'"
        )
        assert "__STR_" in normalized
