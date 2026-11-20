import io
import json
import os
import re
import sys
from datetime import datetime

from PIL import Image, ImageCms, ImageOps

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
MAX_EDGE = 2000
JPEG_QUALITY = 85
SRGB = ImageCms.createProfile("sRGB")
SRGB_ICC = ImageCms.ImageCmsProfile(SRGB).tobytes()


def _profile_name(im):
    icc = im.info.get("icc_profile")
    if not icc:
        return None
    try:
        return ImageCms.getProfileDescription(
            ImageCms.ImageCmsProfile(io.BytesIO(icc))
        ).strip()
    except Exception:
        return "unknown"


def _looks_like_screen_capture(path, profile):
    with open(path, "rb") as f:
        head = f.read(64 * 1024)
    return b"iDOT" in head or (profile is not None and "LCD" in profile)


def normalize_images(folder):
    img_dir = f"docs/blog_posts/{folder}"
    source_path = f"docs/blog_posts/{folder}/post.md"
    if not os.path.isdir(img_dir):
        return
    with open(source_path) as f:
        source = f.read()
    original_source = source

    for name in sorted(os.listdir(img_dir)):
        stem, ext = os.path.splitext(name)
        if ext.lower() not in IMAGE_EXTS:
            continue
        path = os.path.join(img_dir, name)
        im = Image.open(path)
        profile = _profile_name(im)
        is_srgb = profile is None or "srgb" in profile.lower()
        if (
            im.format == "JPEG"
            and im.mode == "RGB"
            and is_srgb
            and max(im.size) <= MAX_EDGE
        ):
            continue

        if _looks_like_screen_capture(path, profile):
            print(
                f"  warning: {path} looks like a screenshot of a photo "
                f"(profile: {profile}); highlights may be clipped. "
                f"Export the original from Photos instead."
            )

        im = ImageOps.exif_transpose(im)
        icc = im.info.get("icc_profile")
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            im = Image.alpha_composite(bg, im)
        im = im.convert("RGB")
        if icc and not is_srgb:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            im = ImageCms.profileToProfile(
                im, src, SRGB, renderingIntent=ImageCms.Intent.PERCEPTUAL
            )
        assert im
        im.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)

        new_name = name if ext.lower() in (".jpg", ".jpeg") else f"{stem}.jpeg"
        new_path = os.path.join(img_dir, new_name)
        if new_name != name and os.path.exists(new_path):
            print(f"  skipping {path}: {new_path} already exists")
            continue
        im.save(
            new_path, "JPEG", quality=JPEG_QUALITY, optimize=True, icc_profile=SRGB_ICC
        )
        if new_name != name:
            os.remove(path)
            source = re.sub(
                r"\]\(" + re.escape(name) + r"([\s)])", f"]({new_name}\\1", source
            )
        print(f"  normalized {path} -> {new_name} (was {profile or 'no profile'})")

    if source != original_source:
        with open(source_path, "w") as f:
            f.write(source)


with open("docs/blog_metadata.json") as f:
    blog_metadata = json.load(f)
blog_folders = sorted(
    d
    for d in os.listdir("docs/blog_posts")
    if os.path.isfile(f"docs/blog_posts/{d}/post.md")
)
folder_to_titles = {}
folder_to_dates = {}
revised_blog_metadata = []
for post in blog_metadata:
    if post["folder"] in blog_folders:
        revised_blog_metadata.append(post)
        folder_to_titles[post["folder"]] = post["title"]
        folder_to_dates[post["folder"]] = post["published_date"]
    else:
        print(f"Removing post: {post['title']}")
for folder in blog_folders:
    if folder not in folder_to_titles:
        title = input(f"Post title for folder: {folder}:   ")
        date = datetime.now().strftime("%m/%d/%Y")
        revised_blog_metadata.append(
            {
                "title": title,
                "folder": folder,
                "published_date": date,
            }
        )
        folder_to_titles[folder] = title
        folder_to_dates[folder] = date
    title = folder_to_titles[folder]
    date = folder_to_dates[folder]
    if folder not in folder_to_titles or len(sys.argv) > 0:
        print(f"re-rendering {folder}")

        normalize_images(folder)
        os.system(
            f"pandoc docs/blog_posts/{folder}/post.md "
            f"-o docs/blog_posts/{folder}/post.html "
            f'--metadata title="{title}" '
            f'--metadata date="{date}" '
            f"--template=blog_template.html "
            f"--standalone "
            f"--css=../../blog_style.css"
        )
with open("docs/blog_metadata.json", "w") as f:
    json.dump(revised_blog_metadata, f)
