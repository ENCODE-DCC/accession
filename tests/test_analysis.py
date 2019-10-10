def test_make_tasks(empty_analysis):
    assert len(empty_analysis.files) == 0
    empty_analysis.tasks = empty_analysis.make_tasks()
    assert len(empty_analysis.files) == 208
    assert len(empty_analysis.tasks) == 38


def test_get_or_make_file(empty_analysis, analysis):
    assert len(empty_analysis.files) == 0
    assert len(analysis.files) == 208
    # Make a file when it doesn't exist
    task = analysis.get_tasks("bam2ta")[0]
    filekey = "ta"
    filename = task.outputs[filekey]
    empty_analysis.get_or_make_file(filekey, filename, task)
    assert len(empty_analysis.files) == 1
    assert empty_analysis.files[0].filename == filename
    # Get file if it exists, don't make a duplicate
    empty_analysis.get_or_make_file(filekey, filename, task)
    assert len(empty_analysis.files) == 1


def test_get_files(analysis):
    files = analysis.get_files(filekey="ta")
    assert len(files) == 9
    assert all(["ta" in file.filekeys for file in files])
    filename = files[0].filename
    files2 = analysis.get_files(filename=filename)
    assert filename == files2[0].filename
    assert len(files2) == 1


def test_get_tasks(analysis):
    tasks = analysis.get_tasks("bam2ta")
    tasks2 = analysis.get_tasks("qc_report")
    assert len(tasks) == 2
    assert all([task.task_name == "bam2ta" for task in tasks])
    assert len(tasks2) == 1
    assert tasks2[0].task_name == "qc_report"


def test_search_up(analysis):
    task = analysis.get_tasks("qc_report")[0]
    files = analysis.search_up(task, "bam2ta", "ta")
    assert len(files) == 2
    assert "ta" in files[0].filekeys
    task2 = analysis.get_tasks("bam2ta")[0]
    files2 = analysis.search_up(task2, "trim_adapter", "fastqs", inputs=True)
    assert len(files2) == 2
    task3 = analysis.get_tasks("ataqc")[0]
    files3 = analysis.search_up(task3, "trim_adapter", "fastqs", inputs=True)
    # Notice how tree nodes widen the search scope
    assert len(files3) == 4


def test_search_down(analysis):
    task = analysis.get_tasks("bam2ta")[0]
    files = analysis.search_down(task, "ataqc", "html")
    assert len(files) == 2
    assert "html" in files[0].filekeys
    files2 = analysis.search_down(task, "qc_report", "report")
    assert len(files2) == 1
    assert "report" in files2[0].filekeys
