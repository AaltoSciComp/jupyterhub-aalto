import json
import random
import stat
from pathlib import Path
from types import SimpleNamespace

import nbgrader_randomised_release as release
import pytest

# from pymod import nbgrader_randomised_release2 as release


def make_notebook() -> dict:
    return {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["Introduction"]},
            {
                "cell_type": "markdown",
                "metadata": {"aalto_nbgrader_bank": {"question_id": "q1", "weight": 1}},
                "source": ["Question one"],
            },
            {
                "cell_type": "code",
                "metadata": {
                    "aalto_nbgrader_bank": {"question_id": "q1", "weight": 1},
                    "nbgrader": {"grade_id": "q1-answer", "solution": True},
                },
                "source": ["answer = None"],
            },
            {
                "cell_type": "markdown",
                "metadata": {"aalto_nbgrader_bank": {"question_id": "q2", "weight": 3}},
                "source": ["Question two"],
            },
        ],
        "metadata": {"kernelspec": {"name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def test_load_students_merges_deduplicates_and_sorts_sources(tmp_path):
    students_file = tmp_path / "students.txt"
    students_file.write_text("# enrolled students\ncarol\nalice\n\n", encoding="utf-8")

    students = release._load_students_from_values("bob, alice, bob", str(students_file))

    assert students == ["alice", "bob", "carol"]


def test_selection_is_deterministic_and_without_replacement():
    first = release.weighted_without_replacement(
        ["q1", "q2", "q3"], [1.0, 2.0, 3.0], 2, random.Random(42)
    )
    second = release.weighted_without_replacement(
        ["q1", "q2", "q3"], [1.0, 2.0, 3.0], 2, random.Random(42)
    )

    assert first == second
    assert len(first) == 2
    assert len(set(first)) == 2


def test_selecting_every_question_preserves_population_order():
    selected = release.weighted_without_replacement(
        ["q2", "q1"], [1.0, 1.0], 2, random.Random(1)
    )

    assert selected == ["q2", "q1"]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ((["q1"], [1.0], 2), "larger than question count"),
        ((["q1"], [], 1), "weights length"),
        ((["q1"], [1.0], 0), "must be > 0"),
        ((["q1", "q2"], [0.0, 0.0], 1), "weights are <= 0"),
        ((["q1", "q2"], [-1.0, -2.0], 1), "weights are <= 0"),
        ((["q1", "q2"], [-1.0, 2.0], 1), "weights are <= 0"),
    ],
)
def test_rejects_invalid_selection_arguments(arguments, message):
    with pytest.raises(ValueError, match=message):
        release.weighted_without_replacement(*arguments, rng=random.Random(1))


def test_extract_bank_groups_question_cells_and_keeps_first_seen_order():
    common, questions, weights, groups, order = release.extract_bank(
        make_notebook(),
        question_metadata_key="aalto_nbgrader_bank",
        weight_key="weight",
    )

    assert [cell["source"] for cell in common] == [["Introduction"]]
    assert list(questions) == ["q1", "q2"]
    assert len(questions["q1"]) == 2
    assert weights == {"q1": 1.0, "q2": 3.0}
    assert groups == {"q1": None, "q2": None}
    assert order == ["q1", "q2"]


@pytest.mark.parametrize(
    ("bank_metadata", "message"),
    [
        ({"weight": 1}, "invalid"),
        ({"question_id": "q1", "weight": "heavy"}, "non-numeric"),
        ({"question_id": "q1", "weight": 0}, "non-positive"),
        ({"question_id": "q1", "weight": -1.0}, "non-positive"),
    ],
)
def test_extract_bank_rejects_invalid_question_metadata(bank_metadata, message):
    notebook = make_notebook()
    notebook["cells"] = [
        {
            "metadata": {"aalto_nbgrader_bank": bank_metadata},
            "source": [],
        }
    ]

    with pytest.raises(ValueError, match=message):
        release.extract_bank(
            notebook, question_metadata_key="aalto_nbgrader_bank", weight_key="weight"
        )


def test_extract_bank_multiple_weights():
    notebook = make_notebook()
    notebook["cells"] = [
        {
            "metadata": {"aalto_nbgrader_bank": {"question_id": "q1", "weight": 1.0}},
            "source": [],
        },
        {
            "metadata": {"aalto_nbgrader_bank": {"question_id": "q1", "weight": 2.0}},
            "source": [],
        },
        {
            "metadata": {"aalto_nbgrader_bank": {"question_id": "q2", "weight": 2.0}},
            "source": [],
        },
        {
            "metadata": {"aalto_nbgrader_bank": {"question_id": "q3"}},
            "source": [],
        },
        {
            "metadata": {"aalto_nbgrader_bank": {"question_id": "q3", "weight": 2.0}},
            "source": [],
        },
    ]

    _, questions, weights, groups, order = release.extract_bank(
        notebook, question_metadata_key="aalto_nbgrader_bank", weight_key="weight"
    )
    assert list(questions) == ["q1", "q2", "q3"]
    assert weights == {"q1": 1.0, "q2": 2.0, "q3": 1.0}
    assert groups == {"q1": None, "q2": None, "q3": None}
    assert order == ["q1", "q2", "q3"]


