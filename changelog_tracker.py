"""
Automated Changelog and Release Notes Manager
blackroad-changelog-tracker: Track, generate, and manage changelogs with semantic versioning.
"""

import argparse
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("changelog_tracker")

DB_PATH = Path(os.environ.get("CHANGELOG_DB", Path.home() / ".blackroad" / "changelog_tracker.db"))

TYPE_FEAT = "feat"
TYPE_FIX = "fix"
TYPE_BREAKING = "breaking"
TYPE_PERF = "perf"
TYPE_REFACTOR = "refactor"
TYPE_DOCS = "docs"
TYPE_CHORE = "chore"

CHANGE_TYPES = [TYPE_FEAT, TYPE_FIX, TYPE_BREAKING, TYPE_PERF, TYPE_REFACTOR, TYPE_DOCS, TYPE_CHORE]

TYPE_EMOJI = {
    TYPE_FEAT: "✨",
    TYPE_FIX: "🐛",
    TYPE_BREAKING: "💥",
    TYPE_PERF: "⚡",
    TYPE_REFACTOR: "♻️",
    TYPE_DOCS: "📝",
    TYPE_CHORE: "🔧",
}

TYPE_SECTION = {
    TYPE_FEAT: "Features",
    TYPE_FIX: "Bug Fixes",
    TYPE_BREAKING: "Breaking Changes",
    TYPE_PERF: "Performance",
    TYPE_REFACTOR: "Refactoring",
    TYPE_DOCS: "Documentation",
    TYPE_CHORE: "Chores",
}


@dataclass
class ChangeEntry:
    """A single change entry in the changelog."""
    id: str
    project: str
    version: str
    type: str
    summary: str
    details: str = ""
    pr_number: Optional[int] = None
    author: str = ""
    date: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    is_finalized: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row) -> "ChangeEntry":
        return cls(
            id=row["id"],
            project=row["project"],
            version=row["version"],
            type=row["type"],
            summary=row["summary"],
            details=row["details"] or "",
            pr_number=row["pr_number"],
            author=row["author"] or "",
            date=row["date"],
            is_finalized=bool(row["is_finalized"]),
        )


@dataclass
class Release:
    """Represents a finalized release with grouped changes."""
    project: str
    version: str
    date: str
    changes: list
    highlights: list

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "version": self.version,
            "date": self.date,
            "changes": self.changes,
            "highlights": self.highlights,
        }


