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

    # Depends on all other tasks and files having finished initializing
    # Returns lisf of files
    def derived_from(self, filekey=None):
        if not filekey:
            return self.task.input_files
        else:
            return list(filter(lambda x: filekey in x.filekeys,
                               self.task.input_files))
