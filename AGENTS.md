# Agents

This repository uses Copilot agents to extend the assistant with specialized workflows.

## Available Agents

- `Explore`
  - Purpose: fast read-only codebase exploration and Q&A.
  - Best use: searching for definitions, file locations, and understanding code structure before editing.
  - Typical tasks: find usages, inspect files, summarize repository sections.

## Repository structure

- `src/`
  - Main Flask application code.
  - `src/app.py` is the entrypoint for the Flask app.
  - `src/blueprints/` contains route blueprints like `admin_bp.py`, `blog_bp.py`, `auth_bp.py`, `movies_bp.py`, and others.
  - `src/templates/` contains Jinja templates used by the app.
  - `src/static/` contains CSS, scripts, and assets.
  - `src/utils.py` contains shared helpers, email sending, data loading, and Redis integration.

- `data/`
  - Stores runtime content such as `blog_posts.json`, `blog_subscribers.json`, `users.json`, movie metadata, and media folders.

- `docs/`
  - Developer and deployment documentation, including installation and content addition guides.

- `Dockerfile` and `docker-compose.yml`
  - Build and run the app inside containers.

- `pyproject.toml`
  - Python dependencies and project metadata.

## Common workflows

- `Explore` is useful when you need to understand how a feature is implemented before changing it.
- Use it to locate template files, request handlers, and utility functions.
- It can also help identify where data files are loaded or saved, especially for blog, movie, and user data.

## Notes

- This file is informational only and does not affect repo execution.
- Add more agents here if custom agents are introduced later.
