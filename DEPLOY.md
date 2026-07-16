# Deploying this (no coding experience needed)

You're going two places: **GitHub** (where the code sits) and **Render**
(where it actually runs). Both are free for this.

## Part 1 — Put the code on GitHub

1. Go to github.com and sign up (free).
2. Click the **+** in the top right → **New repository**.
3. Name it `subverify-backend`. Leave it Public or Private (either is fine —
   Private just means strangers can't browse the code). Click **Create repository**.
4. On the next page, click **uploading an existing file**.
5. Unzip the file I gave you on your computer first (double-click the .zip).
6. Drag the **contents** of the unzipped `subverify-backend` folder into the
   GitHub upload box — all the files and folders (`app`, `README.md`,
   `render.yaml`, `requirements.txt`, `.gitignore`, `.env.example`, `uploads`).
   Don't drag the outer folder itself, just what's inside it.
7. Scroll down, click **Commit changes**. Done — your code is on GitHub.

## Part 2 — Deploy it on Render

1. Go to render.com and sign up — choose **"Sign up with GitHub"** so the two
   are connected automatically.
2. Click **New +** → **Blueprint**.
3. Pick the `subverify-backend` repo you just created.
4. Render will find the `render.yaml` file in the project and fill in almost
   everything by itself (build command, start command, a free disk to keep
   your data, and a random secret key). Click **Apply** / **Create**.
5. Wait a couple of minutes while it builds. When it's done, Render gives you
   a URL like `https://subverify-backend.onrender.com` — that's your live
   backend.

## Using it day to day

- Interactive docs (to create packets, get QR codes, review documents) live at:
  `https://subverify-backend.onrender.com/docs`
  You can do everything from that page by clicking into each endpoint — no
  coding needed, just filling in boxes and clicking "Execute."
- The link you send a subcontractor looks like:
  `https://subverify-backend.onrender.com/pay/<their-token>`
- **Heads up:** on Render's free tier, the app "falls asleep" after 15 minutes
  of no visitors, and takes 30-ish seconds to wake back up on the next visit.
  At ~30 submissions a year, that's basically the only tradeoff of free
  hosting, and it's a non-issue for this use case.

## If something needs fixing later

Come back to me — I can make changes to the code here, and you'd just repeat
the GitHub upload step (upload the changed files, commit) and Render
redeploys automatically within a minute or two.
