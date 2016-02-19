import logging
logging.basicConfig(level=logging.INFO)  # 必须紧跟其后
import asyncio
import json
import os
import time
from datetime import datetime

from aiohttp import web
from jinja2 import Environment, FileSystemLoader

from config import configs
import orm

from web_frame import add_routes, add_static

from handlers import cookie2user, COOKIE_NAME


def init_jinja2(app, **kw):
    logging.info('init jinja2...')
    # 初始化模板配置，包括模板运行代码的开始结束标识符，变量的开始结束标识符等
    options = dict(
        # 是否转义设置为True，就是在渲染模板时自动把变量中的<>&等字符转换为&lt;&gt;&amp;
        autoescape=kw.get('autoescape', True),
        block_start_string=kw.get('block_start_string', '{%'),  # 运行代码的开始标识符
        block_end_string=kw.get('block_end_string', '%}'),  # 运行代码的结束标识符
        variable_start_string=kw.get('variable_start_string', '{{'),  # 变量开始标识符
        variable_end_string=kw.get('variable_end_string', '}}'),  # 变量结束标识符
        # Jinja2会在使用Template时检查模板文件的状态，如果模板有修改， 则重新加载模板。如果对性能要求较高，可以将此值设为False
        auto_reload=kw.get('auto_reload', True)
    )
    # 从参数中获取path字段，即模板文件的位置
    path = kw.get('path', None)
    # 如果没有，则默认为当前文件目录下的 templates 目录
    if path is None:
        path = os.path.join(os.path.dirname(
            os.path.abspath(__file__)), 'templates')
    logging.info('set jinja2 template path: %s' % path)
    # Environment是Jinja2中的一个核心类，它的实例用来保存配置、全局对象，以及从本地文件系统或其它位置加载模板。
    # 这里把要加载的模板和配置传给Environment，生成Environment实例
    env = Environment(loader=FileSystemLoader(path), **options)
    # 从参数取filter字段
    # filters: 一个字典描述的filters过滤器集合, 如果非模板被加载的时候, 可以安全的添加filters或移除较早的.
    filters = kw.get('filters', None)
    # 如果有传入的过滤器设置，则设置为env的过滤器集合
    if filters is not None:
        for name, f in filters.items():
            env.filters[name] = f
    # 给webapp设置模板
    app['__templating__'] = env

# ------------------------------------------拦截器middlewares设置-------------------------


@asyncio.coroutine
def logger_factory(app, handler):  # 在正式处理之前打印日志
    @asyncio.coroutine
    def logger(request):
        logging.info('Requst : %s, %s' % (request.method, request.path))
        return (yield from handler(request))
    return logger


@asyncio.coroutine
def data_factory(app, handler):
    @asyncio.coroutine
    def parse_data(request):
        if request.method == 'POST':
            if request.content_type.startswith('application/json'):
                request.__data__ = yield from request.json()
                logging.info('request json : %s' % str(request.__data__))
            elif request.content_type.startswith('application/x-www-form-urlencoded'):
                request.__data__ = yield from request.post()
                logging.info('request form : %s' % str(request.__data__))
        return (yield from handler(request))
    return parse_data

# 是为了验证当前的这个请求用户是否在登录状态下，或是否是伪造的sha1


@asyncio.coroutine
def auth_factory(app, handler):
    @asyncio.coroutine
    def auth(request):
        logging.info('check user: %s %s' % (request.method, request.path))
        request.__user__ = None
        # 获取到cookie字符串
        cookie_str = request.cookies.get(COOKIE_NAME)
        if cookie_str:
            # 通过反向解析字符串和与数据库对比获取出user
            user = yield from cookie2user(cookie_str)
            if user:
                logging.info('set current user: %s' % user.email)
                # user存在则绑定到request上，说明当前用户是合法的
                request.__user__ = user
        if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
            return web.HTTPFound('/signin')
        # 执行下一步
        return (yield from handler(request))
    return auth