class ChangelogTracker:
    """
    Manages project changelogs with semantic versioning support.

    Stores all change entries in SQLite and generates Markdown or JSON output.

    Usage::

        tracker = ChangelogTracker()
        tracker.add_change("myapp", "1.1.0", "feat", "Add new dashboard", author="alice")
        tracker.finalize_release("myapp", "1.1.0")
        md = tracker.generate_md("myapp")
        print(md)
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS change_entries (
                    id TEXT PRIMARY KEY,
                    project TEXT NOT NULL,
                    version TEXT NOT NULL,
                    type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    details TEXT DEFAULT '',
                    pr_number INTEGER,
                    author TEXT DEFAULT '',
                    date TEXT NOT NULL,
                    is_finalized INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS releases (
                    id TEXT PRIMARY KEY,
                    project TEXT NOT NULL,
                    version TEXT NOT NULL,
                    release_date TEXT NOT NULL,
                    highlights TEXT DEFAULT '[]',
                    UNIQUE(project, version)
                );

                CREATE INDEX IF NOT EXISTS idx_entries_project ON change_entries(project);
                CREATE INDEX IF NOT EXISTS idx_entries_version ON change_entries(project, version);
                CREATE INDEX IF NOT EXISTS idx_releases_project ON releases(project);
            """)
        logger.debug("DB initialized at %s", self.db_path)

    def add_change(
        self,
        project: str,
        version: str,
        change_type: str,
        summary: str,
        details: str = "",
        pr_number: Optional[int] = None,
        author: str = "",
    ) -> ChangeEntry:
        """Add a new change entry.

        Args:
            project: Project identifier.
            version: Target version (e.g. '1.2.0').
            change_type: Type of change (feat/fix/breaking/perf/refactor/docs/chore).
            summary: One-line summary.
            details: Extended description.
            pr_number: PR number if applicable.
            author: Author name or username.

        Returns:
            The created ChangeEntry.
        """
        if change_type not in CHANGE_TYPES:
            raise ValueError(f"Invalid change type: {change_type}. Must be one of {CHANGE_TYPES}")

        entry = ChangeEntry(
            id=str(uuid4()),
            project=project,
            version=version,
            type=change_type,
            summary=summary,
            details=details,
            pr_number=pr_number,
            author=author,
        )
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO change_entries
                   (id, project, version, type, summary, details, pr_number, author, date, is_finalized)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (entry.id, entry.project, entry.version, entry.type,
                 entry.summary, entry.details, entry.pr_number, entry.author, entry.date),
            )
        logger.info("Added %s change for %s@%s: %s", change_type, project, version, summary[:50])
        return entry

    def finalize_release(self, project: str, version: str) -> Release:
        """Finalize a release, locking all change entries for that version.

        Args:
            project: Project identifier.
            version: Version to finalize.

        Returns:
            The Release dataclass.
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM change_entries WHERE project=? AND version=?",
                (project, version),
            ).fetchall()

        if not rows:
            raise ValueError(f"No changes found for {project}@{version}")

        changes = [ChangeEntry.from_row(r) for r in rows]
        highlights = [
            e.summary for e in changes
            if e.type in (TYPE_FEAT, TYPE_BREAKING)
        ][:5]

        release_date = datetime.utcnow().isoformat()
        release_id = str(uuid4())

        with self._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO releases (id, project, version, release_date, highlights)
                   VALUES (?, ?, ?, ?, ?)""",
                (release_id, project, version, release_date, json.dumps(highlights)),
            )
            conn.execute(
                "UPDATE change_entries SET is_finalized=1 WHERE project=? AND version=?",
                (project, version),
            )

        release = Release(
            project=project,
            version=version,
            date=release_date,
            changes=[c.to_dict() for c in changes],
            highlights=highlights,
        )
        logger.info("Finalized release %s@%s with %d changes.", project, version, len(changes))
        return release

    def generate_md(self, project: str, max_versions: int = 5) -> str:
        """Generate a Markdown changelog for a project.

        Args:
            project: Project identifier.
            max_versions: Maximum number of versions to include.

        Returns:
            Markdown string.
        """
        with self._get_conn() as conn:
            releases = conn.execute(
                """SELECT version, release_date, highlights FROM releases
                   WHERE project=? ORDER BY release_date DESC LIMIT ?""",
                (project, max_versions),
            ).fetchall()

        if not releases:
            return f"# Changelog\n\n_No releases found for {project}._\n"

        lines = [f"# Changelog — {project}\n",
                 "_Generated by blackroad-changelog-tracker_\n"]

        for rel in releases:
            version = rel["version"]
            date = rel["release_date"][:10]
            highlights = json.loads(rel["highlights"])

            lines.append(f"\n## [{version}] — {date}\n")

            if highlights:
                lines.append("### Highlights\n")
                for h in highlights:
                    lines.append(f"- {h}")
                lines.append("")

            with self._get_conn() as conn:
                entries = conn.execute(
                    """SELECT * FROM change_entries WHERE project=? AND version=?
                       ORDER BY type, date""",
                    (project, version),
                ).fetchall()

            by_type: dict = {}
            for row in entries:
                t = row["type"]
                by_type.setdefault(t, []).append(row)

            for change_type in CHANGE_TYPES:
                type_entries = by_type.get(change_type, [])
                if not type_entries:
                    continue
                emoji = TYPE_EMOJI.get(change_type, "")
                section = TYPE_SECTION.get(change_type, change_type.title())
                lines.append(f"### {emoji} {section}\n")
                for e in type_entries:
                    pr_str = f" ([#{e['pr_number']}](https://github.com/pulls/{e['pr_number']}))" if e["pr_number"] else ""
                    author_str = f" by @{e['author']}" if e["author"] else ""
                    lines.append(f"- {e['summary']}{pr_str}{author_str}")
                    if e["details"]:
                        lines.append(f"  > {e['details']}")
                lines.append("")

        return "\n".join(lines)

    def generate_json(self, project: str) -> str:
        """Generate a JSON changelog for a project.

        Args:
            project: Project identifier.

        Returns:
            JSON string.
        """
        with self._get_conn() as conn:
            releases = conn.execute(
                "SELECT * FROM releases WHERE project=? ORDER BY release_date DESC",
                (project,),
            ).fetchall()

        output = []
        for rel in releases:
            with self._get_conn() as conn:
                entries = conn.execute(
                    "SELECT * FROM change_entries WHERE project=? AND version=?",
                    (project, rel["version"]),
                ).fetchall()

            output.append({
                "version": rel["version"],
                "date": rel["release_date"],
                "highlights": json.loads(rel["highlights"]),
                "changes": [
                    {
                        "type": e["type"],
                        "summary": e["summary"],
                        "details": e["details"],
                        "pr_number": e["pr_number"],
                        "author": e["author"],
                    }
                    for e in entries
                ],
            })

        return json.dumps({"project": project, "releases": output}, indent=2)

    def semantic_bump(self, project: str, current_version: str) -> str:
        """Suggest next semantic version based on unreleased changes.

        Follows SemVer rules:
        - breaking → major bump
        - feat → minor bump
        - fix/perf/refactor/docs/chore → patch bump

        Args:
            project: Project identifier.
            current_version: Current version string like '1.2.3'.

        Returns:
            Suggested next version string.
        """
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(.*)", current_version)
        if not match:
            raise ValueError(f"Invalid semver: {current_version}")
        major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
        suffix = match.group(4)

        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT type FROM change_entries WHERE project=? AND is_finalized=0",
                (project,),
            ).fetchall()

        if not rows:
            return f"{major}.{minor}.{patch + 1}{suffix}"

        types = {r["type"] for r in rows}

        if TYPE_BREAKING in types:
            return f"{major + 1}.0.0"
        if TYPE_FEAT in types:
            return f"{major}.{minor + 1}.0"
        return f"{major}.{minor}.{patch + 1}{suffix}"

    def search_changes(self, query: str, project: Optional[str] = None) -> list:
        """Full-text search across change summaries and details.

        Args:
            query: Search term.
            project: Limit search to this project if provided.

        Returns:
            List of matching ChangeEntry dicts.
        """
        pattern = f"%{query}%"
        with self._get_conn() as conn:
            if project:
                rows = conn.execute(
                    """SELECT * FROM change_entries
                       WHERE project=? AND (summary LIKE ? OR details LIKE ?)
                       ORDER BY date DESC""",
                    (project, pattern, pattern),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM change_entries
                       WHERE summary LIKE ? OR details LIKE ?
                       ORDER BY date DESC""",
                    (pattern, pattern),
                ).fetchall()

        return [ChangeEntry.from_row(r).to_dict() for r in rows]

    def list_projects(self) -> list:
        """Return all tracked project names."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT project FROM change_entries ORDER BY project"
            ).fetchall()
        return [r["project"] for r in rows]

    def list_versions(self, project: str) -> list:
        """List all versions for a project."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT version, is_finalized FROM change_entries WHERE project=? ORDER BY date DESC",
                (project,),
            ).fetchall()
        return [{"version": r["version"], "finalized": bool(r["is_finalized"])} for r in rows]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_add(args, tracker: ChangelogTracker) -> None:
    entry = tracker.add_change(
        project=args.project,
        version=args.version,
        change_type=args.type,
        summary=args.summary,
        details=args.details or "",
        pr_number=args.pr,
        author=args.author or "",
    )
    print(f"✓ Added [{entry.type}] {entry.summary[:60]} to {args.project}@{args.version}")


def cmd_finalize(args, tracker: ChangelogTracker) -> None:
    release = tracker.finalize_release(args.project, args.version)
    print(f"✓ Finalized {args.project}@{args.version} with {len(release.changes)} change(s).")
    if release.highlights:
        print("  Highlights:")
        for h in release.highlights:
            print(f"    • {h}")


def cmd_generate_md(args, tracker: ChangelogTracker) -> None:
    md = tracker.generate_md(args.project, max_versions=args.max_versions)
    if args.output:
        with open(args.output, "w") as f:
            f.write(md)
        print(f"✓ Written to {args.output}")
    else:
        print(md)


def cmd_generate_json(args, tracker: ChangelogTracker) -> None:
    output = tracker.generate_json(args.project)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"✓ Written to {args.output}")
    else:
        print(output)


def cmd_bump(args, tracker: ChangelogTracker) -> None:
    next_ver = tracker.semantic_bump(args.project, args.current)
    print(f"Suggested next version: {next_ver}")


def cmd_search(args, tracker: ChangelogTracker) -> None:
    results = tracker.search_changes(args.query, project=getattr(args, "project", None))
    if not results:
        print("No matching changes found.")
        return
    for r in results:
        pr = f" (#{r['pr_number']})" if r.get("pr_number") else ""
        print(f"  [{r['type']}] {r['project']}@{r['version']}: {r['summary']}{pr}")


def cmd_list(args, tracker: ChangelogTracker) -> None:
    projects = tracker.list_projects()
    if not projects:
        print("No projects tracked.")
        return
    for p in projects:
        versions = tracker.list_versions(p)
        ver_str = ", ".join(
            f"{v['version']}{'✓' if v['finalized'] else '…'}" for v in versions
        )
        print(f"  {p}: {ver_str}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Automated Changelog and Release Notes Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", help="Override database path")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # add
    p = sub.add_parser("add", help="Add a change entry")
    p.add_argument("project", help="Project name")
    p.add_argument("version", help="Target version (e.g. 1.2.0)")
    p.add_argument("type", choices=CHANGE_TYPES, help="Change type")
    p.add_argument("summary", help="One-line summary")
    p.add_argument("--details", help="Extended description")
    p.add_argument("--pr", type=int, help="PR number")
    p.add_argument("--author", help="Author username")
    p.set_defaults(func=cmd_add)

    # finalize
    p = sub.add_parser("finalize", help="Finalize a release")
    p.add_argument("project", help="Project name")
    p.add_argument("version", help="Version to finalize")
    p.set_defaults(func=cmd_finalize)

    # generate-md
    p = sub.add_parser("generate-md", help="Generate Markdown changelog")
    p.add_argument("project", help="Project name")
    p.add_argument("--output", "-o", help="Output file")
    p.add_argument("--max-versions", type=int, default=5)
    p.set_defaults(func=cmd_generate_md)

    # generate-json
    p = sub.add_parser("generate-json", help="Generate JSON changelog")
    p.add_argument("project", help="Project name")
    p.add_argument("--output", "-o", help="Output file")
    p.set_defaults(func=cmd_generate_json)

    # bump
    p = sub.add_parser("bump", help="Suggest next semantic version")
    p.add_argument("project", help="Project name")
    p.add_argument("current", help="Current version (e.g. 1.2.3)")
    p.set_defaults(func=cmd_bump)

    # search
    p = sub.add_parser("search", help="Search change entries")
    p.add_argument("query", help="Search term")
    p.add_argument("--project", help="Limit to project")
    p.set_defaults(func=cmd_search)

    # list
    p = sub.add_parser("list", help="List all tracked projects and versions")
    p.set_defaults(func=cmd_list)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    db_path = Path(args.db) if getattr(args, "db", None) else None
    tracker = ChangelogTracker(db_path=db_path)
    args.func(args, tracker)


if __name__ == "__main__":
    main()
