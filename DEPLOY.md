# Deploying this (no coding experience needed)

You're going three places, all free:

1. **GitHub** — where the code sits
2. **Neon** — a free database that stores everything permanently (subcontractors, documents, packets)
3. **Render** — where the app actually runs

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

## Part 2 — Create your free database on Neon

1. Go to **neon.tech** and sign up (free — "Sign up with GitHub" is fine here too).
2. Create a new project — any name is fine, e.g. `subverify`.
3. Once it's created, look for a **Connection string** on the project dashboard.
   It'll look like:
   `postgresql://username:password@ep-something.neon.tech/dbname?sslmode=require`
4. **Copy that whole string** — you'll paste it into Render in the next part.
   Keep the tab open, or paste it into a notes app for a moment.

## Part 3 — Deploy it on Render

1. Go to render.com and sign up — choose **"Sign up with GitHub"**.
2. Click **New +** → **Blueprint**.
3. If it says "No repositories found," click the black **GitHub** button
   under "Connect a repository," and on the GitHub screen that pops up,
   grant access to your `subverify-backend` repo. Then come back and pick it.
4. On the review screen, it'll ask you to fill in one value: **DATABASE_URL**.
   Paste in the Neon connection string you copied in Part 2.
5. Click **Apply** / **Create**. Wait a couple of minutes while it builds.
6. When it's done, Render gives you a URL like
   `https://subverify-backend.onrender.com` — that's your live backend.

## Important — resetting your database

The app's structure changed since you first deployed (this version adds the
self-service link and the approve/deny-with-a-reason flow). Your existing
Neon database has the *old* structure, so before deploying this update you
need to clear it out — it only has your one test submission in it, so nothing
real is lost.

1. Go to your Neon project → **SQL Editor** (in the left sidebar).
2. Paste this in and run it:
   ```sql
   DROP TABLE IF EXISTS packet_documents, payment_packets, alerts, documents,
     project_subcontractors, subcontractors, projects, accounts CASCADE;
   ```
3. That's it — the next time your app starts up on Render, it automatically
   recreates all the tables fresh with the new structure.

## Using it day to day

Go to `https://subverify-backend.onrender.com/app` — that's your dashboard.
No API docs needed for normal use:

- **Create an account** the first time for each client (one account per
  client — each gets its own link and branding).
- **Log in** to see that client's dashboard: their permanent link + QR code,
  a branding section (logo + welcome message), and a list of submissions.
- Share the link/QR with subcontractors. They register themselves and upload
  their three documents — no account needed on their end.
- When a submission shows **"Needs your review,"** click into it, view each
  file, and Approve or Deny with a note.
- **Heads up:** on Render's free tier, the app "falls asleep" after 15
  minutes of no visitors, and takes 30-ish seconds to wake back up on the
  next visit. At your volume, that's the only real tradeoff of free hosting.
- Neon's free tier is permanent — no time limit, no credit card required at
  this scale.

## If something needs fixing later

Come back to me — I can make changes to the code here, and you'd just repeat
the GitHub upload step (upload the changed files, commit) and Render
redeploys automatically within a minute or two. The database on Neon stays
put the whole time — updates to the app don't touch your data.
