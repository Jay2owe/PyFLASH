from reproducibility.pytest_shard import partition_nodeids
from reproducibility.run_pytest_shards import run


def test_full_suite_shards_are_balanced_disjoint_and_keep_modules_whole():
    nodeids = [
        *(f'test_large.py::test_case[{index}]' for index in range(40)),
        *(f'test_small_{module}.py::test_case[{index}]'
          for module in range(20) for index in range(5)),
    ]

    assignment = partition_nodeids(nodeids, 3)

    assert set(assignment) == set(nodeids)
    assert set(assignment.values()) == {0, 1, 2}
    by_module = {}
    for nodeid, shard in assignment.items():
        by_module.setdefault(nodeid.split('::', 1)[0], set()).add(shard)
    assert all(len(shards) == 1 for shards in by_module.values())
    counts = [sum(shard == index for shard in assignment.values()) for index in range(3)]
    assert max(counts) - min(counts) <= 10


def test_full_suite_shards_create_each_basetemp_for_tmp_path_tests(tmp_path):
    tests = tmp_path / 'isolated-tests'
    tests.mkdir()
    (tests / 'test_alpha.py').write_text(
        'def test_alpha_owns_a_temp_path(tmp_path):\n'
        '    marker = tmp_path / "alpha.txt"\n'
        '    marker.write_text("alpha", encoding="utf-8")\n'
        '    assert marker.read_text(encoding="utf-8") == "alpha"\n',
        encoding='utf-8',
    )
    (tests / 'test_beta.py').write_text(
        'def test_beta_owns_a_temp_path(tmp_path):\n'
        '    marker = tmp_path / "beta.txt"\n'
        '    marker.write_text("beta", encoding="utf-8")\n'
        '    assert marker.read_text(encoding="utf-8") == "beta"\n',
        encoding='utf-8',
    )

    result = run(tmp_path / 'shard-output', tmp_path / 'pytest-temp',
                 workers=2, tests_path=tests)

    assert result['status'] == 'pass'
    assert result['collected_count'] == 2
    assert result['executed_count'] == 2
    assert all((tmp_path / 'pytest-temp' / f'shard-{index:02d}').is_dir()
               for index in (1, 2))
