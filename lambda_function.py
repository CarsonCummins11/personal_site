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
import email
import json
import os
import re
import urllib.parse
from datetime import datetime, timezone

from github import Github, GithubException, UnknownObjectException

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_OWNER = os.environ.get("REPO_OWNER", "CarsonCummins11")
REPO_NAME = os.environ.get("REPO_NAME", "personal_site")

_repo = Github(GITHUB_TOKEN).get_repo(f"{REPO_OWNER}/{REPO_NAME}")

# ---------------------------------------------------------------------------
# Static assets — loaded once at cold start
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_HERE, "editor.html")) as f:
    _EDITOR_HTML = f.read()
with open(os.path.join(_HERE, "editor.css")) as f:
    _EDITOR_CSS = f.read()
with open(os.path.join(_HERE, "editor.js")) as f:
    _EDITOR_JS = f.read()

# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------


def _parse_multipart(body_bytes: bytes, content_type: str):
    """Parse multipart/form-data. Returns (fields: dict, files: list of (filename, bytes))."""
    raw = b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body_bytes
    msg = email.message_from_bytes(raw)
    fields: dict = {}
    files: list = []
    payload = msg.get_payload()
    if not isinstance(payload, list):
        return fields, files
    for part in payload:
        cd = part.get("Content-Disposition", "")
        name = None
        filename = None
        for token in cd.split(";"):
            token = token.strip()
            if token.lower().startswith("name="):
                name = token[5:].strip('"')
            elif token.lower().startswith("filename="):
                filename = token[9:].strip('"')
        if not name:
            continue
        data = part.get_payload(decode=True) or b""
        if filename:
            files.append((filename, data))
        else:
            fields[name] = data.decode("utf-8")
    return fields, files


def _parse_body(event: dict):
    """Returns (fields: dict, files: list of (filename, bytes))."""
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body_bytes = base64.b64decode(body)
    else:
        body_bytes = body.encode() if isinstance(body, str) else body
    ct = (event.get("headers") or {}).get("content-type", "")
    if "application/json" in ct:
        return (json.loads(body_bytes.decode()) if body_bytes else {}), []
    if "multipart/form-data" in ct:
        return _parse_multipart(body_bytes, ct)
    return dict(urllib.parse.parse_qsl(body_bytes.decode())), []


def _response(status: int, body: str, content_type="text/plain"):
    return {
        "statusCode": status,
        "headers": {"Content-Type": content_type},
        "body": body,
    }


# ---------------------------------------------------------------------------
# GET sub-handlers
# ---------------------------------------------------------------------------

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg"}


def _handle_list() -> dict:
    try:
        f = _repo.get_contents("docs/blog_metadata.json")
        return _response(200, f.decoded_content.decode(), "application/json")
    except Exception as e:
        return _response(500, str(e))


def _handle_load(slug: str) -> dict:
    if not slug:
        return _response(400, "slug is required")
    slug = re.sub(r"[^a-z0-9_-]", "_", slug.lower())
    try:
        md_file = _repo.get_contents(f"blog_posts/{slug}/source.md")
        markdown = md_file.decoded_content.decode("utf-8")

        meta_raw = _repo.get_contents("docs/blog_metadata.json")
        meta = json.loads(meta_raw.decoded_content)
        post_meta = next((p for p in meta if p["folder"] == slug), {})

        try:
            contents = _repo.get_contents(f"docs/blog_posts/{slug}")
            images = [
                {"name": c.name, "url": c.download_url}
                for c in contents
                if c.type == "file"
                and os.path.splitext(c.name)[1].lower() in _IMAGE_EXTS
            ]
        except Exception:
            images = []

        return _response(
            200,
            json.dumps(
                {
                    "title": post_meta.get("title", ""),
                    "date": post_meta.get("published_date", ""),
                    "markdown": markdown,
                    "images": images,
                }
            ),
            "application/json",
        )
    except UnknownObjectException:
        return _response(404, f"Post '{slug}' not found")
    except Exception as e:
        return _response(500, str(e))


# ---------------------------------------------------------------------------
# POST sub-handlers
# ---------------------------------------------------------------------------


