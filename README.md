# ai-skills

Personal, project-agnostic Claude Code skills — reusable across repos, not
tied to any single project's `.claude/` directory.

## Installing a skill locally

Claude Code loads user-level skills from `~/.claude/skills/<name>/`. Symlink
the skill you want from this repo into place:

```sh
ln -s "$(pwd)/usage-review" ~/.claude/skills/usage-review
```

Symlinking (rather than copying) means `git pull` here keeps the installed
skill up to date automatically.

## Adding a new skill

Each skill is a top-level directory containing at minimum a `SKILL.md`
(frontmatter: `name`, `description`) and any supporting `scripts/` it needs.
Keep skill-generated runtime data (logs, caches, anything with personal
usage/content in it) out of this repo — add it to `.gitignore` per skill,
the way `usage-review/data/` is excluded here. This repo is public.

## Skills

- **usage-review** — bi-weekly/monthly personal review of AI-tooling usage
  (Claude Code, Devin Local): spend trend, model-selection judgment, skill
  leverage, git-history correlation, published as an Artifact.
