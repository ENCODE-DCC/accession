class Task:
    """
    The dockerImageUsed key in the task metadata can sometimes be missing if there was a cache hit.
    In that event, the dockerImage will fail back to the docker key in the task runtimeAttributes.
    The RHS of the or statement will guarantee a KeyError if no docker image is found.  Unlike
    dockerImageUsedThis key does not include the image SHA, but rather the image tag. See
    https://github.com/broadinstitute/cromwell/issues/4001
    """

    def __init__(self, task_name, task):
        self.task_name = task_name
        self.input_files = []
        self.output_files = []
        self.inputs = task["inputs"]
        self.outputs = task["outputs"]
        self.docker_image = task.get("dockerImageUsed") or task.get(
            "runtimeAttributes", {}
        ).get("docker")
