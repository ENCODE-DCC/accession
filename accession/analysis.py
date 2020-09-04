import operator
from functools import reduce
from typing import Tuple

from flatdict import FlatDict

from accession.backends import GCBackend
from accession.file import GSFile
from accession.task import Task


class Analysis:
    """
    Parses Cromwell workflow metadata into a searchable digraph
    """

    def __init__(
        self,
        metadata,
        raw_fastqs_keys=None,
        raw_fastqs_can_have_task=False,
        auto_populate=True,
        backend=None,
    ):
        self.files = []
        self.tasks = []
        self.metadata = metadata
        self.raw_fastqs_keys = raw_fastqs_keys
        self.raw_fastqs_can_have_task = raw_fastqs_can_have_task
        if self.metadata:
            if backend is None:
                bucket = (
                    self.metadata.content["workflowRoot"]
                    .split("gs://")[1]
                    .split("/")[0]
                )
                self.backend = GCBackend(bucket)
            else:
                self.backend = backend
        else:
            raise Exception("Valid metadata json output must be supplied")
        if auto_populate:
            self.tasks = self.make_tasks()

    @property
    def workflow_id(self) -> str:
        """
        Returns the Cromwell workflow id
        """
        return self.metadata.workflow_id

    def make_tasks(self):
        """
        Makes instances of Task. If the task did not succeed then will not add it to the
        call graph.
        """
        tasks = []
        for key, value in self.metadata.content["calls"].items():
            for task in value:
                if task["executionStatus"] == "Done":
                    tasks.append(self.make_task(key, task))
        for task in tasks:
            task.output_files = self.get_or_make_files(task.outputs, task)
        # Making input files after making output files avoids creating
        # a duplicate file
        for task in tasks:
            task.input_files = self.get_or_make_files(task.inputs, used_by_tasks=task)
        return tasks

    # Makes an instance of task with input and output GSFile instances
    def make_task(self, task_name, task):
        new_task = Task(task_name.split(".")[1], task)
        return new_task

    def get_or_make_files(self, section, task=None, used_by_tasks=None):
        """
        Makes instances of GSFile from input or output section of task. When task=None,
        file is not associated with a task. Flattens nested dict keys, so if the section
        looks like `{"foo": {"bar": "baz", "qux": [{"quux": "corge"}]}}`, first the
        section will be flattened into
        `{"foo.bar": "baz", "foo.qux": [{"quux": "corge"}]}`, note that arrays are not
        flattened. Any files anywhere inside the array will be reached later via
        `extract_files`
        """
        files = []
        flattened = FlatDict(section, delimiter=".")
        for key, value in flattened.items():
            for filename in self.extract_files(value):
                files.append(self.get_or_make_file(key, filename, task, used_by_tasks))
        return files

    # Returns a GSFile object, makes a new one if one doesn't exist
    def get_or_make_file(self, key, filename, task=None, used_by_tasks=None):
        for file in self.files:
            if filename == file.filename:
                if key not in file.filekeys:
                    file.filekeys.append(key)
                if used_by_tasks and used_by_tasks not in file.used_by_tasks:
                    file.used_by_tasks.append(used_by_tasks)
                return file
        blob = self.backend.blob_from_filename(filename)
        new_file = GSFile(key, filename, blob.md5sum, blob.size, task, used_by_tasks)
        self.files.append(new_file)
        return new_file

    # Extracts file names from dict values
    def extract_files(self, outputs):
        if isinstance(outputs, str) and "gs://" in outputs:
            yield outputs
        elif isinstance(outputs, list):
            for item in outputs:
                yield from self.extract_files(item)
        elif isinstance(outputs, dict):
            for key, values in outputs.items():
                yield from self.extract_files(values)

    def get_tasks(self, task_name):
        tasks = []
        for task in self.tasks:
            if task_name == task.task_name:
                tasks.append(task)
        return tasks

    def get_files(self, filekey=None, filename=None):
        files = []
        if filekey:
            for file in self.files:
                if filekey in file.filekeys:
                    files.append(file)
        if filename:
            for file in self.files:
                if filename == file.filename:
                    files.append(file)
        return list(set(files))

    @property
    def raw_fastqs(self):
        fastqs = []
        raw_fastqs_keys = ("fastq", "fastqs")
        if self.raw_fastqs_keys is not None:
            raw_fastqs_keys = self.raw_fastqs_keys
        for file in self.files:
            if any([k in file.filekeys for k in raw_fastqs_keys]):
                if not self.raw_fastqs_can_have_task:
                    if file.task is not None:
                        continue
                fastqs.append(file)
        return fastqs

    def search_up(
        self,
        start_task,
        task_name,
        filekey,
        inputs=False,
        disallow_tasks: Tuple[str, ...] = (),
    ):
        return list(
            set(self._search_up(start_task, task_name, filekey, inputs, disallow_tasks))
        )

    def search_down(self, start_task, task_name, filekey, inputs: bool = False):
        return list(set(self._search_down(start_task, task_name, filekey, inputs)))

    def _search_up(
        self,
        start_task,
        task_name,
        filekey,
        inputs: bool = False,
        disallow_tasks: Tuple[str, ...] = (),
    ):
        """
        Search the Analysis hirearchy up for a file matching filekey. Returns a
        generator, access with next() or list() task parameter specifies the starting
        point, task_name is target task in which filekey exists.

        The disallow_tasks input is designed to avoid conflicts that can occur when
        there is a diamond dependency of several of a task's inputs on the same parent.
        This mechanism allows for halting the search up one of those branches, avoiding
        the reporting of spurious parent files. A ValueError is raised if the task name
        being searched for is also disallowed.
        """
        if task_name in disallow_tasks:
            raise ValueError(
                f"Cannot search for files in task {task_name} since this task is disallowed"
            )
        if task_name == start_task.task_name:
            if inputs is True:
                for file in start_task.input_files:
                    if filekey in file.filekeys:
                        yield file
            else:
                for file in start_task.output_files:
                    if filekey in file.filekeys:
                        yield file
        for task_item in set(
            map(
                lambda x: x.task
                if x.task is not None
                and x.task.task_name not in disallow_tasks
                and id(start_task) != id(x.task)
                else None,
                start_task.input_files,
            )
        ):
            if task_item:
                yield from self._search_up(
                    task_item, task_name, filekey, inputs, disallow_tasks=disallow_tasks
                )

    def _search_down(self, start_task, task_name, filekey, inputs: bool = False):
        """
        Search the Analysis hirearchy down for a file matching filekey. Returns
        generator object, access with next(). Task parameter specifies the starting
        point, task_name is target task in which filekey exists.

        The third argument to the reduce provides a default in the case that the task
        has no output files.
        """
        if task_name == start_task.task_name:
            if inputs is True:
                for file in start_task.input_files:
                    if filekey in file.filekeys:
                        yield file
            else:
                for file in start_task.output_files:
                    if filekey in file.filekeys:
                        yield file
        for task_item in set(  # type: ignore
            reduce(
                operator.concat,  # type: ignore
                map(lambda x: x.used_by_tasks, start_task.output_files),
                [],
            )
        ):
            if task_item:
                yield from self._search_down(task_item, task_name, filekey, inputs)
