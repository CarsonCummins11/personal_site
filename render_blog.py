import json
import os
import sys
from datetime import datetime

with open("docs/blog_metadata.json") as f:
    blog_metadata = json.load(f)
blog_folders = os.listdir("blog_posts")
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

        os.makedirs(f"docs/blog_posts/{folder}", exist_ok=True)
        os.system(
            f"pandoc ./blog_posts/{folder}/source.md "
            f"-o docs/blog_posts/{folder}/post.html "
            f'--metadata title="{title}" '
            f'--metadata date="{date}" '
            f"--template=blog_template.html "
            f"--standalone "
            f"--css=../../blog_style.css"
        )
with open("docs/blog_metadata.json", "w") as f:
    json.dump(revised_blog_metadata, f)
