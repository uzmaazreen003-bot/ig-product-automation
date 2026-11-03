# ig-product-automation

Free, cloud-run Instagram product marketing for **@uzmaazreen.studio**.
Runs on GitHub Actions (public repo = free minutes). Your laptop is not needed.

## What it does every day
1. 7:00 PM IST (backup run at 9:00 PM IST that does nothing if a post already went out) the workflow starts.
2. It picks the product that was promoted longest ago (never one of the last 8 posts).
3. It picks an angle for that product (showcase / benefit / audience) and builds either
   - a **Reel** (1080x1920, ~17 s, silent track, no music) or
   - a **carousel** (3-4 slides, 1080x1350),
   using the real cover image and facts from `data/products.json`.
4. It writes the caption + hashtags from the same data and publishes through Meta's official Instagram Graph API.
5. It records the post in `data/history.json`. If anything fails, a GitHub Issue is opened (you get an email).

Weekly pattern (IST): Mon Reel · Tue Carousel · Wed Reel · Thu Carousel · Fri Reel · Sat Reel · Sun Carousel.
Change it in `data/config.json` -> `schedule_ist`.

## Nothing is invented
Captions and on-screen text only use text from `data/products.json` (copied from your Payhip pages).
No AI service is used for writing, so there is nothing that can hallucinate a feature, price or discount.
To change a price or wording, edit that file on GitHub (pencil icon) and commit.

## Secrets
Only one secret is needed: `IG_ACCESS_TOKEN` (Settings -> Secrets and variables -> Actions).
The Instagram account ID is not secret and lives in `data/config.json`.

## Try it without posting
Actions -> **Post to Instagram** -> Run workflow -> keep **dry_run** ticked -> Run.
When it finishes, open the run and download the **generated-post** artifact to see the video/images and caption.
Untick dry_run (and optionally pick a format) to publish for real.

## Add a new product
Add an entry to `data/products.json` (copy an existing one). It joins the rotation automatically.

## If the token stops working
You get an Issue saying so. Meta dashboard -> your app -> Use cases -> Customize -> API setup -> **Generate token**,
then update the `IG_ACCESS_TOKEN` secret. History and schedule are untouched.

## Notes
- Scheduled GitHub workflows can start a few minutes late (sometimes much later at busy hours); that is why there is a backup run.
- GitHub pauses scheduled workflows in a public repo after 60 days without repo activity. Every successful post commits
  `data/history.json`, so the repo stays active.
- Optional natural-sound background: put an mp3 at `assets/ambient.mp3` and set `"ambient_audio": "assets/ambient.mp3"` in config. Default is silent.
- Local tests: `python -m tests.test_publish`, `python -m tests.test_rotation`, `python -m tests.test_e2e` (they use a fake Instagram server).

## Voice-over (ElevenLabs)
Set `voice.voice_id` in `data/config.json` to your ElevenLabs voice ID and add the secret `ELEVENLABS_API_KEY`.
The voice reads only the hook, product title/subtitle, the 3 points and the price/CTA line from `data/products.json`.
Roughly 350-450 characters per Reel. If the key/credits are missing the Reel is built silent and the run log says why.
Set `"enabled": false` to switch the voice off. No music is ever added.
