"""
AWS Lambda handler for the blog post editor.

Environment variables:
  GITHUB_TOKEN   - GitHub PAT with repo write scope
  REPO_OWNER     - GitHub username/org (default: CarsonCummins11)
  REPO_NAME      - GitHub repo name (default: personal_site)

Expects an AWS Lambda function URL or API Gateway proxy integration.
Commits source.md + blog_metadata.json to GitHub; a GitHub Actions workflow
(.github/workflows/render.yml) runs render_blog.py to produce the HTML.
"""

import base64
import json
import os
import re
import urllib.parse
from datetime import datetime, timezone

from github import Github, GithubException, UnknownObjectException

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_OWNER = os.environ.get("REPO_OWNER", "CarsonCummins11")
REPO_NAME = os.environ.get("REPO_NAME", "personal_site")

# Initialised once per container so warm invocations reuse the session.
_repo = Github(GITHUB_TOKEN).get_repo(f"{REPO_OWNER}/{REPO_NAME}")

# ---------------------------------------------------------------------------
# HTML editor page
# ---------------------------------------------------------------------------

EDITOR_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>New Blog Post</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #f5f5f5;
    color: #1a1a1a;
  }
  header {
    background: #1a1a1a;
    color: #f5f5f5;
    padding: 0.75rem 1.5rem;
    display: flex;
    align-items: center;
    gap: 1rem;
  }
  header h1 { margin: 0; font-size: 1rem; font-weight: 600; letter-spacing: 0.05em; }
  .container { max-width: 1200px; margin: 0 auto; padding: 1.5rem; }
  .fields {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 1rem;
    margin-bottom: 1rem;
  }
  .field { display: flex; flex-direction: column; gap: 0.3rem; }
  label { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; color: #666; }
  input[type=text], input[type=date], input[type=password] {
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 0.5rem 0.75rem;
    font-size: 0.95rem;
    width: 100%;
    background: #fff;
  }
  input:focus { outline: none; border-color: #1a1a1a; }
  .editor-panes {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
    height: 60vh;
  }
  .pane-label {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    color: #999;
    margin-bottom: 0.25rem;
  }
  textarea {
    width: 100%;
    height: 100%;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 0.75rem;
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 0.85rem;
    line-height: 1.6;
    resize: none;
    background: #fff;
  }
  textarea:focus { outline: none; border-color: #1a1a1a; }
  .preview {
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 0.75rem 1.25rem;
    overflow-y: auto;
    background: #fff;
    font-size: 0.95rem;
    line-height: 1.7;
    height: 100%;
  }
  .preview img { max-width: 100%; }
  .actions { margin-top: 1rem; display: flex; gap: 0.75rem; align-items: center; }
  button[type=submit] {
    background: #1a1a1a;
    color: #fff;
    border: none;
    padding: 0.6rem 1.5rem;
    font-size: 0.95rem;
    border-radius: 4px;
    cursor: pointer;
  }
  button[type=submit]:hover { background: #333; }
  button[type=submit]:disabled { background: #999; cursor: not-allowed; }
  .status { font-size: 0.85rem; color: #666; }
  .status.error { color: #c0392b; }
  .status.ok { color: #27ae60; }
  .hint { font-size: 0.75rem; color: #999; margin-top: 0.2rem; }
</style>
</head>
<body>
<header><h1>Blog Post Editor</h1></header>
<div class="container">
  <form id="post-form">
    <div class="fields">
      <div class="field">
        <label for="title">Title</label>
        <input type="text" id="title" name="title" placeholder="My Adventure Post" required>
      </div>
      <div class="field">
        <label for="slug">Folder slug</label>
        <input type="text" id="slug" name="slug" placeholder="adventure_jun19" required>
        <span class="hint">blog_posts/<span id="slug-preview">…</span>/source.md</span>
      </div>
      <div class="field">
        <label for="date">Date</label>
        <input type="date" id="date" name="date" required>
      </div>
    </div>
    __TOKEN_FIELD__
    <div class="editor-panes">
      <div>
        <div class="pane-label">Markdown</div>
        <textarea id="md" name="markdown" placeholder="Write your post in Markdown…" required></textarea>
      </div>
      <div>
        <div class="pane-label">Preview</div>
        <div class="preview" id="preview"></div>
      </div>
    </div>
    <div class="actions">
      <button type="submit" id="submit-btn">Publish</button>
      <span class="status" id="status"></span>
    </div>
  </form>
</div>
<script>
  const d = new Date();
  document.getElementById('date').value = d.toISOString().slice(0,10);

  document.getElementById('slug').addEventListener('input', e => {
    document.getElementById('slug-preview').textContent = e.target.value || '…';
  });

  const md = document.getElementById('md');
  const preview = document.getElementById('preview');
  md.addEventListener('input', () => { preview.innerHTML = marked.parse(md.value); });

  document.getElementById('post-form').addEventListener('submit', async e => {
    e.preventDefault();
    const btn = document.getElementById('submit-btn');
    const status = document.getElementById('status');
    btn.disabled = true;
    status.className = 'status';
    status.textContent = 'Publishing…';

    const form = new FormData(e.target);
    const raw = form.get('date');
    const [y,m,day] = raw.split('-');
    form.set('date', m+'/'+day+'/'+y);

    try {
      const resp = await fetch(window.location.pathname, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams(form),
      });
      const text = await resp.text();
      if (resp.ok) {
        status.className = 'status ok';
        status.textContent = text;
        e.target.reset();
        document.getElementById('date').value = new Date().toISOString().slice(0,10);
        preview.innerHTML = '';
        document.getElementById('slug-preview').textContent = '…';
      } else {
        status.className = 'status error';
        status.textContent = 'Error: ' + text;
      }
    } catch (err) {
      status.className = 'status error';
      status.textContent = 'Network error: ' + err.message;
    } finally {
      btn.disabled = false;
    }
  });
</script>
</body>
</html>
"""

def _build_editor() -> str:
    return EDITOR_HTML.replace("__TOKEN_FIELD__", "")


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------

def _parse_body(event: dict) -> dict:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode()
    ct = (event.get("headers") or {}).get("content-type", "")
    if "application/json" in ct:
        return json.loads(body) if body else {}
    return dict(urllib.parse.parse_qsl(body))


def _response(status: int, body: str, content_type="text/plain"):
    return {
        "statusCode": status,
        "headers": {"Content-Type": content_type},
        "body": body,
    }


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def handler(event, context):
    method = (
        event.get("httpMethod")
        or event.get("requestContext", {}).get("http", {}).get("method", "GET")
    )

    if method == "GET":
        return _response(200, _build_editor(), "text/html")

    if method != "POST":
        return _response(405, "Method Not Allowed")

    data = _parse_body(event)

    title = data.get("title", "").strip()
    slug = data.get("slug", "").strip()
    markdown = data.get("markdown", "").strip()
    date = data.get("date", datetime.now(timezone.utc).strftime("%m/%d/%Y"))

    if not title or not slug or not markdown:
        return _response(400, "title, slug, and markdown are required")

    slug = re.sub(r"[^a-z0-9_-]", "_", slug.lower())

    try:
        # Reject duplicate slugs
        try:
            _repo.get_contents(f"blog_posts/{slug}")
            return _response(409, f"A post with slug '{slug}' already exists")
        except UnknownObjectException:
            pass

        # Commit metadata FIRST so render_blog.py never hits the input() branch
        # when the workflow fires on the source.md push.
        meta_file = _repo.get_contents("blog_metadata.json")
        meta = json.loads(meta_file.decoded_content)
        meta.append({"title": title, "folder": slug, "published_date": date})
        _repo.update_file(
            "blog_metadata.json",
            f"update metadata for: {title}",
            json.dumps(meta, indent=2),
            meta_file.sha,
        )

        # Commit source.md — this push triggers the render workflow.
        _repo.create_file(
            f"blog_posts/{slug}/source.md",
            f"add blog post: {title}",
            markdown,
        )

        return _response(200, f'Post "{title}" published — GitHub Actions will render the HTML.')

    except GithubException as e:
        return _response(502, f"GitHub error {e.status}: {e.data.get('message', str(e))}")
    except Exception as e:
        return _response(500, str(e))