def test_extract_bank_records_groups_and_rejects_inconsistent_group_metadata():
    notebook = make_notebook()
    notebook["cells"][1]["metadata"]["aalto_nbgrader_bank"]["group"] = "algebra"
    notebook["cells"][2]["metadata"]["aalto_nbgrader_bank"]["group"] = "algebra"
    notebook["cells"][3]["metadata"]["aalto_nbgrader_bank"]["group"] = "geometry"

    _, _, _, groups, _ = release.extract_bank(
        notebook, question_metadata_key="aalto_nbgrader_bank", weight_key="weight"
    )
    assert groups == {"q1": "algebra", "q2": "geometry"}

    notebook["cells"][2]["metadata"]["aalto_nbgrader_bank"]["group"] = "geometry"
    with pytest.raises(ValueError, match="inconsistent group"):
        release.extract_bank(
            notebook,
            question_metadata_key="aalto_nbgrader_bank",
            weight_key="weight",
        )


@pytest.mark.parametrize("group", ["", 1, []])
def test_extract_bank_rejects_invalid_groups(group):
    notebook = make_notebook()
    notebook["cells"][1]["metadata"]["aalto_nbgrader_bank"]["group"] = group

    with pytest.raises(ValueError, match="invalid group"):
        release.extract_bank(
            notebook,
            question_metadata_key="aalto_nbgrader_bank",
            weight_key="weight",
        )


def test_build_notebook_keeps_metadata_and_only_selected_question(monkeypatch):
    source = make_notebook()
    common, questions, _, _, order = release.extract_bank(
        source, question_metadata_key="aalto_nbgrader_bank", weight_key="weight"
    )
    monkeypatch.setattr(release.time, "time", lambda: 1234)

    generated = release.build_notebook(
        source, common, questions, {"q1"}, order, "alice", 99
    )

    assert len(generated["cells"]) == 3
    assert generated["cells"][2]["metadata"]["nbgrader"]["grade_id"] == "q1-answer"
    assert generated["metadata"]["kernelspec"] == {"name": "python3"}
    assert generated["metadata"]["aalto_nbgrader_randomisation"] == {
        "student": "alice",
        "seed": 99,
        "selected_question_ids": ["q1"],
        "generated_unix_time": 1234,
    }
    assert "aalto_nbgrader_randomisation" not in source["metadata"]


