"""MCPGroupService 单元测试"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dm_mcp.domain.mcp.events import MCPGroupChanged, MCPEntityAssigned, MCPProvidersStarted
from dm_mcp.domain.mcp.services.group import MCPGroupService
from tests.conftest import FakeEventService


def _make_group(id_, name, parent_id=None):
    g = MagicMock()
    g.id = id_
    g.name = name
    g.parent_id = parent_id
    g.short_description = ""
    g.long_description = ""
    g.created_at = None
    g.updated_at = None
    return g


@pytest.fixture
def mcp_group_service():
    return MCPGroupService(FakeEventService())


@pytest.fixture
def mock_session_ctx():
    """提供 mock 数据库会话上下文"""
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx, session


# ============================================================
# MCPGroupService 分组结构事件发布测试
# ============================================================
class TestMCPGroupServiceEventPublishing:
    """测试 MCPGroupService mutation 后发布事件"""

    @pytest.mark.asyncio
    async def test_delete_cli_group_publishes_event(
        self, mcp_group_service, mock_session_ctx
    ):
        """删除 CLI 分组应发布 MCPGroupChanged 事件"""
        ctx, session = mock_session_ctx

        groups = [
            _make_group("g1", "db"),
            _make_group("g2", "sub", parent_id="g1"),
        ]

        def side_effect(*args, **kwargs):
            r = MagicMock()
            r.scalars.return_value.all.return_value = groups
            r.scalar_one_or_none.return_value = groups[0]
            return r

        session.execute = AsyncMock(side_effect=side_effect)

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ):
            await mcp_group_service.delete_cli_group("g1")

        events = mcp_group_service._event_service.get_events()
        assert len(events) == 1
        assert isinstance(events[0], MCPGroupChanged)
        assert events[0].group_id == "g1"
        assert events[0].operation == "deleted"
        assert events[0].old_path == "db"

    @pytest.mark.asyncio
    async def test_rename_cli_group_publishes_event(
        self, mcp_group_service, mock_session_ctx
    ):
        """重命名 CLI 分组应发布 MCPGroupChanged 事件"""
        ctx, session = mock_session_ctx

        groups = [_make_group("g1", "db")]

        exec_count = [0]

        def side_effect(*args, **kwargs):
            exec_count[0] += 1
            r = MagicMock()
            r.scalars.return_value.all.return_value = groups
            if exec_count[0] == 2:  # 检查重名
                r.scalar_one_or_none.return_value = None
            elif exec_count[0] == 3:  # 获取模型
                r.scalar_one_or_none.return_value = groups[0]
            else:
                r.scalar_one_or_none.return_value = None
            return r

        session.execute = AsyncMock(side_effect=side_effect)

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ):
            await mcp_group_service.rename_cli_group("g1", "database")

        events = mcp_group_service._event_service.get_events()
        assert len(events) == 1
        assert isinstance(events[0], MCPGroupChanged)
        assert events[0].group_id == "g1"
        assert events[0].operation == "renamed"
        assert events[0].old_path == "db"
        assert events[0].new_path == "database"

    @pytest.mark.asyncio
    async def test_move_cli_group_publishes_event(
        self, mcp_group_service, mock_session_ctx
    ):
        """移动 CLI 分组应发布 MCPGroupChanged 事件"""
        ctx, session = mock_session_ctx

        groups = [
            _make_group("g1", "old"),
            _make_group("g2", "parent"),
        ]

        exec_count = [0]

        def side_effect(*args, **kwargs):
            exec_count[0] += 1
            r = MagicMock()
            r.scalars.return_value.all.return_value = groups
            if exec_count[0] == 2:  # 检查重名
                r.scalar_one_or_none.return_value = None
            elif exec_count[0] == 3:  # 获取模型
                r.scalar_one_or_none.return_value = groups[0]
            else:
                r.scalar_one_or_none.return_value = None
            return r

        session.execute = AsyncMock(side_effect=side_effect)

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ):
            await mcp_group_service.move_cli_group("g1", "g2")

        events = mcp_group_service._event_service.get_events()
        assert len(events) == 1
        assert isinstance(events[0], MCPGroupChanged)
        assert events[0].group_id == "g1"
        assert events[0].operation == "moved"
        assert events[0].old_path == "old"
        assert events[0].new_path == "parent.old"

    @pytest.mark.asyncio
    async def test_create_cli_group_publishes_event(
        self, mcp_group_service, mock_session_ctx
    ):
        """创建 CLI 分组应发布 MCPGroupChanged 事件"""
        ctx, session = mock_session_ctx

        groups = []

        def side_effect(*args, **kwargs):
            r = MagicMock()
            r.scalars.return_value.all.return_value = groups
            r.scalar_one_or_none.return_value = None
            return r

        session.execute = AsyncMock(side_effect=side_effect)

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ):
            await mcp_group_service.create_cli_group(
                parent_id=None, name="db", description="desc"
            )

        events = mcp_group_service._event_service.get_events()
        assert len(events) == 1
        assert isinstance(events[0], MCPGroupChanged)
        assert events[0].operation == "created"
        assert events[0].new_path == "db"

    @pytest.mark.asyncio
    async def test_update_description_publishes_event(
        self, mcp_group_service, mock_session_ctx
    ):
        """更新 CLI 分组描述应发布 MCPGroupChanged 事件"""
        ctx, session = mock_session_ctx

        groups = [_make_group("g1", "db")]

        def side_effect(*args, **kwargs):
            r = MagicMock()
            r.scalars.return_value.all.return_value = groups
            r.scalar_one.return_value = groups[0]
            return r

        session.execute = AsyncMock(side_effect=side_effect)

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ):
            await mcp_group_service.update_cli_group_description("g1", "new desc")

        events = mcp_group_service._event_service.get_events()
        assert len(events) == 1
        assert isinstance(events[0], MCPGroupChanged)
        assert events[0].group_id == "g1"
        assert events[0].operation == "updated"


# ============================================================
# MCPGroupService 缓存测试
# ============================================================
class TestMCPGroupServiceCache:
    """测试缓存行为"""

    @pytest.mark.asyncio
    async def test_cache_invalidated_on_delete(self, mcp_group_service, mock_session_ctx):
        ctx, session = mock_session_ctx

        groups = [_make_group("g1", "db")]

        def side_effect(*args, **kwargs):
            r = MagicMock()
            r.scalars.return_value.all.return_value = groups
            r.scalar_one_or_none.return_value = groups[0]
            return r

        session.execute = AsyncMock(side_effect=side_effect)

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ):
            # 先填充缓存
            await mcp_group_service._ensure_cache()
            assert mcp_group_service._path_to_id is not None

            await mcp_group_service.delete_cli_group("g1")
            assert mcp_group_service._path_to_id is None


# ============================================================
# MCPGroupService ID 格式测试
# ============================================================
class TestMCPGroupServiceShortId:
    """测试短 id 行为"""

    @pytest.mark.asyncio
    async def test_create_generates_short_id(self, mcp_group_service, mock_session_ctx):
        ctx, session = mock_session_ctx

        def side_effect(*args, **kwargs):
            r = MagicMock()
            r.scalars.return_value.all.return_value = []
            r.scalar_one_or_none.return_value = None
            return r

        session.execute = AsyncMock(side_effect=side_effect)

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ):
            result = await mcp_group_service.create_cli_group(
                parent_id=None, name="db", description="test"
            )

        assert isinstance(result["id"], str)
        assert len(result["id"]) == 12
        assert result["id"].isalnum()


# ============================================================
# sync_missing_group_paths
# ============================================================
class TestSyncMissingGroupPaths:
    """测试将 Provider 硬编码 group 同步到数据库"""

    @pytest.mark.asyncio
    async def test_creates_missing_paths(self, mcp_group_service, mock_session_ctx):
        """db.dpc.cluster 会依次创建 db、db.dpc、db.dpc.cluster"""
        ctx, session = mock_session_ctx

        def side_effect(*args, **kwargs):
            r = MagicMock()
            r.scalars.return_value.all.return_value = []
            r.scalar_one_or_none.return_value = None
            return r

        session.execute = AsyncMock(side_effect=side_effect)

        call_count = 0
        id_to_path: dict[str, str] = {}

        async def fake_create(parent_id, name, description):
            nonlocal call_count
            call_count += 1
            new_id = f"id{call_count}"
            if parent_id is None:
                path = name
            else:
                path = f"{id_to_path[parent_id]}.{name}"
            id_to_path[new_id] = path
            return {"id": new_id, "path": path, "name": name}

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ), patch.object(
            mcp_group_service, "create_cli_group", side_effect=fake_create
        ):
            created = await mcp_group_service.sync_missing_group_paths(
                ["db.dpc.cluster"]
            )

        assert len(created) == 3
        assert created[0]["path"] == "db"
        assert created[1]["path"] == "db.dpc"
        assert created[2]["path"] == "db.dpc.cluster"

    @pytest.mark.asyncio
    async def test_skips_existing_paths(
        self, mcp_group_service, mock_session_ctx
    ):
        """已存在的路径不再重复创建"""
        ctx, session = mock_session_ctx

        # 模拟 DB 里已有 "db" 和 "db.mysql"
        db_group = _make_group("abc123", "db", None)
        mysql_group = _make_group("def456", "mysql", "abc123")

        def side_effect(*args, **kwargs):
            r = MagicMock()
            r.scalars.return_value.all.return_value = [db_group, mysql_group]
            r.scalar_one_or_none.return_value = None
            return r

        session.execute = AsyncMock(side_effect=side_effect)

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ):
            created = await mcp_group_service.sync_missing_group_paths(
                ["db", "db.mysql", "db.dpc"]
            )

        # 只创建 db.dpc（db 已存在，db.mysql 已存在）
        assert len(created) == 1
        assert created[0]["path"] == "db.dpc"

    @pytest.mark.asyncio
    async def test_empty_input(self, mcp_group_service, mock_session_ctx):
        """空列表不执行任何操作"""
        ctx, session = mock_session_ctx

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ):
            created = await mcp_group_service.sync_missing_group_paths([])

        assert created == []


class TestOnMCPProvidersStarted:
    """测试 MCPGroupService 对 MCPProvidersStarted 事件的响应"""

    @pytest.mark.asyncio
    async def test_on_mcp_providers_started_calls_sync(self, mcp_group_service):
        event = MCPProvidersStarted(group_paths=["db", "db.mysql"])

        with patch.object(
            mcp_group_service, "sync_missing_group_paths", new_callable=AsyncMock
        ) as mock_sync:
            await mcp_group_service.on_mcp_providers_started(event)

        mock_sync.assert_awaited_once_with(["db", "db.mysql"])

    @pytest.mark.asyncio
    async def test_on_mcp_providers_started_skips_empty(self, mcp_group_service):
        event = MCPProvidersStarted(group_paths=[])

        with patch.object(
            mcp_group_service, "sync_missing_group_paths", new_callable=AsyncMock
        ) as mock_sync:
            await mcp_group_service.on_mcp_providers_started(event)

        mock_sync.assert_not_awaited()


# ============================================================
# MCPGroupService 实体归属 assign / unassign 测试
# ============================================================
class TestMCPGroupServiceAssign:
    """测试单实体分组归属"""

    @pytest.mark.asyncio
    async def test_assign_tool_publishes_event(
        self, mcp_group_service, mock_session_ctx
    ):
        """分配工具到分组应发布事件"""
        ctx, session = mock_session_ctx

        def side_effect(*args, **kwargs):
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            return r

        session.execute = AsyncMock(side_effect=side_effect)

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ), patch.object(
            mcp_group_service, "get_cli_group_by_id", new_callable=AsyncMock,
            return_value={"id": "g1", "name": "test"}
        ):
            result = await mcp_group_service.assign_tool("tool1", "g1")

        assert result["object_type"] == "tool"
        assert result["key"] == "tool1"
        assert result["group_id"] == "g1"
        events = mcp_group_service._event_service.get_events()
        assert len(events) == 1
        assert isinstance(events[0], MCPEntityAssigned)
        assert events[0].group_id == "g1"

    @pytest.mark.asyncio
    async def test_unassign_tool_publishes_event(
        self, mcp_group_service, mock_session_ctx
    ):
        """解除工具分组归属应发布事件"""
        ctx, session = mock_session_ctx

        mo_result = MagicMock()
        mo_result.scalar_one_or_none.return_value = MagicMock()
        session.execute.return_value = mo_result

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ):
            result = await mcp_group_service.unassign_tool("tool1")

        assert result["object_type"] == "tool"
        assert result["key"] == "tool1"
        assert result["group_id"] is None
        events = mcp_group_service._event_service.get_events()
        assert len(events) == 1
        assert events[0].group_id is None

    @pytest.mark.asyncio
    async def test_assign_resource(self, mcp_group_service, mock_session_ctx):
        ctx, session = mock_session_ctx

        def side_effect(*args, **kwargs):
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            return r

        session.execute = AsyncMock(side_effect=side_effect)

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ), patch.object(
            mcp_group_service, "get_cli_group_by_id", new_callable=AsyncMock,
            return_value={"id": "g2", "name": "test"}
        ):
            result = await mcp_group_service.assign_resource("res1", "g2")

        assert result["group_id"] == "g2"

    @pytest.mark.asyncio
    async def test_assign_prompt(self, mcp_group_service, mock_session_ctx):
        ctx, session = mock_session_ctx

        def side_effect(*args, **kwargs):
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            return r

        session.execute = AsyncMock(side_effect=side_effect)

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ), patch.object(
            mcp_group_service, "get_cli_group_by_id", new_callable=AsyncMock,
            return_value={"id": "g3", "name": "test"}
        ):
            result = await mcp_group_service.assign_prompt("prompt1", "g3")

        assert result["group_id"] == "g3"

    @pytest.mark.asyncio
    async def test_assign_with_invalid_group_id_raises(
        self, mcp_group_service, mock_session_ctx
    ):
        """传入不存在的 group_id 应抛 CliGroupNotFoundError"""
        mcp_group_service.get_cli_group_by_id = AsyncMock(return_value=None)
        ctx, session = mock_session_ctx

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ):
            with pytest.raises(Exception):
                await mcp_group_service.assign_tool("tool1", "bad_id")


# ============================================================
# MCPGroupService 批量 assign 测试
# ============================================================
class TestMCPGroupServiceBatchAssign:
    """测试批量分组归属"""

    @pytest.mark.asyncio
    async def test_batch_assign_tools(self, mcp_group_service, mock_session_ctx):
        ctx, session = mock_session_ctx

        def side_effect(*args, **kwargs):
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            return r

        session.execute = AsyncMock(side_effect=side_effect)

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ), patch.object(
            mcp_group_service, "get_cli_group_by_id", new_callable=AsyncMock,
            return_value={"id": "g1", "name": "test"}
        ):
            result = await mcp_group_service.batch_assign_tools(
                ["t1", "t2"], group_id="g1"
            )

        assert len(result["updated"]) == 2
        assert result["updated"][0]["group_id"] == "g1"
        events = mcp_group_service._event_service.get_events()
        assert len(events) == 2
        assert all(e.group_id == "g1" for e in events)

    @pytest.mark.asyncio
    async def test_batch_unassign_tools(self, mcp_group_service, mock_session_ctx):
        ctx, session = mock_session_ctx

        mo_result = MagicMock()
        mo_result.scalar_one_or_none.return_value = MagicMock()
        session.execute.return_value = mo_result

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ):
            result = await mcp_group_service.batch_assign_tools(
                ["t1", "t2"], group_id=None
            )

        assert len(result["updated"]) == 2
        assert result["updated"][0]["group_id"] is None
        events = mcp_group_service._event_service.get_events()
        assert len(events) == 2
        assert all(e.group_id is None for e in events)

    @pytest.mark.asyncio
    async def test_batch_assign_resources(self, mcp_group_service, mock_session_ctx):
        ctx, session = mock_session_ctx

        def side_effect(*args, **kwargs):
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            return r

        session.execute = AsyncMock(side_effect=side_effect)

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ), patch.object(
            mcp_group_service, "get_cli_group_by_id", new_callable=AsyncMock,
            return_value={"id": "g2", "name": "test"}
        ):
            result = await mcp_group_service.batch_assign_resources(
                ["r1"], group_id="g2"
            )

        assert len(result["updated"]) == 1
        assert result["updated"][0]["group_id"] == "g2"

    @pytest.mark.asyncio
    async def test_batch_assign_prompts(self, mcp_group_service, mock_session_ctx):
        ctx, session = mock_session_ctx

        def side_effect(*args, **kwargs):
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            return r

        session.execute = AsyncMock(side_effect=side_effect)

        with patch(
            "dm_mcp.domain.mcp.services.group.get_async_session", return_value=ctx
        ), patch.object(
            mcp_group_service, "get_cli_group_by_id", new_callable=AsyncMock,
            return_value={"id": "g3", "name": "test"}
        ):
            result = await mcp_group_service.batch_assign_prompts(
                ["p1"], group_id="g3"
            )

        assert len(result["updated"]) == 1
        assert result["updated"][0]["group_id"] == "g3"
