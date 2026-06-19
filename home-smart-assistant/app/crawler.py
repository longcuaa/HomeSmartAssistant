"""Crawl tai lieu tu web, trich noi dung chinh bang trafilatura, luu vao thu muc
articles de pipeline nap vao Vector DB. Ton trong robots.txt va co nghi giua cac request.
"""
import os
import re
import time
import hashlib
from urllib.parse import urlparse, urljoin
from urllib import robotparser
import requests
import trafilatura
from bs4 import BeautifulSoup
import config

_robots_cache = {}


def _allowed(url):
    """robots.txt cua site co cho phep crawl url nay khong.

    Doc robots.txt bang requests voi User-Agent that, tranh truong hop dung UA mac dinh
    cua urllib bi site tra 403 roi hieu nham thanh cam tat ca. Cache theo ten mien.
    """
    try:
        p = urlparse(url)
        host = p.netloc
        if host not in _robots_cache:
            rp = None
            try:
                r = requests.get(
                    f"{p.scheme}://{host}/robots.txt",
                    headers={"User-Agent": config.CRAWL_USER_AGENT},
                    timeout=config.CRAWL_TIMEOUT,
                )
                if r.status_code == 200 and r.text.strip():
                    rp = robotparser.RobotFileParser()
                    rp.parse(r.text.splitlines())
            except Exception:
                rp = None
            _robots_cache[host] = rp
        rp = _robots_cache[host]
        if rp is None:
            return True  # khong doc duoc robots ro rang thi mac dinh cho phep
        return rp.can_fetch(config.CRAWL_USER_AGENT, url)
    except Exception:
        return True


def _fetch(url):
    r = requests.get(url, headers={"User-Agent": config.CRAWL_USER_AGENT}, timeout=config.CRAWL_TIMEOUT)
    r.raise_for_status()
    return r.text


def _slug(url):
    h = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    p = urlparse(url)
    base = re.sub(r"[^a-zA-Z0-9]+", "-", (p.netloc + p.path)).strip("-")[:60]
    return f"{base or 'page'}-{h}.md"


def _extract(html):
    return trafilatura.extract(
        html, output_format="markdown", include_comments=False, include_tables=True
    )


def _title(html, url):
    try:
        meta = trafilatura.extract_metadata(html)
        if meta and meta.title:
            return meta.title
    except Exception:
        pass
    return url


def _save(url, html, text):
    os.makedirs(config.ARTICLES_DIR, exist_ok=True)
    path = os.path.join(config.ARTICLES_DIR, _slug(url))
    header = f"# {_title(html, url)}\n\nNguon: {url}\n\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + text)
    return path


def crawl_urls(urls, delay=None):
    """Crawl mot danh sach url cho truoc. Tra ve danh sach file da luu."""
    delay = config.CRAWL_DELAY if delay is None else delay
    saved = []
    for url in urls:
        if not _allowed(url):
            print(f"  [bo qua] robots.txt chan: {url}")
            time.sleep(delay)
            continue
        try:
            html = _fetch(url)
        except Exception as e:
            print(f"  [loi] {url}: {e}")
            time.sleep(delay)
            continue
        text = _extract(html)
        if not text or len(text.strip()) < config.CRAWL_MIN_CHARS:
            print(f"  [bo qua] trich ra qua ngan, co the la trang danh muc: {url}")
        else:
            path = _save(url, html, text)
            saved.append(path)
            print(f"  + {url} -> {os.path.basename(path)} ({len(text)} ky tu)")
        time.sleep(delay)
    return saved


def _links(html, base_url):
    out = []
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        link = urljoin(base_url, a["href"]).split("#")[0]
        if link.startswith("http"):
            out.append(link)
    return out


def crawl_site(seed_url, max_pages=20, delay=None):
    """Crawl trong cung mot ten mien tu mot url goc, toi da max_pages trang."""
    delay = config.CRAWL_DELAY if delay is None else delay
    seed_host = urlparse(seed_url).netloc
    visited, queue, saved = set(), [seed_url], []
    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        if not _allowed(url):
            print(f"  [bo qua] robots.txt chan: {url}")
            continue
        try:
            html = _fetch(url)
        except Exception as e:
            print(f"  [loi] {url}: {e}")
            continue
        text = _extract(html)
        if text and len(text.strip()) >= config.CRAWL_MIN_CHARS:
            saved.append(_save(url, html, text))
            print(f"  + {url} -> da luu")
        for link in _links(html, url):
            if urlparse(link).netloc == seed_host and link not in visited:
                queue.append(link)
        time.sleep(delay)
    return saved
