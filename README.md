# personal_site

## Tokens needed

| Token | What it is | Where it goes |
|---|---|---|
| **GitHub PAT** | Classic token with `repo` scope — [create one here](https://github.com/settings/tokens) | `TF_VAR_github_token` (see below) |
| **AWS credentials** | IAM user or role with Lambda + IAM permissions | `~/.aws/credentials` or env vars |

GitHub Actions does **not** need a token — the workflow uses the built-in `GITHUB_TOKEN` that Actions provides automatically.

## Deploy

```bash
cd terraform

export TF_VAR_github_token="ghp_..."

terraform init
terraform apply
# → editor_url = "https://abc123.lambda-url.us-east-1.on.aws/"
```

Open the printed URL in a browser to write posts.

## Render blog posts locally

```bash
uv run render_blog.py
git add blog_posts/ blog_metadata.json
git commit -m "render posts"
git push
```

## CI/CD

Pushing `blog_metadata.json` or any `source.md` to `master` triggers `.github/workflows/render.yml`, which installs pandoc, runs `render_blog.py`, and commits the rendered HTML back to the repo. GitHub Pages then serves the updated site automatically.

```
editor UI → Lambda → GitHub commit → Actions → pandoc → post.html → GitHub Pages
```
