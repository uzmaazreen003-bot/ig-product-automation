"""Instagram publishing through Meta's official Graph API (graph.facebook.com, unified login token).

Flow (official two-step container model):
  1. create a media container (Reel / image / carousel children + carousel)
  2. wait until it is FINISHED
  3. media_publish

Reels are uploaded with Meta's resumable upload when possible (no public hosting needed) and
fall back to video_url (the file hosted on the repo's `media` branch).
"""
from __future__ import annotations

import os
import time

import requests

GRAPH = os.environ.get("GRAPH_BASE", "https://graph.facebook.com").rstrip("/")
RUPLOAD = os.environ.get("RUPLOAD_BASE", "https://rupload.facebook.com").rstrip("/")
SLEEP = float(os.environ.get("PUBLISH_POLL_SLEEP", "8"))


class PublishError(Exception):
    def __init__(self, message, code=None, subcode=None, transient=False, kind="api"):
        super().__init__(message)
        self.code, self.subcode, self.transient, self.kind = code, subcode, transient, kind


def _classify(resp):
    try:
        err = resp.json().get("error", {})
    except Exception:
        err = {}
    code, sub = err.get("code"), err.get("error_subcode")
    msg = err.get("message") or resp.text[:300]
    kind = "api"
    if code == 190:
        kind = "token"
    elif code in (4, 17, 32, 613) or sub == 2207042:
        kind = "rate_limit"
    transient = resp.status_code >= 500 or code in (1, 2, 4, 17, 32, 613) and kind != "token"
    return PublishError(f"HTTP {resp.status_code}: {msg}", code, sub, transient, kind)


def call(method, url, token, *, params=None, data=None, headers=None, body=None, retries=3):
    delay = 3
    for attempt in range(retries + 1):
        try:
            hdrs = dict(headers or {})
            if method == "GET":
                resp = requests.get(url, params={**(params or {}), "access_token": token}, timeout=60)
            elif body is not None:
                resp = requests.post(url, data=body, headers=hdrs, timeout=600)
            else:
                resp = requests.post(url, data={**(data or {}), "access_token": token}, headers=hdrs, timeout=120)
        except requests.RequestException as exc:
            if attempt == retries:
                raise PublishError(f"Network error: {exc}", transient=True, kind="network")
            time.sleep(delay); delay *= 2
            continue
        if resp.ok:
            try:
                return resp.json()
            except ValueError:
                return {}
        err = _classify(resp)
        if err.transient and attempt < retries:
            time.sleep(delay); delay *= 2
            continue
        raise err
    raise PublishError("unreachable")


def wait_for_url(url, timeout=90):
    """Raw GitHub content can take a few seconds to appear after the push."""
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            r = requests.get(url, stream=True, timeout=30)
            ok = r.status_code == 200
            r.close()
            if ok:
                return
            last = r.status_code
        except requests.RequestException as exc:
            last = str(exc)
        time.sleep(4)
    raise PublishError(f"Media URL not reachable: {url} ({last})", kind="media_url")


def wait_ready(container_id, token, timeout=900):
    end = time.time() + timeout
    while time.time() < end:
        info = call("GET", f"{GRAPH}/{container_id}", token, params={"fields": "status_code,status"})
        status = info.get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise PublishError(f"Container {container_id} {status}: {info.get('status')}", kind="container")
        time.sleep(SLEEP)
    raise PublishError(f"Container {container_id} not ready after {timeout}s", kind="container")


def quota(ig_id, token):
    try:
        info = call("GET", f"{GRAPH}/{ig_id}/content_publishing_limit", token, params={"fields": "quota_usage,config"}, retries=1)
        return (info.get("data") or [{}])[0].get("quota_usage")
    except PublishError:
        return None


def _create(ig_id, token, **fields):
    return call("POST", f"{GRAPH}/{ig_id}/media", token, data=fields)


def _publish(ig_id, token, container_id):
    res = call("POST", f"{GRAPH}/{ig_id}/media_publish", token, data={"creation_id": container_id})
    return res["id"]


def _permalink(media_id, token):
    try:
        return call("GET", f"{GRAPH}/{media_id}", token, params={"fields": "permalink"}, retries=1).get("permalink")
    except PublishError:
        return None


def publish_reel(plan, ig_id, token, method="auto"):
    video_path = plan["files"][0]
    caption = plan["caption"]
    container = None
    if method in ("auto", "resumable"):
        try:
            made = _create(ig_id, token, media_type="REELS", caption=caption, share_to_feed="true", upload_type="resumable")
            container = made["id"]
            size = os.path.getsize(video_path)
            upload_url = made.get("uri") or f"{RUPLOAD}/ig-api-upload/{container}"
            with open(video_path, "rb") as fh:
                call("POST", upload_url, token, body=fh.read(),
                     headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)})
            wait_ready(container, token)
            print("[publish] reel uploaded with resumable upload")
        except PublishError as exc:
            if exc.kind == "token" or method == "resumable":
                raise
            print(f"[publish] resumable upload failed ({exc}); falling back to video_url")
            container = None
    if container is None:
        url = plan["media_urls"][0]
        wait_for_url(url)
        made = _create(ig_id, token, media_type="REELS", caption=caption, share_to_feed="true", video_url=url)
        container = made["id"]
        wait_ready(container, token)
    media_id = _publish(ig_id, token, container)
    return media_id, _permalink(media_id, token)


def publish_carousel(plan, ig_id, token):
    children = []
    for url in plan["media_urls"]:
        wait_for_url(url)
        made = _create(ig_id, token, image_url=url, is_carousel_item="true")
        children.append(made["id"])
    for cid in children:
        wait_ready(cid, token, timeout=300)
    made = _create(ig_id, token, media_type="CAROUSEL", children=",".join(children), caption=plan["caption"])
    wait_ready(made["id"], token, timeout=300)
    media_id = _publish(ig_id, token, made["id"])
    return media_id, _permalink(media_id, token)


def publish_plan(plan, ig_id, token, video_method="auto"):
    used = quota(ig_id, token)
    if used is not None and used >= 45:
        raise PublishError(f"Publishing quota nearly used up ({used}/50 in 24h)", kind="rate_limit")
    if plan["format"] == "reel":
        return publish_reel(plan, ig_id, token, video_method)
    return publish_carousel(plan, ig_id, token)
