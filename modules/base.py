class BaseService:
    def __init__(self, plugin):
        self.p = plugin

    def __getattr__(self, name):
        return getattr(self.p, name)
