class GSFile(object):
    """docstring for File"""
    def __init__(self, key, name, md5sum, size, task=None, used_by_tasks=None):
        super().__init__()
        self.filename = name
        self.filekeys = [key]
        self.task = task
        self.used_by_tasks = [used_by_tasks] if used_by_tasks else []
        self.md5sum = md5sum
        self.size = size