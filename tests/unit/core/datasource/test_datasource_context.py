"""DatasourceContext 数据源上下文测试模块"""

import pytest
import uuid
from dm_mcp.core.datasource import DatasourceContext


class TestDatasourceContext:
    """DatasourceContext 测试类"""

    def test_create_datasource_context(self):
        """测试创建数据源上下文"""
        ds_id = uuid.uuid4()
        ctx = DatasourceContext(datasource_id=ds_id)
        assert ctx.datasource_id == ds_id

    def test_get_without_context(self):
        """测试无上下文时抛出异常"""
        # 需要确保没有设置上下文
        import dm_mcp.core.datasource.datasource_context as dc_module

        # 保存原始默认值
        orig_default = dc_module._datasource_context_var.get()
        try:
            dc_module._datasource_context_var.set(None)
            with pytest.raises(ValueError, match="No datasource context set"):
                DatasourceContext.get()
        finally:
            dc_module._datasource_context_var.set(orig_default)

    def test_get_with_context(self):
        """测试有上下文时返回正确的对象"""
        ds_id = uuid.uuid4()
        ctx = DatasourceContext(datasource_id=ds_id)

        import dm_mcp.core.datasource.datasource_context as dc_module

        orig_default = dc_module._datasource_context_var.get()
        try:
            token = dc_module._datasource_context_var.set(ctx)
            try:
                result = DatasourceContext.get()
                assert result.datasource_id == ds_id
            finally:
                dc_module._datasource_context_var.reset(token)
        finally:
            dc_module._datasource_context_var.set(orig_default)

    def test_as_current_context_manager(self):
        """测试上下文管理器"""
        ds_id = uuid.uuid4()
        ctx = DatasourceContext(datasource_id=ds_id)

        import dm_mcp.core.datasource.datasource_context as dc_module

        orig_default = dc_module._datasource_context_var.get()
        try:
            with DatasourceContext.as_current(ctx):
                result = DatasourceContext.get()
                assert result.datasource_id == ds_id
            # 退出后上下文应该被重置
            assert dc_module._datasource_context_var.get() == orig_default
        finally:
            dc_module._datasource_context_var.set(orig_default)

    def test_as_current_nested(self):
        """测试嵌套上下文管理器"""
        ds_id1 = uuid.uuid4()
        ds_id2 = uuid.uuid4()
        ctx1 = DatasourceContext(datasource_id=ds_id1)
        ctx2 = DatasourceContext(datasource_id=ds_id2)

        import dm_mcp.core.datasource.datasource_context as dc_module

        orig_default = dc_module._datasource_context_var.get()
        try:
            with DatasourceContext.as_current(ctx1):
                assert DatasourceContext.get().datasource_id == ds_id1
                with DatasourceContext.as_current(ctx2):
                    assert DatasourceContext.get().datasource_id == ds_id2
                # 嵌套退出后应该恢复外层上下文
                assert DatasourceContext.get().datasource_id == ds_id1
        finally:
            dc_module._datasource_context_var.set(orig_default)

    def test_datasource_context_as_pydantic_model(self):
        """测试作为 Pydantic 模型"""
        ds_id = uuid.uuid4()
        ctx = DatasourceContext(datasource_id=ds_id)
        # 验证 Pydantic 模型功能
        assert ctx.model_validate(ctx.model_dump()) == ctx
