#!/usr/bin/env python3
"""Refresh youtube.json with the latest uploads from the YouTube channel.

Uses the public channel RSS feed, so no API key is required. Run by
.github/workflows/update-youtube.yml on a schedule; can also be run by hand:

    python3 scripts/fetch_youtube.py
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

HANDLE = "@saeidrafshar"
CHANNEL_ID = "UC_98EqzehlUBOwsggG1JkjA"
MAX_VIDEOS = 6
OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "youtube.json")

FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
CHANNEL_URL = "https://www.youtube.com/{}"
USER_AGENT = "Mozilla/5.0 (compatible; saeedrafsharx.github.io site updater)"

# YouTube occasionally answers a perfectly valid feed URL with a transient
# 404/5xx. Retry a few times with a short backoff before giving up.
RETRY_ATTEMPTS = 4
RETRY_DELAY_SECONDS = 5

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def get(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", "replace")
        except (urllib.error.URLError, OSError) as error:
            last_error = error
            if attempt < RETRY_ATTEMPTS:
                print("warning: fetch failed ({}), retrying in {}s ({}/{})".format(
                    error, RETRY_DELAY_SECONDS, attempt, RETRY_ATTEMPTS))
                time.sleep(RETRY_DELAY_SECONDS)
    raise last_error


def resolve_channel_id():
    """Look the channel id up from the handle, falling back to the known id."""
    try:
        page = get(CHANNEL_URL.format(HANDLE))
    except (urllib.error.URLError, OSError) as error:
        print("warning: could not load channel page ({}), using known id".format(error))
        return CHANNEL_ID

    match = re.search(r'"externalId":"(UC[A-Za-z0-9_-]{22})"', page)
    if match:
        return match.group(1)

    print("warning: no channel id found on the channel page, using known id")
    return CHANNEL_ID


def text_of(entry, path):
    node = entry.find(path, NS)
    return node.text.strip() if node is not None and node.text else ""


def parse_feed(xml):
    feed = ET.fromstring(xml)
    channel_title = text_of(feed, "atom:title")
    videos = []

    for entry in feed.findall("atom:entry", NS)[:MAX_VIDEOS]:
        video_id = text_of(entry, "yt:videoId")
        if not video_id:
            continue

        description = text_of(entry, "media:group/media:description")
        videos.append(
            {
                "id": video_id,
                "title": text_of(entry, "atom:title"),
                "url": "https://www.youtube.com/watch?v={}".format(video_id),
                "thumbnail": "https://i.ytimg.com/vi/{}/hqdefault.jpg".format(video_id),
                "published": text_of(entry, "atom:published"),
                "description": " ".join(description.split())[:220],
            }
        )

    return channel_title, videos


def main():
    channel_id = resolve_channel_id()

    try:
        xml = get(FEED_URL.format(channel_id))
    except (urllib.error.URLError, OSError) as error:
        print("error: could not fetch the feed: {}".format(error))
        return 1

    try:
        channel_title, videos = parse_feed(xml)
    except ET.ParseError as error:
        print("error: could not parse the feed: {}".format(error))
        return 1

    if not videos:
        print("error: the feed contained no videos, keeping the existing youtube.json")
        return 1

    data = {
        "channelTitle": channel_title,
        "channelId": channel_id,
        "channelUrl": CHANNEL_URL.format(HANDLE),
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "videos": videos,
    }

    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print("wrote {} video(s) for {} to {}".format(len(videos), channel_title, OUTPUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
