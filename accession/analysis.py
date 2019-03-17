import json
import operator
from functools import reduce
from accession.backends import GCBackend
from accession.file import GSFile
from accession.task import Task


class Analysis(object):
    """docstring for Analysis"""
    def __init__(self, metadata_json, auto_populate=True):
        self.files = []
        self.tasks = []
        with open(metadata_json) as json_file:
            self.metadata = json.load(json_file)
        if self.metadata:
            bucket = self.metadata['workflowRoot'].split('gs://')[1].split('/')[0]
            self.backend = GCBackend(bucket)
        else:
            raise Exception('Valid metadata json output must be supplied')
        if auto_populate:
            self.tasks = self.make_tasks()

    # Makes instances of Task
    def make_tasks(self):
        tasks = []
        for key, value in self.metadata['calls'].items():
            for task in value:
                tasks.append(self.make_task(key, task))
        for task in tasks:
            task.output_files = self.get_or_make_files(task.outputs, task)
        # Making input files after making output files avoids creating
        # a duplicate file
        for task in tasks:
            task.input_files = self.get_or_make_files(task.inputs,
                                                      used_by_tasks=task)
        return tasks

    # Makes an instance of task with input and output GSFile instances
    def make_task(self, task_name, task):
        new_task = Task(task_name.split('.')[1], task, self)
        return new_task

    # Makes instances of GSFile from input or output section of task
    # When task=None, file is not associated with a task
    def get_or_make_files(self, section, task=None, used_by_tasks=None):
        files = []
        for key, value in section.items():
            for filename in self.extract_files(value):
                files.append(self.get_or_make_file(key,
                                                   filename,
                                                   task,
                                                   used_by_tasks))
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
        md5sum = self.backend.md5sum(filename)
        size = self.backend.size(filename)
        new_file = GSFile(key, filename, md5sum, size, task, used_by_tasks)
        self.files.append(new_file)
        return new_file

    # Cromwell workflow id
    @property
    def workflow_id(self):
        return self.metadata['labels']['cromwell-workflow-id']

    # Files in the 'outputs' of the metadata that are
    # used for filtering out intermediate outputs
    @property
    def outputs_whitelist(self):
        return list(self.extract_files(self.metadata['outputs']))

    # Files in the 'inputs' of the metadata that are
    # used for filtering out intermediate inputs
    @property
    def inputs_whitelist(self):
        return list(self.extract_files(self.metadata['inputs']))

    # Extracts file names from dict values
    def extract_files(self, outputs):
        if (isinstance(outputs, str) and 'gs://' in outputs):
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
        for file in self.files:
            if 'fastqs' in file.filekeys and file.task is None:
                fastqs.append(file)
        return fastqs

    def search_up(self, start_task, task_name, filekey, inputs=False):
        return list(set(self._search_up(start_task,
                                        task_name,
                                        filekey,
                                        inputs)))

    def search_down(self, start_task, task_name, filekey):
        return list(set(self._search_down(start_task,
                                          task_name,
                                          filekey)))

    # Search the Analysis hirearchy up for a file matching filekey
    # Returns generator object, access with next() or list()
    # task parameter specifies the starting point
    # task_name is target task in which filekey exists
    def _search_up(self, start_task, task_name, filekey, inputs=False):
        if task_name == start_task.task_name:
            if inputs:
                for file in start_task.input_files:
                    if filekey in file.filekeys:
                        yield file
            else:
                for file in start_task.output_files:
                    if filekey in file.filekeys:
                        yield file
        for task_item in set(map(lambda x: x.task, start_task.input_files)):
            if task_item:
                yield from self._search_up(task_item,
                                           task_name,
                                           filekey,
                                           inputs)

    # Search the Analysis hirearchy down for a file matching filekey
    # Returns generator object, access with next()
    # task parameter specifies the starting point
    # task_name is target task in which filekey exists
    def _search_down(self, start_task, task_name, filekey):
        if task_name == start_task.task_name:
            for file in start_task.output_files:
                if filekey in file.filekeys:
                    yield file
        for task_item in set(reduce(operator.concat,
                                    map(lambda x: x.used_by_tasks,
                                        start_task.output_files))):
            if task_item:
                yield from self._search_down(task_item,
                                             task_name,
                                             filekey)