# 响应处理
# 总结下来一个请求在服务端收到后的方法调用顺序是:
#     	logger_factory->response_factory->RequestHandler().__call__->get或post->handler
# 那么结果处理的情况就是:
#     	由handler构造出要返回的具体对象
#     	然后在这个返回的对象上加上'__method__'和'__route__'属性，以标识别这个对象并使接下来的程序容易处理
#     	RequestHandler目的就是从URL函数中分析其需要接收的参数，从request中获取必要的参数，调用URL函数,然后把结果返回给response_factory
#     	response_factory在拿到经过处理后的对象，经过一系列对象类型和格式的判断，构造出正确web.Response对象，以正确的方式返回给客户端
# 在这个过程中，我们只用关心我们的handler的处理就好了，其他的都走统一的通道，如果需要差异化处理，就在通道中选择适合的地方添加处理代码。
# 在response_factory中应用了jinja2来套用模板
@asyncio.coroutine
def response_factory(app, handler):
    @asyncio.coroutine
    def response(request):
        logging.info('Response handler...')
        # 调用相应的handler处理request
        r = yield from handler(request)
        logging.info('r = %s' % str(r))
        # 如果响应结果为web.StreamResponse类，则直接把它作为响应返回
        if isinstance(r, web.StreamResponse):
            return r
        # 如果响应结果为字节流，则把字节流塞到response的body里，设置响应类型为流类型，返回
        if isinstance(r, bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        # 如果响应结果为字符串
        if isinstance(r, str):
            # 先判断是不是需要重定向，是的话直接用重定向的地址重定向
            if r.startswith('redirect:'):
                return web.HTTPFound(r[9:])
            # 不是重定向的话，把字符串当做是html代码来处理
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
            return resp
        # 如果响应结果为字典
        if isinstance(r, dict):
            # 先查看一下有没有'__template__'为key的值
            template = r.get('__template__')
            # 如果没有，说明要返回json字符串，则把字典转换为json返回，对应的response类型设为json类型
            if template is None:
                resp = web.Response(body=json.dumps(
                    r, ensure_ascii=False, default=lambda o: o.__dict__).encode('utf-8'))
                resp.content_type = 'application/json;charset=utf-8'
                return resp
            else:
                r['__user__'] = request.__user__
                # 如果有'__template__'为key的值，则说明要套用jinja2的模板，'__template__'Key对应的为模板网页所在位置
                resp = web.Response(body=app['__templating__'].get_template(
                    template).render(**r).encode('utf-8'))
                resp.content_type = 'text/html;charset=utf-8'
                # 以html的形式返回
                return resp
        # 如果响应结果为int
        if isinstance(r, int) and r >= 100 and r < 600:
            return web.Response(r)
        # 如果响应结果为tuple且数量为2
        if isinstance(r, tuple) and len(r) == 2:
            t, m = r
            # 如果tuple的第一个元素是int类型且在100到600之间，这里应该是认定为t为http状态码，m为错误描述
            # 或者是服务端自己定义的错误码+描述
            if isinstance(t, int) and t >= 100 and t < 600:
                return web.Response(status=t, text=str(m))
            # default: 默认直接以字符串输出
            resp = web.Response(body=str(r).encode('utf-8'))
            resp.content_type = 'text/plain;charset=utf-8'
            return resp
    return response


def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return u'1分钟前'
    if delta < 3600:
        return u'%s分钟前' % (delta // 60)
    if delta < 86400:
        return u'%s小时前' % (delta // 3600)
    if delta < 604800:
        return u'%s天前' % (delta // 86400)
    dt = datetime.fromtimestamp(t)
    return u'%s年%s月%s日' % (dt.year, dt.month, dt.day)


@asyncio.coroutine
def init(loop):
        # 创建数据库连接池，db参数传配置文件里的配置db
    yield from orm.create_pool(loop=loop, **configs.db)
    # middlewares设置两个中间处理函数
    # middlewares中的每个factory接受两个参数，app 和 handler(即middlewares中得下一个handler)
    # 譬如这里logger_factory的handler参数其实就是response_factory()
    # middlewares的最后一个元素的Handler会通过routes查找到相应的，其实就是routes注册的对应handler
    app = web.Application(loop=loop, middlewares=[
        logger_factory, auth_factory, response_factory
    ])
    # 初始化jinja2模板
    init_jinja2(app, filters=dict(datetime=datetime_filter))
    # 添加请求的handlers，即各请求相对应的处理函数
    add_routes(app, 'handlers')
    # 添加静态文件所在地址
    add_static(app)
    # 启动
    srv = yield from loop.create_server(app.make_handler(), '127.0.0.1', 9000)
    logging.info('server started at http://127.0.0.1:9000...')
    return srv


# 入口，固定写法
# 获取eventloop然后加入运行事件
loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()