def test_generation_writes_variants_manifest_and_uses_cache(tmp_path, monkeypatch):
    source_path = tmp_path / "assignment.ipynb"
    output_dir = tmp_path / "randomised"
    source_path.write_text(json.dumps(make_notebook()), encoding="utf-8")
    plugin = SimpleNamespace(coursedir=SimpleNamespace(groupshared=False))
    arguments = {
        "course_slug": "course",
        "assignment": "assignment",
        "source_path": source_path,
        "output_dir": output_dir,
        "pick_count": 1,
        "group_pick_counts": {},
        "students": ["alice", "bob"],
        "seed_salt": "salt",
        "question_metadata_key": "aalto_nbgrader_bank",
        "weight_key": "weight",
        "force": False,
        "lock_timeout": 1,
        "self": plugin,
        "logger": None,
    }
    monkeypatch.setattr(release.time, "time", lambda: 1000)

    release._generate_randomised_notebooks(**arguments)

    manifest_path = (
        output_dir / "manifests" / "assignment" / "_randomisation_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(manifest["per_student"]) == {"alice", "bob"}
    assert manifest["config"]["students"] == ["alice", "bob"]
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600

    for student, student_manifest in manifest["per_student"].items():
        notebook_path = (
            output_dir / "students" / student / "assignment" / "assignment.ipynb"
        )
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        randomisation = notebook["metadata"]["aalto_nbgrader_randomisation"]
        assert randomisation["student"] == student
        assert randomisation["selected_question_ids"] == sorted(
            student_manifest["selected_question_ids"]
        )
        assert stat.S_IMODE(notebook_path.stat().st_mode) == 0o644

    alice_path = Path(manifest["per_student"]["alice"]["path"])
    alice_path.write_text("cached", encoding="utf-8")
    release._generate_randomised_notebooks(**arguments)
    assert alice_path.read_text(encoding="utf-8") == "cached"

    arguments["force"] = True
    release._generate_randomised_notebooks(**arguments)
    assert alice_path.read_text(encoding="utf-8") != "cached"
    assert not (manifest_path.parent / ".randomisation.lock").exists()


def test_generation_samples_each_group_and_ungrouped_pool(tmp_path, monkeypatch):
    notebook = make_notebook()
    notebook["cells"].extend(
        [
            {
                "cell_type": "markdown",
                "metadata": {
                    "aalto_nbgrader_bank": {
                        "question_id": "q3",
                        "group": "algebra",
                        "weight": 1,
                    }
                },
                "source": ["Question three"],
            },
            {
                "cell_type": "markdown",
                "metadata": {
                    "aalto_nbgrader_bank": {
                        "question_id": "q4",
                        "group": "algebra",
                        "weight": 2,
                    }
                },
                "source": ["Question four"],
            },
            {
                "cell_type": "markdown",
                "metadata": {
                    "aalto_nbgrader_bank": {
                        "question_id": "q5",
                        "group": "geometry",
                        "weight": 1,
                    }
                },
                "source": ["Question five"],
            },
        ]
    )
    source_path = tmp_path / "assignment.ipynb"
    output_dir = tmp_path / "randomised"
    source_path.write_text(json.dumps(notebook), encoding="utf-8")
    arguments = {
        "course_slug": "course",
        "assignment": "assignment",
        "source_path": source_path,
        "output_dir": output_dir,
        "pick_count": 1,
        "group_pick_counts": {"algebra": 1, "geometry": 1},
        "students": ["alice"],
        "seed_salt": "salt",
        "question_metadata_key": "aalto_nbgrader_bank",
        "weight_key": "weight",
        "force": False,
        "lock_timeout": 1,
        "self": SimpleNamespace(coursedir=SimpleNamespace(groupshared=False)),
        "logger": None,
    }
    monkeypatch.setattr(release.time, "time", lambda: 1000)

    release._generate_randomised_notebooks(**arguments)

    manifest_path = (
        output_dir / "manifests" / "assignment" / "_randomisation_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    student_manifest = manifest["per_student"]["alice"]
    selected_by_group = student_manifest["selected_by_group"]
    assert len(student_manifest["selected_ungrouped_question_ids"]) == 1
    assert len(selected_by_group["algebra"]) == 1
    assert selected_by_group["geometry"] == ["q5"]
    assert manifest["config"]["group_pick_counts"] == {
        "algebra": 1,
        "geometry": 1,
    }

    notebook_path = Path(manifest["per_student"]["alice"]["path"])
    notebook_path.write_text("cached", encoding="utf-8")
    arguments["group_pick_counts"] = {"algebra": 2, "geometry": 1}
    release._generate_randomised_notebooks(**arguments)
    assert notebook_path.read_text(encoding="utf-8") != "cached"


@pytest.mark.parametrize(
    ("question_groups", "group_pick_counts", "message"),
    [
        ({"q1": None, "q2": "algebra"}, {}, "Missing group_pick_counts"),
        ({"q1": None}, {"algebra": 1}, "unknown groups"),
        ({"q1": None, "q2": "algebra"}, {"algebra": 0}, "must be > 0"),
        (
            {"q1": None, "q2": "algebra"},
            {"algebra": 2},
            "larger than question count",
        ),
    ],
)
def test_select_questions_rejects_invalid_group_quotas(
    question_groups, group_pick_counts, message
):
    question_ids = list(question_groups)
    with pytest.raises(ValueError, match=message):
        release.select_questions(
            question_ids,
            {question_id: 1.0 for question_id in question_ids},
            question_groups,
            pick_count=1,
            group_pick_counts=group_pick_counts,
            rng=random.Random(1),
        )


def test_select_questions_samples_weighted_pools_deterministically(monkeypatch):
    calls = []

    def record_selection(population, weights, pick_count, rng):
        calls.append((population, weights, pick_count))
        return population[:pick_count]

    monkeypatch.setattr(release, "weighted_without_replacement", record_selection)
    arguments = {
        "question_ids": ["u1", "u2", "a1", "a2", "g1"],
        "question_weights": {
            "u1": 1.0,
            "u2": 2.0,
            "a1": 3.0,
            "a2": 4.0,
            "g1": 5.0,
        },
        "question_groups": {
            "u1": None,
            "u2": None,
            "a1": "algebra",
            "a2": "algebra",
            "g1": "geometry",
        },
        "pick_count": 1,
        "group_pick_counts": {"algebra": 1, "geometry": 1},
    }

    first = release.select_questions(**arguments, rng=random.Random(42))
    second = release.select_questions(**arguments, rng=random.Random(42))

    assert first == second
    assert calls[:3] == [
        (["u1", "u2"], [1.0, 2.0], 1),
        (["a1", "a2"], [3.0, 4.0], 1),
        (["g1"], [5.0], 1),
    ]


def test_generation_rejects_empty_students_and_invalid_pick_count():
    base_arguments = {
        "course_slug": "course",
        "assignment": "assignment",
        "source_path": Path("unused.ipynb"),
        "output_dir": Path("unused"),
        "group_pick_counts": {},
        "students": ["alice"],
        "seed_salt": "",
        "question_metadata_key": "aalto_nbgrader_bank",
        "weight_key": "weight",
        "force": False,
        "lock_timeout": 1,
        "self": SimpleNamespace(coursedir=SimpleNamespace(groupshared=False)),
        "logger": None,
    }

    with pytest.raises(ValueError, match="pick_count must be > 0"):
        release._generate_randomised_notebooks(**base_arguments, pick_count=0)
    with pytest.raises(ValueError, match="No students provided"):
        release._generate_randomised_notebooks(
            **{**base_arguments, "students": []}, pick_count=1
        )
