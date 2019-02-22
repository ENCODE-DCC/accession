class Task(object):
    """docstring for Task"""
    def __init__(self, task_name, task, analysis):
        super().__init__()
        self.task_name = task_name
        self.input_files = []
        self.output_files = []
        self.inputs = task['inputs']
        self.outputs = task['outputs']
        self.docker_image = task.get('dockerImageUsed', None)
        self.analysis = analysis
