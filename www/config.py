import config_default

# 这个类主要可以使dict对象，以object.key 形式来替代  object[key]来取值


class Dict(dict):
    '''
    Simple dict but support access as x.y style.
    '''

    def __init__(self, names=(), values=(), **kw):
        super(Dict, self).__init__(**kw)
        for k, v in zip(names, values):
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

# 用override的已存在配置覆盖default里配置
# 简单地递归


def merge(default, override):
    r = {}
    for k, v in default.items():
        if k in override:
            if isinstance(v, dict):
                r[k] = merge(v, override[k])
            else:
                r[k] = override[k]
        else:
            r[k] = v
    return r

# 把配置文件转换为Dict类实例


def toDict(d):
    D = Dict()
    for k, v in d.items():
        D[k] = toDict(v) if isinstance(v, dict) else v
    return D

# configs默认为默认配置
configs = config_default.configs

try:
    import config_override
    # 这里把自定义配置文件里的配置项覆盖了默认配置里的配置项，
    # 如果自定义配置里没有定义，默认配置定义了，则还是沿用默认配置
    configs = merge(configs, config_override.configs)
except ImportError:
    pass

configs = toDict(configs)
