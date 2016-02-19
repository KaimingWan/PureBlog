from models import User
import asyncio
import orm
import pdb
import time


# import pdb


# 测试插入


@asyncio.coroutine
def test_save(loop):
    yield from orm.create_pool(loop, user='kami', password='kami', db='pure_blog')
    u = User(name='hi', email='hi@example.com',
             passwd='hi', image='about:blank')
    # pdb.set_trace()
    yield from u.save()

# 测试查询


@asyncio.coroutine
def test_findAll(loop):
    yield from orm.create_pool(loop, user='kami', password='kami', db='pure_blog')
    # 这里给的关键字参数按照xxx='xxx'的形式给出，会自动分装成dict
    rs = yield from User.findAll(email='test@example.com')		# rs是一个元素为dict的list
    # pdb.set_trace()
    for i in range(len(rs)):
        print(rs[i])

# 查询条数?


@asyncio.coroutine
def test_findNumber(loop):
    yield from orm.create_pool(loop, user='kami', password='kami', db='pure_blog')
    count = yield from User.findNumber('email')
    print(count)

# 根据主键查找，这里试ID


@asyncio.coroutine
def test_find_by_key(loop):
    yield from orm.create_pool(loop, user='kami', password='kami', db='pure_blog')
    # rs是一个dict
    # ID请自己通过数据库查询
    rs = yield from User.find_by_key('0014531826762080b29033a78624bc68c867550778f64d6000')
    print(rs)

# 根据主键删除


@asyncio.coroutine
def test_remove(loop):
    yield from orm.create_pool(loop, user='kami', password='kami', db='pure_blog')
    # 用id初始化一个实例对象
    u = User(id='0014531826762080b29033a78624bc68c867550778f64d6000')
    yield from u.remove()


# 根据主键更新
@asyncio.coroutine
def test_update(loop):
    yield from orm.create_pool(loop, user='kami', password='kami', db='pure_blog')
    # 必须按照列的顺序来初始化：'update `users` set `created_at`=?, `passwd`=?, `image`=?,
    # `admin`=?, `name`=?, `email`=? where `id`=?' 注意这里要使用time()方法，否则会直接返回个时间戳对象，而不是float值
    u = User(id='00145318300622886f186530ee74afabecedb42f9cd590a000', created_at=time.time(), passwd='test',
             image='about:blank', admin=True, name='test', email='hello1@example.com')  # id必须和数据库一直，其他属性可以设置成新的值,属性要全
    # pdb.set_trace()
    yield from u.update()


loop = asyncio.get_event_loop()
loop.run_until_complete(test_update(loop))
__pool = orm.__pool
__pool.close()  # 需要先关闭连接池
loop.run_until_complete(__pool.wait_closed())
loop.close()
