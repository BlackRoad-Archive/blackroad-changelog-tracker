"""Tests for Changelog Tracker."""
import json
import pytest
import sys
sys.path.insert(0, "/tmp")
from changelog_tracker import (
    ChangelogTracker, ChangeEntry, Release,
    TYPE_FEAT, TYPE_FIX, TYPE_BREAKING, TYPE_CHORE,
)


@pytest.fixture
def tracker(tmp_path):
    return ChangelogTracker(db_path=tmp_path / "test.db")


@pytest.fixture
def tracker_with_data(tracker):
    tracker.add_change("myapp", "1.0.0", TYPE_FEAT, "Initial release", author="alice")
    tracker.add_change("myapp", "1.0.0", TYPE_FIX, "Fix typo in readme", pr_number=1, author="bob")
    tracker.add_change("myapp", "1.0.0", TYPE_CHORE, "Setup CI pipeline")
    return tracker


def test_init_creates_db(tmp_path):
    db = tmp_path / "new.db"
    ChangelogTracker(db_path=db)
    assert db.exists()


def test_add_change_returns_entry(tracker):
    entry = tracker.add_change("proj", "1.0.0", TYPE_FEAT, "New feature")
    assert isinstance(entry, ChangeEntry)
    assert entry.project == "proj"
    assert entry.version == "1.0.0"
    assert entry.type == TYPE_FEAT
    assert entry.id


def test_add_change_invalid_type(tracker):
    with pytest.raises(ValueError, match="Invalid change type"):
        tracker.add_change("proj", "1.0.0", "invalid", "summary")


def test_finalize_release(tracker_with_data):
    release = tracker_with_data.finalize_release("myapp", "1.0.0")
    assert isinstance(release, Release)
    assert release.version == "1.0.0"
    assert len(release.changes) == 3
    assert "Initial release" in release.highlights


def test_finalize_no_changes_raises(tracker):
    with pytest.raises(ValueError):
        tracker.finalize_release("ghost", "9.9.9")


def test_generate_md(tracker_with_data):
    tracker_with_data.finalize_release("myapp", "1.0.0")
    md = tracker_with_data.generate_md("myapp")
    assert "# Changelog" in md
    assert "1.0.0" in md
    assert "Initial release" in md
    assert "Fix typo" in md


def test_generate_md_no_releases(tracker):
    md = tracker.generate_md("ghost")
    assert "No releases found" in md


def test_generate_json(tracker_with_data):
    tracker_with_data.finalize_release("myapp", "1.0.0")
    js = tracker_with_data.generate_json("myapp")
    data = json.loads(js)
    assert data["project"] == "myapp"
    assert len(data["releases"]) == 1
    assert data["releases"][0]["version"] == "1.0.0"


def test_semantic_bump_patch(tracker):
    tracker.add_change("proj", "1.0.0-unreleased", TYPE_FIX, "Fix bug")
    result = tracker.semantic_bump("proj", "1.2.3")
    assert result == "1.2.4"


def test_semantic_bump_minor(tracker):
    tracker.add_change("proj", "dev", TYPE_FEAT, "New feature")
    result = tracker.semantic_bump("proj", "1.2.3")
    assert result == "1.3.0"


def test_semantic_bump_major(tracker):
    tracker.add_change("proj", "dev", TYPE_BREAKING, "Breaking change")
    result = tracker.semantic_bump("proj", "1.2.3")
    assert result == "2.0.0"


def test_semantic_bump_no_changes(tracker):
    result = tracker.semantic_bump("proj", "1.2.3")
    assert result == "1.2.4"


def test_semantic_bump_invalid_version(tracker):
    with pytest.raises(ValueError):
        tracker.semantic_bump("proj", "not-semver")


def test_search_changes(tracker_with_data):
    results = tracker_with_data.search_changes("typo")
    assert len(results) == 1
    assert results[0]["summary"] == "Fix typo in readme"


def test_search_changes_with_project(tracker_with_data):
    results = tracker_with_data.search_changes("feature", project="myapp")
    assert all(r["project"] == "myapp" for r in results)


def test_list_projects(tracker_with_data):
    projects = tracker_with_data.list_projects()
    assert "myapp" in projects


def test_list_versions(tracker_with_data):
    versions = tracker_with_data.list_versions("myapp")
    assert any(v["version"] == "1.0.0" for v in versions)


def test_md_includes_pr_link(tracker):
    tracker.add_change("proj", "1.0.0", TYPE_FIX, "Bug fix", pr_number=42)
    tracker.finalize_release("proj", "1.0.0")
    md = tracker.generate_md("proj")
    assert "#42" in md
