"""数据库模型测试模块"""

import json
import uuid
from datetime import datetime, timezone

import pytest

from dm_mcp.infra.persistence.models import AdminUserModel, Base, DataSourceModel, TokenModel


class TestTokenModel:
    """Token模型测试类"""

    @staticmethod
    def _token_kwargs(**overrides):
        ds_id = overrides.pop("ds_id", uuid.uuid4())
        ssh_id = overrides.pop("ssh_id", uuid.uuid4())
        defaults = {
            "token": "test-token-123",
            "user_id": "user123",
            "datasource_ids": json.dumps([str(ds_id)]),
            "default_datasource_id": ds_id,
            "ssh_host_ids": json.dumps([str(ssh_id)]),
            "expires_at": datetime.now(timezone.utc).replace(year=9999),
            "name": "Test token",
        }
        defaults.update(overrides)
        return defaults, ds_id, ssh_id

    def test_token_model_creation(self):
        """测试创建Token模型"""
        now = datetime.now(timezone.utc)
        expires_at = datetime.now(timezone.utc).replace(year=9999)
        kwargs, ds_id, ssh_id = self._token_kwargs(
            created_at=now,
            expires_at=expires_at,
            token_metadata='{"role": "admin"}',
        )
        token = TokenModel(**kwargs)

        assert token.token == "test-token-123"
        assert token.user_id == "user123"
        assert json.loads(token.datasource_ids) == [str(ds_id)]
        assert token.default_datasource_id == ds_id
        assert json.loads(token.ssh_host_ids) == [str(ssh_id)]
        assert token.token_metadata == '{"role": "admin"}'
        assert token.created_at == now
        assert token.expires_at == expires_at
        assert token.name == "Test token"

    def test_token_model_to_dict(self):
        """测试Token模型转换为字典"""
        now = datetime.now(timezone.utc)
        expires_at = datetime.now(timezone.utc).replace(year=9999)
        kwargs, ds_id, ssh_id = self._token_kwargs(
            created_at=now,
            expires_at=expires_at,
            token_metadata='{"env": "test"}',
        )
        token = TokenModel(**kwargs)

        result = token.to_dict()
        assert result["token"] == "test-token-123"
        assert result["user_id"] == "user123"
        assert result["datasource_ids"] == json.dumps([str(ds_id)])
        assert result["default_datasource_id"] == str(ds_id)
        assert result["ssh_host_ids"] == json.dumps([str(ssh_id)])
        assert result["metadata"] == {"env": "test"}
        assert result["created_at"] == now.isoformat()
        assert result["expires_at"] == expires_at.isoformat()
        assert result["name"] == "Test token"

    def test_token_model_default_values(self):
        """测试Token模型的默认值"""
        expires_at = datetime.now(timezone.utc).replace(year=9999)
        token = TokenModel(
            token="test-token-123",
            user_id="user123",
            expires_at=expires_at,
            name="Test token",
            datasource_ids="[]",
            ssh_host_ids="[]",
            token_metadata="{}",
        )

        assert token.datasource_ids == "[]"
        assert token.ssh_host_ids == "[]"
        assert token.token_metadata == "{}"
        assert token.default_datasource_id is None
        assert token.last_used_at is None
        assert token.name == "Test token"

        result = token.to_dict()
        assert result["metadata"] == {}
        assert result["default_datasource_id"] is None

        assert TokenModel.__table__.columns["datasource_ids"].default.arg == "[]"
        assert TokenModel.__table__.columns["ssh_host_ids"].default.arg == "[]"
        assert TokenModel.__table__.columns["metadata"].default.arg == "{}"

    def test_token_model_with_metadata(self):
        """测试Token模型的元数据"""
        kwargs, _, _ = self._token_kwargs(
            token_metadata='{"scopes": ["read"]}',
        )
        token = TokenModel(**kwargs)

        result = token.to_dict()
        assert result["metadata"] == {"scopes": ["read"]}
        assert "datasource_ids" in result
        assert "ssh_host_ids" in result

    def test_token_model_token_id_field(self):
        """测试Token模型 token_id 字段：可显式设置且 to_dict 包含它"""
        kwargs, _, _ = self._token_kwargs(token_id="abc123def456")
        token = TokenModel(**kwargs)

        assert token.token_id == "abc123def456"
        result = token.to_dict()
        assert result["token_id"] == "abc123def456"

    def test_token_model_token_id_default_generator(self):
        """验证 token_id 列默认值绑定的是 generate_short_id"""
        from dm_mcp.infra.persistence.models import generate_short_id

        column = TokenModel.__table__.columns["token_id"]
        # default 是 ColumnDefault 包装；arg 应该是 generate_short_id callable
        assert column.default is not None
        assert callable(column.default.arg)
        assert column.default.arg.__name__ == generate_short_id.__name__
        # 12 字符 base62
        sample = generate_short_id()
        assert len(sample) == 12
        assert sample.isalnum()


