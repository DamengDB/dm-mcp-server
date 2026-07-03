import asyncio
from typing import Optional

from dmAsync.pool import Pool


async def gather_table_stats(
    schema_name: str,
    table_name: str,
    *,
    dsn: Optional[str] = None,
    host: Optional[str] = "localhost",
    port: int = 5237,
    user: str = "SYSDBA",
    password: str = "Abc123456",
) -> None:
    """
    使用 dmAsync 直接执行:

        CALL DBMS_STATS.GATHER_TABLE_STATS(?, ?, NULL, 100, TRUE);

    参数:
        schema_name: 模式名(Owner)
        table_name: 表名
        dsn/host: 根据实际环境二选一配置
    """

    # 根据实际环境选择 dsn 或 host
    async def _on_connect(conn):
        # 保持与项目中 AsyncPoolService 一致，启用自动提交
        conn.autoCommit = True

    pool = await Pool.from_pool_fill(
        dsn=dsn,
        host=None if dsn else host,
        minsize=1,
        maxsize=5,
        timeout=30,
        on_connect=_on_connect,
        pool_recycle=30,
        user=user,
        password=password,
        port=port,
        local_code=1,
    )

    sql = """
    CALL DBMS_STATS.GATHER_TABLE_STATS(?, ?, NULL, 100, TRUE);
    """

    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 注意: 参数顺序是 (schema_name, table_name)
                await cur.execute(sql, (schema_name, table_name))
                print("@@", cur.description)
                await cur.execute("select 1;")
                print("@@", cur.description)
                # 如果需要显式提交，可以取消下一行注释
                # await conn.commit()
        print(f"统计信息收集成功: {schema_name}.{table_name}")
    except Exception as exc:
        print(f"统计信息收集失败: {schema_name}.{table_name}, error={exc}")
    finally:
        pool.close()
        await pool.wait_closed()


async def main() -> None:
    # TODO: 根据你的实际表信息修改这里
    schema_name = "DMHR"
    table_name = "EMPLOYEE"

    # 如果你使用 DSN 连接，把 dsn 改成实际值，并把 host=None
    await gather_table_stats(
        schema_name=schema_name,
        table_name=table_name,
        dsn=None,  # 例如: "DM8"
        host="localhost",
        port=5237,
        user="SYSDBA",
        password="Abc123456",
    )


if __name__ == "__main__":
    asyncio.run(main())
