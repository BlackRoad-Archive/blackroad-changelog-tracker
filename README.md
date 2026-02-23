# blackroad-changelog-tracker

> Automated changelog and release notes manager with semantic versioning

Track changes per project and version, generate Markdown or JSON changelogs, and get semantic version bump suggestions based on unreleased change types.

## Features

- 📝 **Change tracking** — Record feat/fix/breaking/perf/refactor/docs/chore entries
- 🚀 **Release finalization** — Lock a version with highlights
- �� **Markdown generation** — Generate CHANGELOG.md with emoji sections
- 🔢 **Semantic versioning** — Auto-suggest next version based on pending changes
- 🔍 **Search** — Full-text search across all change summaries

## Installation

```bash
git clone https://github.com/BlackRoad-Archive/blackroad-changelog-tracker
cd blackroad-changelog-tracker
```

## Usage

### Add a change

```bash
python changelog_tracker.py add myapp 1.2.0 feat "Add dark mode toggle" \
  --author alice --pr 42
python changelog_tracker.py add myapp 1.2.0 fix "Fix login race condition" --pr 43
python changelog_tracker.py add myapp 1.2.0 breaking "Remove deprecated /v1 API"
```

### Finalize a release

```bash
python changelog_tracker.py finalize myapp 1.2.0
```

### Generate changelog

```bash
# Markdown
python changelog_tracker.py generate-md myapp --output CHANGELOG.md

# JSON
python changelog_tracker.py generate-json myapp --output changelog.json
```

### Semantic version bump

```bash
python changelog_tracker.py bump myapp 1.1.3
# → Suggested next version: 1.2.0  (because of feat changes)
```

### Search changes

```bash
python changelog_tracker.py search "dark mode"
python changelog_tracker.py search "auth" --project myapp
```

## Semantic Versioning Rules

| Change Types Present | Bump |
|---------------------|------|
| `breaking` | Major (X.0.0) |
| `feat` (no breaking) | Minor (x.Y.0) |
| `fix`, `perf`, `refactor`, `docs`, `chore` | Patch (x.y.Z) |

## Change Types

| Type | Emoji | Description |
|------|-------|-------------|
| `feat` | ✨ | New feature |
| `fix` | 🐛 | Bug fix |
| `breaking` | 💥 | Breaking change |
| `perf` | ⚡ | Performance improvement |
| `refactor` | ♻️ | Code refactoring |
| `docs` | 📝 | Documentation |
| `chore` | 🔧 | Maintenance |

## Tests

```bash
pytest tests/ -v
```