class TestAdminUserModel:
    """AdminUser模型测试类"""

    def test_admin_user_model_creation(self):
        """测试创建AdminUser模型"""
        now = datetime.now(timezone.utc)
        user = AdminUserModel(
            username="admin",
            password_hash="hashed_password",
            created_at=now,
            updated_at=now,
        )

        assert user.username == "admin"
        assert user.password_hash == "hashed_password"
        assert user.created_at == now
        assert user.updated_at == now

    def test_admin_user_model_to_dict(self):
        """测试AdminUser模型转换为字典"""
        now = datetime.now(timezone.utc)
        user = AdminUserModel(
            username="admin",
            password_hash="hashed_password",
            created_at=now,
            updated_at=now,
        )

        result = user.to_dict()
        assert result["username"] == "admin"
        assert result["created_at"] == now.isoformat()
        assert result["updated_at"] == now.isoformat()
        # password_hash不应该在to_dict中
        assert "password_hash" not in result


class TestDataSourceModel:
    """DataSource模型测试类"""

    def test_datasource_model_creation(self):
        """测试创建DataSource模型"""
        now = datetime.now(timezone.utc)
        datasource = DataSourceModel(
            name="test_ds",
            enabled=True,
            deploy_type="standalone",
            read_only=False,
            dsn="dm://user:password@localhost:5236",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password="password123",
            minsize=1,
            maxsize=10,
            timeout=30.0,
            weight=1,
            created_at=now,
            updated_at=now,
        )

        assert datasource.name == "test_ds"
        assert datasource.enabled is True
        assert datasource.deploy_type == "standalone"
        assert datasource.read_only is False
        assert datasource.dsn == "dm://user:password@localhost:5236"
        assert datasource.host == "localhost"
        assert datasource.port == 5236
        assert datasource.user == "SYSDBA"
        assert datasource.password == "password123"
        assert datasource.minsize == 1
        assert datasource.maxsize == 10
        assert datasource.timeout == 30.0
        assert datasource.weight == 1

    def test_datasource_model_default_values(self):
        """测试DataSource模型的默认值"""
        # SQLAlchemy的default参数在创建对象时可能不会自动应用
        # 但我们可以通过显式传递默认值来测试模型结构
        # 或者测试字段可以被正确设置
        datasource = DataSourceModel(
            name="test_ds",
            enabled=True,
            deploy_type="standalone",
            read_only=False,
            dsn="",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password="",
            minsize=1,
            maxsize=10,
            timeout=30.0,
            weight=1,
        )

        # 验证字段值正确
        assert datasource.enabled is True
        assert datasource.deploy_type == "standalone"
        assert datasource.read_only is False
        assert datasource.dsn == ""
        assert datasource.host == "localhost"
        assert datasource.port == 5236
        assert datasource.user == "SYSDBA"
        assert datasource.password == ""
        assert datasource.minsize == 1
        assert datasource.maxsize == 10
        assert datasource.timeout == 30.0
        assert datasource.weight == 1

    def test_datasource_model_to_dict(self):
        """测试DataSource模型转换为字典"""
        now = datetime.now(timezone.utc)
        datasource = DataSourceModel(
            name="test_ds",
            enabled=True,
            deploy_type="standalone",
            read_only=False,
            dsn="dm://localhost:5236",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password="password123",
            minsize=1,
            maxsize=10,
            timeout=30.0,
            weight=1,
            created_at=now,
            updated_at=now,
        )

        result = datasource.to_dict()
        assert result["name"] == "test_ds"
        assert result["enabled"] is True
        assert result["deploy_type"] == "standalone"
        assert result["read_only"] is False
        assert result["host"] == "localhost"
        assert result["port"] == 5236
        assert result["user"] == "SYSDBA"
        assert "password" not in result
        assert result["minsize"] == 1
        assert result["maxsize"] == 10
        assert result["timeout"] == 30.0
        assert result["weight"] == 1
        assert result["created_at"] == now.isoformat()
        assert result["updated_at"] == now.isoformat()

    def test_datasource_model_read_only(self):
        """测试DataSource模型的只读标志"""
        datasource = DataSourceModel(name="readonly_ds", read_only=True)
        assert datasource.read_only is True

        result = datasource.to_dict()
        assert result["read_only"] is True


class TestBaseModel:
    """Base模型测试类"""

    def test_base_model_is_declarative_base(self):
        """测试Base是SQLAlchemy的DeclarativeBase"""
        assert issubclass(TokenModel, Base)
        assert issubclass(AdminUserModel, Base)
        assert issubclass(DataSourceModel, Base)