def _handle_upload_image(event: dict) -> dict:
    """Upload a single image for a given slug. Called before main form submit."""
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body_bytes = base64.b64decode(body)
    else:
        body_bytes = body.encode() if isinstance(body, str) else body
    ct = (event.get("headers") or {}).get("content-type", "")
    _, files = _parse_multipart(body_bytes, ct)
    if not files:
        return _response(400, "no image provided")

    slug = (event.get("queryStringParameters") or {}).get("slug", "").strip()
    slug = re.sub(r"[^a-z0-9_-]", "_", slug.lower())
    if not slug:
        return _response(400, "slug is required")

    filename, img_bytes = files[0]
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    path = f"docs/blog_posts/{slug}/{safe_name}"
    try:
        try:
            existing = _repo.get_contents(path)
            _repo.update_file(
                path, f"update image {safe_name}", img_bytes, existing.sha
            )
        except UnknownObjectException:
            _repo.create_file(path, f"add image {safe_name}", img_bytes)
        return _response(200, json.dumps({"name": safe_name}), "application/json")
    except GithubException as e:
        return _response(
            502, f"GitHub error {e.status}: {e.data.get('message', str(e))}"
        )
    except Exception as e:
        return _response(500, str(e))


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def handler(event, context):
    method = event.get("httpMethod") or event.get("requestContext", {}).get(
        "http", {}
    ).get("method", "GET")

    if method == "GET":
        path = event.get("rawPath", "/")
        if path == "/editor.css":
            return _response(200, _EDITOR_CSS, "text/css")
        if path == "/editor.js":
            return _response(200, _EDITOR_JS, "application/javascript")
        qs = event.get("queryStringParameters") or {}
        action = qs.get("action", "")
        if action == "list":
            return _handle_list()
        if action == "load":
            return _handle_load(qs.get("slug", ""))
        return _response(200, _EDITOR_HTML, "text/html")

    if method != "POST":
        return _response(405, "Method Not Allowed")

    qs = event.get("queryStringParameters") or {}
    if qs.get("action") == "upload-image":
        return _handle_upload_image(event)

    data, _ = _parse_body(event)

    title = data.get("title", "").strip()
    slug = data.get("slug", "").strip()
    markdown = data.get("markdown", "").strip()
    date = data.get("date", datetime.now(timezone.utc).strftime("%m/%d/%Y"))

    if not title or not slug or not markdown:
        return _response(400, "title, slug, and markdown are required")

    slug = re.sub(r"[^a-z0-9_-]", "_", slug.lower())
    is_edit = data.get("edit") == "true"

    try:
        if is_edit:
            # ---- Update existing post ----
            try:
                src_file = _repo.get_contents(f"blog_posts/{slug}/source.md")
            except UnknownObjectException:
                return _response(404, f"Post '{slug}' not found")

            meta_file = _repo.get_contents("docs/blog_metadata.json")
            meta = json.loads(meta_file.decoded_content)
            updated = False
            for i, p in enumerate(meta):
                if p["folder"] == slug:
                    meta[i] = {"title": title, "folder": slug, "published_date": date}
                    updated = True
                    break
            if not updated:
                meta.append({"title": title, "folder": slug, "published_date": date})
            _repo.update_file(
                "docs/blog_metadata.json",
                f"update metadata for: {title}",
                json.dumps(meta, indent=2),
                meta_file.sha,
            )

            # Update source.md — triggers the render workflow
            _repo.update_file(
                f"blog_posts/{slug}/source.md",
                f"update blog post: {title}",
                markdown,
                src_file.sha,
            )

            return _response(
                200, f'Post "{title}" updated — GitHub Actions will render the HTML.'
            )

        else:
            # ---- Create new post ----
            try:
                _repo.get_contents(f"blog_posts/{slug}")
                return _response(409, f"A post with slug '{slug}' already exists")
            except UnknownObjectException:
                pass

            # Commit metadata FIRST so render_blog.py never hits the input() branch
            # when the workflow fires on the source.md push.
            meta_file = _repo.get_contents("docs/blog_metadata.json")
            meta = json.loads(meta_file.decoded_content)
            meta.append({"title": title, "folder": slug, "published_date": date})
            _repo.update_file(
                "docs/blog_metadata.json",
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

            return _response(
                200, f'Post "{title}" published — GitHub Actions will render the HTML.'
            )

    except GithubException as e:
        return _response(
            502, f"GitHub error {e.status}: {e.data.get('message', str(e))}"
        )
    except Exception as e:
        return _response(500, str(e))
