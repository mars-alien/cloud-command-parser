from worker.worker import my_lines


def test_worker_shards_partition_lines_without_overlap():
    lines = ["a", "b", "c", "d", "e"]

    assert my_lines(lines, 0, 2) == ["a", "c", "e"]
    assert my_lines(lines, 1, 2) == ["b", "d"]
