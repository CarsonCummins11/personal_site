# personal_site

Static site served by GitHub Pages from `docs/`.

## Writing a post

1. Create `docs/blog_posts/<folder>/post.md`.
2. Put any images for the post in `docs/blog_posts/<folder>/` and reference them by filename (e.g. `![caption](photo.jpg)`).
3. Run `./deploy.sh` (optionally with a commit message: `./deploy.sh "add post about X"`).

`deploy.sh` runs `render_blog.py` (requires `pandoc` and `uv`), which converts post images to sRGB JPEGs (≤2000px, metadata stripped), renders each `post.md` through `blog_template.html` into `docs/blog_posts/<folder>/post.html` and updates `docs/blog_metadata.json`. New posts prompt for a title. It then commits `docs/` and pushes to `master`.
