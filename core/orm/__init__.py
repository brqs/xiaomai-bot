from creart import create
from loguru import logger
from sqlalchemy import MetaData, inspect, delete, update, select, insert
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker

from core.config import GlobalConfig


class AsyncORM:
    """对象关系映射（Object Relational Mapping）"""

    def __init__(self, db_link: str):
        """
        AsyncORM类可以支持多种数据库，只需要将不同的数据库链接字符串传入db_link函数即可。
        :param db_link: 数据库链接
        """
        self.db_link = db_link
        """
        创建异步数据库引擎
        echo参数是SQLAlchemy引擎的一个布尔值选项，表示是否在引擎创建时打印所有SQL语句。
        当echo=True时，会将所有的SQL语句输出到标准输出（也就是控制台），方便开发人员调试和查看。
        但是在生产环境中，这个选项就没有意义了，因为输出的SQL语句会对性能产生负面影响。
        所以，在生产环境中，建议将echo设为False，以关闭SQL语句输出。
        """
        try:
            self.engine = create_async_engine(db_link, echo=False)
        except Exception as e:
            logger.error(f"连接数据库失败: {e}")
            raise e
        """
        创建一个元数据对象，用于管理表的元数据。
        """
        self.metadata = MetaData()
        """
        将元数据对象与数据库引擎进行绑定。
        """
        self.metadata.bind = self.engine
        """
        declarative_base()是一个函数，它返回一个DeclarativeMeta类，这个类可以用来创建SQLAlchemy中的数据库模型
        """
        self.Base = declarative_base()
        """
        创建一个Session的工厂，使用这个工厂创建的Session对象与数据库连接关联。
        可以通过这个Session对象来执行SQL操作，如查询、插入、更新等。
        """
        self.async_session = sessionmaker(bind=self.engine, class_=AsyncSession)
        logger.success(f"已连接至数据库: {self.engine.url}")

    # 建表、删表、获取表
    async def create_all(self):
        """创建所有表"""
        async with self.engine.begin() as conn:
            await conn.run_sync(self.Base.metadata.create_all)

    async def drop_all(self):
        """删除所有表"""
        async with self.engine.begin() as conn:
            await conn.run_sync(self.Base.metadata.drop_all)

    async def get_tables(self):
        """获取所有表"""
        async with self.engine.connect() as conn:
            return await conn.run_sync(lambda x: inspect(x).get_table_names())

    # 利用模型直接进行增删改查
    async def execute(self, sql, parameters=None):
        """
        执行SQL语句
        :param sql: sql语句
        :param parameters: 参数
        :return: result
        """
        async with self.async_session() as session:
            async with session.begin():
                result = await session.execute(sql, parameters)
                await session.commit()
                return result

    async def fetch_one(self, sql, parameters=None):
        """获取单条记录"""
        async with self.engine.connect() as conn:
            result = await conn.execute(sql, parameters)
            return await result.fetchone()

    async def fetch_all(self, sql, parameters=None):
        """获取多条记录"""
        async with self.engine.connect() as conn:
            result = await conn.execute(sql, parameters)
            return await result.fetchall()

    async def rowcount(self, sql, parameters=None):
        """获取记录条数"""
        async with self.engine.connect() as conn:
            result = await conn.execute(sql, parameters)
            return result.rowcount

    async def add(self, table, data: dict):
        """
        插入数据
        :param table: 表
        :param data: 数据
        """
        async with self.async_session() as session:
            async with session.begin():
                session.add(table(**data))
            await session.commit()

    async def delete(self, table, condition):
        """
        删除数据
        :param table: 表
        :param condition: 条件
        """
        return await self.execute(delete(table).where(*condition))

    async def update(self, table, data, condition):
        """
        更新数据
        :param table: 表
        :param data: 更新的数据
        :param condition: 条件
        """
        async with self.async_session() as session:
            async with session.begin():
                await session.execute(update(table).where(condition).values(**data))
            await session.commit()

    async def insert_or_update(self, table, data, condition):
        """
        如果满足条件则更新，否则插入
        :param table: 表
        :param data: 数据
        :param condition: 条件
        """
        if (await self.execute(select(table).where(*condition))).all():
            return await self.execute(update(table).where(*condition).values(**data))
        else:
            return await self.execute(insert(table).values(**data))

    async def insert_or_ignore(self, table, data, condition):
        """
        不满足条件则插入,否则跳过
        :param table: 表
        :param data: 数据
        :param condition: 条件
        """
        if not (await self.execute(select(table).where(*condition))).all():
            return await self.execute(insert(table).values(**data))

    async def select(self, el, condition=None):
        """
        查询数据"
        :param el: 查找的元素
        :param condition: 条件
        :return: result.fetchall() / None
        """
        if condition is None:
            result = await self.execute(select([el]))
        else:
            result = await self.execute(select([el]).where(condition))
        if result:
            return result.fetchall()
        else:
            return None

    async def init_check(self):
        for table in self.Base.__subclasses__():
            if not await self.table_exists(table.__tablename__):
                table.__table__.create(self.engine)
        return None

    @staticmethod
    def use_inspector(conn):
        inspector = inspect(conn)
        return inspector.get_table_names()

    async def table_exists(self, table_name: str) -> bool:
        """
        检查表是否存在
        :param table_name: 表名
        :return: bool
        """
        async with self.engine.connect() as conn:
            tables = await conn.run_sync(self.use_inspector)
        return table_name in tables


# 初始化AsyncORM
orm = AsyncORM(create(GlobalConfig).db_link)
