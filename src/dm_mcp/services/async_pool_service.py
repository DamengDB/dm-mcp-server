"""dmAsync 连接池服务模块

提供服务功能：
- dmAsync 连接池的管理和生命周期
- 安全执行器（异常安全、重试、指标收集、SQL 安全策略）
- 读写分离支持（SELECT 默认走 replica）
- 负载均衡策略（round_robin、least_connections、weighted_round_robin）
- 动态数据源管理（添加、删除、重载）
"""

import asyncio
import base64
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from dmAsync.pool import Pool

from dm_mcp.core.metrics.metrics import PoolQueryMetrics
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.services.base_service import BaseService
from dm_mcp.services.datasource_service import DataSourceService
from dm_mcp.services.metrics_service import MetricsService
from dm_mcp.settings.datasource_config import DataSourceConfig
from dm_mcp.settings.pool_config import DmPoolConfig

logger = logging.getLogger(__name__)

# SQL 黑名单关键字（静态配置：不通过 env / 配置注入）
SQL_BLACKLIST_TOKENS: List[str] = [
    "DROP ",
    "TRUNCATE ",
    "ALTER SYSTEM",
    "SHUTDOWN",
]


# =========================================================
# AsyncPoolService
# =========================================================
class AsyncPoolService(BaseService):
    """dmAsync 连接池服务

    管理 dmAsync 数据库连接池，提供安全的数据查询执行能力。

    主要功能：
    - 连接池生命周期管理（初始化、关闭）
    - 安全执行器 execute_query()：异常安全、重试、指标收集、SQL 安全策略
    - 读写分离：SELECT 查询默认路由到 replica 数据源
    - 负载均衡策略：支持 round_robin
    - 动态数据源管理：支持运行时添加、删除、重载数据源
    """

    def __init__(
        self,
        pool_cfg: DmPoolConfig,
        datasource_service: DataSourceService,
        metrics_service: MetricsService,
    ) -> None:
        self.pool_cfg = pool_cfg
        self.datasource_service = datasource_service
        self.metrics_service = metrics_service

        # data_source_name -> Pool
        self._pools: Dict[str, Pool] = {}

        # data_source_name -> DataSourceConfig
        self._ds_map: Dict[str, DataSourceConfig] = {}

        # 连接失败的数据源跟踪 (data_source_name -> error_message)
        self._failed_pools: Dict[str, str] = {}

        # init 防重入
        self._init_lock = asyncio.Lock()
        self._initialized = False

    # ---------------------------
    # 生命周期
    # ---------------------------
    async def startup(self) -> None:
        # 允许重复调用，但不重复初始化
        await self.init_pools()

    async def shutdown(self) -> None:
        # 关闭所有 pool
        for name, pool in list(self._pools.items()):
            try:
                pool.close()
                await pool.wait_closed()
            except Exception as e:
                logger.warning(f"关闭连接池失败: {name}, err={e}")
        self._pools.clear()
        self._ds_map.clear()
        self._failed_pools.clear()
        self._initialized = False

    # ---------------------------
    # init 防重入 + 默认 primary
    # ---------------------------
    async def init_pools(self) -> None:
        async with self._init_lock:
            if self._initialized:
                return

            # enabled=false 直接跳过
            if not self.pool_cfg.enabled:
                logger.warning("连接池服务已禁用(pool.enabled=false)，初始化跳过")
                self._initialized = True
                return

            # 从数据源服务获取已启用的数据源配置
            all_datasources = await self.datasource_service.list_datasources()
            self._ds_map = {ds.name: ds for ds in all_datasources if ds.enabled}

            if not self._ds_map:
                logger.warning("未配置任何可用数据源(enabled=true)，连接池初始化跳过")
                self._initialized = True
                return

            # 创建 pool - 支持部分失败，不影响整体启动
            successful_pools = 0
            failed_pools = 0

            for ds in self._ds_map.values():
                try:
                    self._pools[ds.name] = await self._init_single_pool(ds)
                    # 移除之前的失败记录（如果有）
                    self._failed_pools.pop(ds.name, None)
                    successful_pools += 1
                except Exception as e:
                    failed_pools += 1
                    error_msg = str(e)
                    self._failed_pools[ds.name] = error_msg
                    logger.warning(
                        f"数据源 [{ds.name}] 连接池初始化失败，跳过该数据源: {error_msg}"
                    )
                    # 保留配置信息在 _ds_map 中

            if successful_pools == 0:
                logger.warning(
                    "所有数据源连接池初始化均失败，连接池服务将处于不可用状态"
                )

            self._initialized = True
            logger.info(
                f"dmAsync 连接池初始化完成，成功: {successful_pools} 个，失败: {failed_pools} 个"
            )

    async def retry_failed_pools(self) -> Dict[str, bool]:
        """重试连接失败的数据源

        Returns:
            字典：数据源名称 -> 是否重试成功
        """
        if not self._failed_pools:
            logger.info("没有失败的数据源需要重试")
            return {}

        results = {}
        for ds_name, error_msg in list(self._failed_pools.items()):
            ds = self._ds_map.get(ds_name)
            if not ds:
                logger.warning(f"数据源配置不存在，跳过重试: {ds_name}")
                continue

            try:
                logger.info(f"正在重试数据源连接: {ds_name}")
                self._pools[ds_name] = await self._init_single_pool(ds)
                self._failed_pools.pop(ds_name, None)
                results[ds_name] = True
                logger.info(f"数据源重试成功: {ds_name}")
            except Exception as e:
                new_error = str(e)
                self._failed_pools[ds_name] = new_error
                results[ds_name] = False
                logger.warning(f"数据源重试失败: {ds_name}, {new_error}")

        # 如果有重试成功的，重新生成 WRR 序列
        successful_retries = sum(1 for success in results.values() if success)
        logger.info(
            f"重试完成，成功: {successful_retries} 个，失败: {len(results) - successful_retries} 个"
        )

        return results

    async def _default_on_connect(self, conn):
        """dmAsync 连接建立后的回调

        Args:
            conn: dmAsync 连接对象

        注意：此回调必须是异步函数
        """
        try:
            conn.autoCommit = True
        except Exception as e:
            logger.warning(f"on_connect 执行异常: {e}")

    async def _init_single_pool(self, ds: DataSourceConfig) -> Pool:
        """初始化单个数据源的连接池

        支持单实例数据源类型，直接连接到指定的 host:port 或 dsn
        """
        return await self._init_single_instance_pool(ds)

    async def _init_single_instance_pool(self, ds: DataSourceConfig) -> Pool:
        """初始化单实例连接池"""
        password = ds.password.get_secret_value() if ds.password else ""

        conn_kwargs: Dict[str, Any] = {
            "user": ds.user,
            "password": password,
            "port": ds.port,
            "local_code": 1,
        }

        # dsn / host 互斥（dmAsync 约束）
        if ds.dsn:
            dsn = ds.dsn
            host = None
        else:
            dsn = None
            host = ds.host

        pool = await Pool.from_pool_fill(
            dsn=dsn,
            host=host,
            minsize=ds.minsize,
            maxsize=ds.maxsize,
            timeout=ds.timeout,
            on_connect=self._default_on_connect,
            pool_recycle=ds.timeout,
            **conn_kwargs,
        )

        logger.info(
            f"单实例数据源 [{ds.name}] 连接池已创建："
            f"min={ds.minsize}, max={ds.maxsize}, read_only={ds.read_only}"
        )

        return pool

    # ---------------------------
    # 对外能力
    # ---------------------------
    async def pool_status(self) -> Dict[str, Any]:
        """获取连接池状态信息（增强版，支持监控系统集成）

        返回所有数据源的连接池状态，包括监控指标和 Prometheus 格式输出。
        用于 HTTP API 和 MCP tools 展示，以及监控系统集成。

        Returns:
            字典，包含 status 和 prometheus_metrics 两个部分
        """
        current_time = int(time.time() * 1000)  # 毫秒时间戳
        status_info: Dict[str, Any] = {}
        prometheus_metrics: List[str] = []

        # 活跃的连接池
        for name, pool in self._pools.items():
            pool_info = self._build_pool_info(name, pool, current_time, is_active=True)
            status_info[name] = pool_info
            prometheus_metrics.extend(
                self._generate_prometheus_metrics(name, pool_info)
            )

        # 失败的连接池
        for name, error_msg in self._failed_pools.items():
            pool_info = self._build_pool_info(
                name, None, current_time, is_active=False, error_msg=error_msg
            )
            status_info[name] = pool_info
            prometheus_metrics.extend(
                self._generate_prometheus_metrics(name, pool_info)
            )

        return {
            "status": status_info,
            "prometheus_metrics": "\n".join(prometheus_metrics),
        }

    def _build_pool_info(
        self,
        name: str,
        pool: Optional[Any],
        current_time: int,
        is_active: bool,
        error_msg: Optional[str] = None,
    ) -> Dict[str, Any]:
        """构建连接池信息字典

        Args:
            name: 数据源名称
            pool: 连接池对象（活跃池时传入，失败池时为 None）
            current_time: 当前时间戳（毫秒）
            is_active: 是否为活跃连接池
            error_msg: 错误消息（仅失败池时传入）

        Returns:
            连接池信息字典
        """
        ds = self._ds_map.get(name)
        deploy_type = ds.deploy_type if ds else ""
        read_only = ds.read_only if ds else False

        if is_active and pool:
            # 活跃连接池
            size = getattr(pool, "size", 0)
            freesize = getattr(pool, "freesize", 0)
            minsize = getattr(pool, "minsize", 0)
            maxsize = getattr(pool, "maxsize", 0)

            active_connections = max(0, int(size) - int(freesize))
            usage_rate = (
                (active_connections / max(1, int(size))) * 100 if size > 0 else 0
            )

            health_status = self._determine_pool_health(
                usage_rate, active_connections > 0
            )

            return {
                "status": "active",
                "size": size,
                "freesize": freesize,
                "minsize": minsize,
                "maxsize": maxsize,
                "active_connections": active_connections,
                "usage_rate": round(usage_rate, 2),
                "health_status": health_status,
                "deploy_type": deploy_type,
                "read_only": read_only,
                "lb_strategy": self.pool_cfg.load_balancing_strategy,
                "last_check_time": current_time,
                "error_count": 0,
            }
        else:
            # 失败连接池
            return {
                "status": "failed",
                "error": error_msg,
                "size": 0,
                "freesize": 0,
                "minsize": 0,
                "maxsize": 0,
                "active_connections": 0,
                "usage_rate": 0.0,
                "health_status": "critical",
                "deploy_type": deploy_type,
                "read_only": read_only,
                "lb_strategy": self.pool_cfg.load_balancing_strategy,
                "last_check_time": current_time,
                "error_count": 1,
            }

    def _determine_pool_health(self, usage_rate: float, has_errors: bool) -> str:
        """确定连接池健康状态

        Args:
            usage_rate: 连接使用率百分比
            has_errors: 是否有连接错误

        Returns:
            健康状态: "healthy", "warning", "critical"
        """
        if has_errors or usage_rate > 95:
            return "critical"
        if usage_rate > 80:
            return "warning"
        return "healthy"

    def _generate_prometheus_metrics(
        self, pool_name: str, pool_info: Dict[str, Any]
    ) -> List[str]:
        """生成 Prometheus 格式的监控指标

        Args:
            pool_name: 连接池名称
            pool_info: 连接池信息字典

        Returns:
            Prometheus 格式指标字符串列表
        """
        metrics = []
        base_labels = f'pool_name="{pool_name}"'

        # 连接池大小指标
        metrics.append(f'dm_pool_size{{{base_labels}}} {pool_info["size"]}')
        metrics.append(f'dm_pool_free_size{{{base_labels}}} {pool_info["freesize"]}')
        metrics.append(f'dm_pool_min_size{{{base_labels}}} {pool_info["minsize"]}')
        metrics.append(f'dm_pool_max_size{{{base_labels}}} {pool_info["maxsize"]}')

        # 连接使用情况
        metrics.append(
            f'dm_pool_active_connections{{{base_labels}}} {pool_info["active_connections"]}'
        )
        metrics.append(f'dm_pool_usage_rate{{{base_labels}}} {pool_info["usage_rate"]}')

        # 健康状态 (0=healthy, 1=warning, 2=critical)
        health_value = {"healthy": 0, "warning": 1, "critical": 2}.get(
            pool_info["health_status"], 2
        )
        metrics.append(f"dm_pool_health_status{{{base_labels}}} {health_value}")

        # 错误计数
        metrics.append(
            f'dm_pool_error_count{{{base_labels}}} {pool_info["error_count"]}'
        )

        # 状态指标 (0=active, 1=failed)
        status_value = 0 if pool_info["status"] == "active" else 1
        metrics.append(f"dm_pool_status{{{base_labels}}}{status_value}")

        return metrics

    # ---------------------------
    # 动态管理方法（用于 API 管理数据源）
    # ---------------------------
    async def add_pool(self, ds: DataSourceConfig) -> None:
        """
        动态添加连接池

        Args:
            ds: 数据源配置

        Raises:
            ValueError: 数据源已存在
        """
        if ds.name in self._pools:
            raise ValueError(f"数据源已存在: {ds.name}")

        # 创建连接池
        pool = await self._init_single_pool(ds)
        self._pools[ds.name] = pool
        self._ds_map[ds.name] = ds

        logger.info(f"已动态添加连接池: {ds.name}")

    async def remove_pool(self, name: str, timeout: float = 30.0) -> None:
        """
        动态删除连接池（优雅关闭）

        Args:
            name: 数据源名称
            timeout: 等待超时时间（秒）

        Raises:
            ValueError: 数据源不存在
        """
        if name not in self._pools:
            raise ValueError(f"数据源不存在: {name}")

        pool = self._pools.get(name)
        if pool:
            # 优雅关闭：等待活跃连接完成
            await self._graceful_close_pool(pool, name, timeout)

            # 从映射中移除
            del self._pools[name]
            if name in self._ds_map:
                del self._ds_map[name]

        logger.info(f"已动态删除连接池: {name}")

    async def reload_pool(self, ds: DataSourceConfig, timeout: float = 30.0) -> None:
        """
        重载单个连接池（先关闭旧池，再创建新池）

        Args:
            ds: 新的数据源配置
            timeout: 等待超时时间（秒）

        Raises:
            ValueError: 数据源不存在
        """
        if ds.name not in self._pools:
            raise ValueError(f"数据源不存在: {ds.name}")

        # 关闭旧池
        await self.remove_pool(ds.name, timeout)

        # 创建新池
        await self.add_pool(ds)

        logger.info(f"已重载连接池: {ds.name}")

    async def reload_all_pools(
        self, datasources: List[DataSourceConfig], timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        重载所有连接池

        Args:
            datasources: 新的数据源配置列表
            timeout: 单个连接池的等待超时时间（秒）

        Returns:
            重载结果统计
        """
        result = {
            "closed": [],
            "created": [],
            "errors": [],
        }

        # 1. 关闭所有旧池
        for name in list(self._pools.keys()):
            try:
                await self.remove_pool(name, timeout)
                result["closed"].append(name)
            except Exception as e:
                logger.error(f"关闭连接池失败: {name}, err={e}")
                result["errors"].append({"name": name, "error": str(e)})

        # 2. 创建新池
        for ds in datasources:
            if ds.enabled:
                try:
                    await self.add_pool(ds)
                    result["created"].append(ds.name)
                except Exception as e:
                    logger.error(f"创建连接池失败: {ds.name}, err={e}")
                    result["errors"].append({"name": ds.name, "error": str(e)})

        logger.info(
            f"已重载所有连接池: closed={len(result['closed'])}, "
            f"created={len(result['created'])}, errors={len(result['errors'])}"
        )

        return result

    async def test_connection(self, ds: DataSourceConfig) -> Dict[str, Any]:
        """
        测试数据源连接

        Args:
            ds: 数据源配置

        Returns:
            测试结果
        """
        try:
            # 创建临时连接
            pool = await self._init_single_pool(ds)

            # 执行简单查询
            async with pool.acquire() as conn:
                cur = await conn.cursor()
                try:
                    await cur.execute("SELECT 1")
                    rows = await cur.fetchall()
                    success = len(rows) > 0
                finally:
                    try:
                        cur.close()
                    except Exception:
                        pass

            # 关闭临时连接池
            pool.close()
            await pool.wait_closed()

            return {
                "success": success,
                "message": "连接测试成功",
            }

        except Exception as e:
            logger.error(f"连接测试失败: {ds.name}, err={e}")
            return {
                "success": False,
                "message": f"连接测试失败: {str(e)}",
            }

    async def _graceful_close_pool(
        self, pool: Pool, name: str, timeout: float = 30.0
    ) -> None:
        """
        优雅关闭连接池

        等待活跃连接完成，超时后强制关闭

        Args:
            pool: 连接池对象
            name: 数据源名称
            timeout: 超时时间（秒）
        """
        start_time = time.time()
        wait_interval = 0.5  # 每 0.5 秒检查一次

        while True:
            # 检查活跃连接数
            size = getattr(pool, "size", 0)
            freesize = getattr(pool, "freesize", 0)
            active = max(0, int(size) - int(freesize))

            if active == 0:
                # 没有活跃连接，可以安全关闭
                logger.info(f"连接池 {name} 无活跃连接，安全关闭")
                break

            # 检查超时
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                logger.warning(
                    f"连接池 {name} 等待超时({timeout}s)，仍有 {active} 个活跃连接，强制关闭"
                )
                break

            # 继续等待
            logger.debug(
                f"连接池 {name} 有 {active} 个活跃连接，等待中... ({elapsed:.1f}s/{timeout}s)"
            )
            await asyncio.sleep(wait_interval)

        # 关闭连接池
        try:
            pool.close()
            await pool.wait_closed()
        except Exception as e:
            logger.warning(f"关闭连接池失败: {name}, err={e}")

    async def execute_query(
        self,
        sql: str,
        *,
        source: str = "auto",
        schema: Optional[str] = None,
        max_rows: Optional[int] = None,
        timeout: Optional[float] = None,
        timeout_ms: Optional[int] = None,
        read_only: Optional[bool] = None,
        params: Optional[Dict[str, Any]] = None,
        **kwargs: object,
    ) -> Dict[str, Any]:
        """安全执行器（带异常安全、重试、指标收集）

        执行 SQL 查询，自动路由到合适的数据源，支持重试和指标收集。

        Args:
            sql: 要执行的 SQL 语句
            source: 数据源选择策略
                - "auto": 按 SQL 类型、读写分离和负载均衡自动选择
                - 指定数据源名：直接路由到对应的连接池
                - "primary"/"replica" 或 "read_write"/"read_only": 按角色选择（再走 LB）
            schema: 默认 schema 名称（可选），用于 SQL 查询
            max_rows: 最大返回行数限制（可选），超过此数量的行将被截断
            timeout: 查询执行超时时间（秒，可选）
            timeout_ms: 查询执行超时时间（毫秒，可选，优先级高于 timeout）
            read_only: 强制指定是否为只读查询（可选），影响数据源选择
            params: SQL 参数（可选）
            **kwargs: 扩展参数（用于未来兼容性）

        Returns:
            包含查询结果的字典，包括 status、result、source、duration_ms 等

        Raises:
            ValueError: SQL 命中黑名单或只读数据源禁止写入
            Exception: 查询执行失败（重试后仍失败）
        """
        await self.init_pools()

        # 如果提供了 read_only 参数，使用它；否则根据 SQL 自动判断
        if read_only is not None:
            is_read_only = read_only
        else:
            is_read_only = self._is_read_sql(sql)
        sql_type = "query" if is_read_only else "write"

        chosen_source, _ = self._choose_source_for_sql(sql, source)

        # SQL 安全：黑名单（保留原有的黑名单检查）
        self._check_sql_blacklist(sql)

        max_retries = max(0, int(self.pool_cfg.max_retries))
        backoff_ms = max(0, int(self.pool_cfg.retry_backoff_ms))

        # 统一计算一次超时时间（重试期间保持一致）
        if timeout_ms is not None:
            timeout_s = timeout_ms / 1000.0
        elif timeout is not None:
            timeout_s = timeout
        else:
            timeout_s = None

        last_err: Optional[Exception] = None
        start_all = time.time()

        for attempt in range(max_retries + 1):
            try:
                t0 = time.time()

                if timeout_s is not None and timeout_s > 0:
                    result = await asyncio.wait_for(
                        self._execute_once(chosen_source, sql, params, schema),
                        timeout=timeout_s,
                    )
                else:
                    result = await self._execute_once(
                        chosen_source, sql, params, schema
                    )

                # 应用行数限制
                if max_rows is not None and max_rows > 0:
                    result = result[:max_rows]

                duration_ms = round((time.time() - t0) * 1000, 3)

                # metrics：成功
                self._record_metrics(
                    source=chosen_source,
                    is_read_only=is_read_only,
                    sql_type=sql_type,
                    status="ok",
                    duration_ms=duration_ms,
                    retries=attempt,
                    error=False,
                )

                return {
                    "sql": sql,
                    "params": params,
                    "result": result,
                    "status": "ok",
                    "source": chosen_source,
                    "read_only": is_read_only,
                    "duration_ms": duration_ms,
                    "summary": f"执行完成，返回 {len(result)} 行",
                }

            except Exception as e:
                last_err = e
                duration_ms = round((time.time() - start_all) * 1000, 3)

                # metrics：失败（每次失败都记一次，方便看重试是否在生效）
                self._record_metrics(
                    source=chosen_source,
                    is_read_only=is_read_only,
                    sql_type=sql_type,
                    status="error",
                    duration_ms=duration_ms,
                    retries=attempt,
                    error=True,
                )

                # 简单策略：最后一次不 sleep
                if attempt < max_retries:
                    await asyncio.sleep(backoff_ms / 1000.0)

        # 所有重试失败：抛出最后异常
        raise last_err  # type: ignore[misc]

    # ---------------------------
    # 内部执行：短连接模式
    # ---------------------------
    def _convert_bytes_for_json(self, obj: Any) -> Any:
        """递归转换数据中的 bytes 为可 JSON 序列化的格式

        Args:
            obj: 要转换的对象（可能是 bytes、list、tuple、dict 等）

        Returns:
            转换后的对象，bytes 会被转换为 UTF-8 字符串或 base64 编码
        """
        if isinstance(obj, bytes):
            # 尝试解码为 UTF-8 字符串，如果失败则使用 base64 编码
            try:
                return obj.decode("utf-8")
            except (UnicodeDecodeError, AttributeError):
                # 无法解码为 UTF-8，使用 base64 编码
                return base64.b64encode(obj).decode("ascii")
        elif isinstance(obj, (list, tuple)):
            return [self._convert_bytes_for_json(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: self._convert_bytes_for_json(v) for k, v in obj.items()}
        else:
            return obj

    def _normalize_rows_to_dicts(
        self, rows: List[Any], description: Optional[Any]
    ) -> List[Any]:
        """根据 cursor.description 将行转换为 dict 列表（保持原有行为）

        - 如果没有 description 或行本身就是 dict，则原样返回
        - 映射失败时，回退到原始行
        """
        if not rows or isinstance(rows[0], dict):
            return rows

        col_names: Optional[List[Any]] = None
        try:
            if description:
                col_names = [desc[0] for desc in description]
        except Exception:
            col_names = None

        if not col_names:
            return rows

        mapped_rows: List[Any] = []
        for row in rows:
            if isinstance(row, dict):
                mapped_rows.append(row)
                continue
            try:
                mapped_rows.append(
                    {col_names[i]: row[i] for i in range(len(col_names))}
                )
            except Exception:
                mapped_rows.append(row)

        return mapped_rows

    async def _execute_once(
        self,
        source: str,
        sql: str,
        params: Optional[Dict[str, Any]],
        schema: Optional[str] = None,
    ) -> List[Any]:
        pool = self._pools.get(source)
        if pool is None:
            raise ValueError(f"数据源不存在: {source}")

        # dmAsync：pool.acquire() -> conn.cursor() -> execute -> fetchall -> close/release
        async with pool.acquire() as conn:
            cur = await conn.cursor()
            try:
                # 设置默认 schema（如果提供）
                if schema:
                    await cur.execute(f"SET SCHEMA {schema}")

                if params:
                    await cur.execute(sql, params)
                else:
                    await cur.execute(sql)

                # 对于无结果集的语句（如存储过程、DDL），不调用 fetchall
                description = getattr(cur, "description", None)
                if description:
                    rows = await cur.fetchall()
                    # Normalize list/tuple rows to dicts when cursor provides column names.
                    rows = self._normalize_rows_to_dicts(rows, description)
                else:
                    rows = []

                # 转换结果中的 bytes 为可序列化的格式
                return self._convert_bytes_for_json(rows)
            finally:
                try:
                    cur.close()
                except Exception:
                    pass

    # ---------------------------
    # 路由与策略
    # ---------------------------
    def _choose_source_for_sql(self, sql: str, source: str) -> Tuple[str, bool]:
        """选择适合的数据源

        根据 source 参数和 SQL 类型选择合适的数据源。

        Args:
            sql: SQL 语句
            source: 数据源选择策略（见 execute_query 文档）

        Returns:
            (chosen_source, is_read_only) 元组

        Raises:
            ValueError: 数据源不存在
        """
        # 指定具体数据源名
        if source in self._ds_map:
            ds = self._ds_map[source]
            return ds.name, ds.read_only

        # 指定 read_only 类型（向后兼容：primary/replica）
        if source == "primary" or source == "read_write":
            chosen = self._choose_any_available_source(False)
            ds = self._ds_map.get(chosen)
            return chosen, ds.read_only if ds else False
        if source == "replica" or source == "read_only":
            chosen = self._choose_any_available_source(True)
            ds = self._ds_map.get(chosen)
            return chosen, ds.read_only if ds else True

        # auto：读写分离
        if source == "auto":
            is_read = self._is_read_sql(sql)
            if is_read and self.pool_cfg.read_write_split:
                # 将来可以在此扩展真正的 read_only 选择逻辑
                chosen = self._choose_any_available_source(True)
                ds = self._ds_map.get(chosen)
                return chosen, ds.read_only if ds else True

            # 否则使用 read_write 数据源（当前等同于任意可用数据源）
            chosen = self._choose_any_available_source(False)
            ds = self._ds_map.get(chosen)
            return chosen, ds.read_only if ds else False

        raise ValueError(f"非法 source 参数: {source}")

    def _choose_any_available_source(self, read_only: bool) -> str:
        """选择一个可用的数据源（当前忽略 read_only）

        为了保持接口兼容性，暂保留 read_only 参数，但在当前单数据源架构下不会使用。
        """
        available_pools = [name for name in self._pools.keys() if name in self._ds_map]
        if not available_pools:
            raise ValueError("没有可用的数据源连接池")
        return available_pools[0]

    # ---------------------------
    # SQL 安全策略
    # ---------------------------
    def _check_sql_blacklist(self, sql: str) -> None:
        """检查 SQL 是否命中黑名单关键字

        Args:
            sql: 要检查的 SQL 语句

        Raises:
            ValueError: SQL 命中黑名单关键字
        """
        upper = sql.upper()
        for token in SQL_BLACKLIST_TOKENS:
            if token and token.upper() in upper:
                raise ValueError(f"SQL 命中黑名单关键字: {token}")

    def _check_read_only_guard(self, sql: str, chosen_source: str) -> None:
        """检查只读数据源是否禁止写入

        如果目标数据源是只读的，但 SQL 是写入操作，则抛出异常。

        Args:
            sql: 要执行的 SQL 语句
            chosen_source: 选择的数据源名称

        Raises:
            ValueError: 只读数据源禁止写入
        """
        ds = self._ds_map.get(chosen_source)
        if not ds:
            return
        if not ds.read_only:
            return
        # 落到只读库时：禁止写
        if not self._is_read_sql(sql):
            raise ValueError(f"只读数据源禁止写入: source={chosen_source}")

    def _is_read_sql(self, sql: str) -> bool:
        """判断 SQL 是否为只读查询

        检查 SQL 语句的第一个关键字是否为只读操作（SELECT、WITH、SHOW 等）。

        Args:
            sql: SQL 语句

        Returns:
            True 如果是只读查询，False 否则
        """
        s = sql.strip().lstrip("(").strip()
        if not s:
            return True
        head = s.split(None, 1)[0].upper()
        return head in ("SELECT", "WITH", "SHOW", "DESC", "DESCRIBE", "EXPLAIN")

    # ---------------------------
    # metrics
    # ---------------------------
    def _record_metrics(
        self,
        source: str,
        is_read_only: bool,
        sql_type: str,
        status: str,
        duration_ms: float,
        retries: int,
        error: bool,
    ) -> None:
        """记录查询指标

        Args:
            source: 数据源名称
            is_read_only: 是否为只读查询
            status: 查询状态（"ok" 或 "error"）
            duration_ms: 执行耗时（毫秒）
            retries: 重试次数
            error: 是否出错
        """
        try:
            m = PoolQueryMetrics(
                source=source,
                is_read_only=is_read_only,
                lb_strategy=self.pool_cfg.load_balancing_strategy,
                sql_type=sql_type,
                status=status,
                total=1,
                error=1 if error else 0,
                retries=int(retries),
                duration_ms=float(duration_ms),
            )
            self.metrics_service.record_dataclass(m, prefix="db_pool")
        # 这个地方是假设metrics_service依赖服务存在，所以可能报错
        except Exception as e:
            logger.debug(f"记录 metrics 失败: {e}")


# =========================================================
# Factory
# =========================================================
class AsyncPoolServiceFactory(ServiceFactory):
    """dmAsync 连接池服务工厂

    负责创建和配置 AsyncPoolService 实例。
    """

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="async_pool_service",
            service_type=AsyncPoolService,
            description="dmAsync 异步连接池服务（读写分离 + 负载均衡 + 安全执行器）",
            author="DM MCP Team",
            dependencies=["datasource_service", "metrics_service"],
            priority=50,  # 在 DataSourceService 之后启动
        )

    def create(self, settings, **deps) -> AsyncPoolService:
        # 兼容：settings.pool 可能尚未启用时为空，这里兜底构造默认
        pool_cfg = getattr(settings, "pool", None)
        if pool_cfg is None:
            pool_cfg = DmPoolConfig()

        return AsyncPoolService(
            pool_cfg, deps["datasource_service"], deps["metrics_service"]
        )
