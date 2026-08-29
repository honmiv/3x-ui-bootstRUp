import io
import json
import os
import secrets
import shutil
import string
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from typing import Any, Dict, List, Optional

REPO_ROOT = os.path.dirname(os.path.abspath(globals().get("__file__", sys.argv[0] if sys.argv and sys.argv[0] else os.getcwd())))
CACHE_DIR = os.path.join(REPO_ROOT, ".cache", "decoys")
DEFAULT_HTML_DIR = os.path.join(REPO_ROOT, "common", "templates", "nginx-decoy", "html")
DEFAULT_ERRORS_DIR = os.path.join(DEFAULT_HTML_DIR, "errors")

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

DEFAULT_DECOYS: List[Dict[str, Any]] = [
    {
        "id": "builtin",
        "name": "📄 Документация (Workspace Documentation)",
        "description": "Встроенная страница документации и заметок рабочего пространства.",
        "type": "builtin",
        "badge": "Встроено",
        "preview_image": "",
    },
    {
        "id": "game-2048",
        "name": "🎮 Игра 2048 (Gabriele Cirulli)",
        "description": "Классическая веб-игра 2048. Полностью интерактивная, чистый HTML/JS/CSS.",
        "repo": "gabrielecirulli/2048",
        "branch": "master",
        "subpath": "",
        "type": "github",
        "badge": "Игра",
        "preview_image": "https://raw.githubusercontent.com/gabrielecirulli/2048/master/meta/apple-touch-startup-image-640x920.png",
    },
    {
        "id": "game-hextris",
        "name": "🔷 Игра Hextris (Гексагональный тетрис)",
        "description": "Интерактивная браузерная HTML5-игра головоломка с вращением шестиугольника.",
        "repo": "Hextris/hextris",
        "branch": "gh-pages",
        "subpath": "",
        "type": "github",
        "badge": "Игра",
        "preview_image": "https://raw.githubusercontent.com/Hextris/hextris/gh-pages/images/facebook-opengraph.png",
    },
    {
        "id": "agency-landing",
        "name": "🏢 Корпоративный лендинг (StartBootstrap Agency)",
        "description": "Сайт диджитал-агентства / сервисной компании с портфолио, услугами и контактами.",
        "repo": "StartBootstrap/startbootstrap-agency",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Бизнес",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/themes/agency.png",
    },
    {
        "id": "landing-page",
        "name": "🚀 Промо-лендинг продукта (StartBootstrap Landing)",
        "description": "Чистый адаптивный лендинг для презентации онлайн-сервиса или продукта.",
        "repo": "StartBootstrap/startbootstrap-landing-page",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Лендинг",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/themes/landing-page.png",
    },
    {
        "id": "creative",
        "name": "🎨 Креативная студия (StartBootstrap Creative)",
        "description": "Эффектный лендинг для дизайн-студии, фотографа или креативного агентства.",
        "repo": "StartBootstrap/startbootstrap-creative",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Студия",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/themes/creative.png",
    },
    {
        "id": "new-age",
        "name": "📱 Мобильное приложение (StartBootstrap New Age)",
        "description": "Презентация мобильного приложения с кнопками магазинов (App Store / Google Play).",
        "repo": "StartBootstrap/startbootstrap-new-age",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "App",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/themes/new-age.png",
    },
    {
        "id": "business-casual",
        "name": "☕ Кафе / Кофейня / Пекарня (Business Casual)",
        "description": "Уютный сайт кофейни или ресторана с меню, историей и часами работы.",
        "repo": "StartBootstrap/startbootstrap-business-casual",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Кафе",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/themes/business-casual.png",
    },
    {
        "id": "clean-blog",
        "name": "📝 Личный блог (StartBootstrap Clean Blog)",
        "description": "Статический чистый блог со статьями и заметками о технологиях и путешествиях.",
        "repo": "StartBootstrap/startbootstrap-clean-blog",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Блог",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/themes/clean-blog.png",
    },
    {
        "id": "freelancer-portfolio",
        "name": "💼 Портфолио услуг (StartBootstrap Freelancer)",
        "description": "Сайт-визитка специалиста/фрилансера с галереей проектов и отзывами.",
        "repo": "StartBootstrap/startbootstrap-freelancer",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Портфолио",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/themes/freelancer.png",
    },
    {
        "id": "stylish-portfolio",
        "name": "🎯 Дизайн-портфолио (StartBootstrap Stylish)",
        "description": "Портфолио с боковым меню (off-canvas), секциями услуг и портфолио работ.",
        "repo": "StartBootstrap/startbootstrap-stylish-portfolio",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Портфолио",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/themes/stylish-portfolio.png",
    },
    {
        "id": "grayscale",
        "name": "🌌 Промо-лендинг продукта (StartBootstrap Grayscale)",
        "description": "Стильный темный промо-лендинг для презентации продукта или приложения.",
        "repo": "StartBootstrap/startbootstrap-grayscale",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Лендинг",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/themes/grayscale.png",
    },
    {
        "id": "coming-soon",
        "name": "⏳ Скоро открытие (StartBootstrap Coming Soon)",
        "description": "Страница «Сайт в разработке / Скоро открытие» с формой подписки на запуск.",
        "repo": "StartBootstrap/startbootstrap-coming-soon",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Скоро",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/themes/coming-soon.png",
    },
    {
        "id": "resume",
        "name": "📄 Интерактивное резюме (StartBootstrap Resume)",
        "description": "Классическое онлайн-резюме специалиста с опытом и навыками.",
        "repo": "StartBootstrap/startbootstrap-resume",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Резюме",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/themes/resume.png",
    },
    {
        "id": "shop-homepage",
        "name": "🛍️ Каталог интернет-магазина (Shop Homepage)",
        "description": "Витрина онлайн-магазина с карточками товаров, ценами и рейтингами.",
        "repo": "StartBootstrap/startbootstrap-shop-homepage",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Магазин",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/templates/shop-homepage.png",
    },
    {
        "id": "small-business",
        "name": "🏢 Малый бизнес и консалтинг (Small Business)",
        "description": "Деловой сайт локальной компании или консалтингового бюро с блоком преимуществ.",
        "repo": "StartBootstrap/startbootstrap-small-business",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Бизнес",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/templates/small-business.png",
    },
    {
        "id": "modern-business",
        "name": "🌐 Корпоративный портал (Modern Business)",
        "description": "Полноразмерный сайт IT-компании или организации с разделами о нас, ценами и блогом.",
        "repo": "StartBootstrap/startbootstrap-modern-business",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Корпоративный",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/templates/modern-business.png",
    },
    {
        "id": "heroic-features",
        "name": "⚡ Витрина возможностей и сервисов (Heroic Features)",
        "description": "Лендинг с акцентным баннером и сеткой карточек ключевых возможностей продукта.",
        "repo": "StartBootstrap/startbootstrap-heroic-features",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Лендинг",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/templates/heroic-features.png",
    },
    {
        "id": "blog-home",
        "name": "📰 Информационный журнал (Blog Home)",
        "description": "Сайт новостного издания, журнала или медиа-ресурса с категориями и виджетами.",
        "repo": "StartBootstrap/startbootstrap-blog-home",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Медиа",
        "preview_image": "https://assets.startbootstrap.com/img/screenshots/templates/blog-home.png",
    },
    {
        "id": "portfolio-item",
        "name": "🖼️ Презентация проекта и кейса (Portfolio Item)",
        "description": "Страница демонстрации архитектурного, дизайнерского или программного кейса.",
        "repo": "StartBootstrap/startbootstrap-portfolio-item",
        "branch": "master",
        "subpath": "dist",
        "type": "github",
        "badge": "Кейс",
        "preview_image": "https://opengraph.githubassets.com/1/StartBootstrap/startbootstrap-portfolio-item",
    },
    {
        "id": "game-floppybird",
        "name": "🐦 Игра Floppy Bird (HTML5 Canvas)",
        "description": "Популярный аркадный клон Flappy Bird на чистом JavaScript и Canvas.",
        "repo": "nebez/floppybird",
        "branch": "master",
        "subpath": "",
        "type": "github",
        "badge": "Игра",
        "preview_image": "https://raw.githubusercontent.com/nebez/floppybird/master/assets/thumb.png",
    },
    {
        "id": "game-tower",
        "name": "🏗️ Игра Tower Building (Башня из блоков)",
        "description": "Красочная физическая 3D-игра на Canvas по строительству высокой башни из блоков.",
        "repo": "iamkun/tower_game",
        "branch": "master",
        "subpath": "",
        "type": "github",
        "badge": "Игра",
        "preview_image": "https://raw.githubusercontent.com/iamkun/tower_game/master/assets/icon.png",
    },
]


def is_decoy_cached(decoy_id: str) -> bool:
    if decoy_id == "builtin":
        return os.path.isdir(DEFAULT_HTML_DIR) and os.path.isfile(os.path.join(DEFAULT_HTML_DIR, "index.html"))
    
    target_dir = os.path.join(CACHE_DIR, decoy_id)
    return os.path.isdir(target_dir) and os.path.isfile(os.path.join(target_dir, "index.html"))


def get_decoy_catalog() -> List[Dict[str, Any]]:
    catalog: List[Dict[str, Any]] = []
    for item in DEFAULT_DECOYS:
        entry = dict(item)
        entry["is_cached"] = is_decoy_cached(item["id"])
        catalog.append(entry)
    return catalog


def get_decoy_meta(decoy_id: str) -> Optional[Dict[str, Any]]:
    for item in DEFAULT_DECOYS:
        if item["id"] == decoy_id:
            return dict(item)
    return None


def _safe_extract_tar(tf: tarfile.TarFile, target_dir: str) -> None:
    for member in tf.getmembers():
        target_path = os.path.abspath(os.path.join(target_dir, member.name))
        if not target_path.startswith(os.path.abspath(target_dir) + os.sep) and target_path != os.path.abspath(target_dir):
            raise ValueError(f"Illegal path in archive: {member.name}")
    tf.extractall(target_dir)


def _safe_extract_zip(zf: zipfile.ZipFile, target_dir: str) -> None:
    for name in zf.namelist():
        target_path = os.path.abspath(os.path.join(target_dir, name))
        if not target_path.startswith(os.path.abspath(target_dir) + os.sep) and target_path != os.path.abspath(target_dir):
            raise ValueError(f"Illegal path in archive: {name}")
    zf.extractall(target_dir)


def _fetch_archive_bytes(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _ensure_errors_merged(target_dir: str) -> None:
    if not os.path.isdir(DEFAULT_ERRORS_DIR):
        return
    errors_dest = os.path.join(target_dir, "errors")
    os.makedirs(errors_dest, exist_ok=True)
    for fn in os.listdir(DEFAULT_ERRORS_DIR):
        src_file = os.path.join(DEFAULT_ERRORS_DIR, fn)
        dst_file = os.path.join(errors_dest, fn)
        if os.path.isfile(src_file) and not os.path.exists(dst_file):
            try:
                shutil.copy2(src_file, dst_file)
            except Exception:
                pass


def ensure_decoy_cached(decoy_id: str, custom_url: str = "", force: bool = False) -> str:
    if decoy_id == "builtin":
        return DEFAULT_HTML_DIR

    target_dir = os.path.join(CACHE_DIR, decoy_id)
    if not force and is_decoy_cached(decoy_id):
        return target_dir

    meta = get_decoy_meta(decoy_id)
    download_urls: List[str] = []

    if meta and meta.get("repo"):
        repo = meta["repo"]
        branch = meta.get("branch", "master")
        download_urls.append(f"https://github.com/{repo}/archive/refs/heads/{branch}.tar.gz")
        if branch == "master":
            download_urls.append(f"https://github.com/{repo}/archive/refs/heads/main.tar.gz")
        subpath = meta.get("subpath", "")
    elif custom_url:
        c_url = custom_url.strip()
        subpath = ""
        if "/" in c_url and not c_url.startswith("http://") and not c_url.startswith("https://"):
            # Format: owner/repo
            download_urls.append(f"https://github.com/{c_url}/archive/refs/heads/main.tar.gz")
            download_urls.append(f"https://github.com/{c_url}/archive/refs/heads/master.tar.gz")
        else:
            download_urls.append(c_url)
    else:
        raise ValueError(f"Unknown decoy id: {decoy_id}")

    data: Optional[bytes] = None
    last_err: Optional[Exception] = None

    for u in download_urls:
        try:
            data = _fetch_archive_bytes(u)
            if data:
                break
        except Exception as e:
            last_err = e

    if not data:
        raise RuntimeError(f"Failed to download decoy archive from {download_urls}: {last_err}")

    with tempfile.TemporaryDirectory() as tmp_extract:
        # Try extracting as tar.gz first, then as zip
        extracted = False
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
                _safe_extract_tar(tf, tmp_extract)
                extracted = True
        except Exception:
            pass

        if not extracted:
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    _safe_extract_zip(zf, tmp_extract)
                    extracted = True
            except Exception as e:
                raise RuntimeError(f"Failed to unpack archive: {e}")

        # Locate root directory with index.html
        source_content_dir = ""
        if subpath:
            # Check with subpath in top extracted dirs
            for entry in os.listdir(tmp_extract):
                cand = os.path.join(tmp_extract, entry, subpath)
                if os.path.isdir(cand) and os.path.isfile(os.path.join(cand, "index.html")):
                    source_content_dir = cand
                    break

        if not source_content_dir:
            # Look for index.html recursively
            candidates = []
            for root, _, files in os.walk(tmp_extract):
                if "index.html" in files:
                    candidates.append(root)
            if candidates:
                # Pick the shallowest directory with index.html
                candidates.sort(key=lambda p: len(p.split(os.sep)))
                source_content_dir = candidates[0]

        if not source_content_dir or not os.path.isfile(os.path.join(source_content_dir, "index.html")):
            raise RuntimeError(f"Decoy archive does not contain 'index.html'")

        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        os.makedirs(target_dir, exist_ok=True)

        for item in os.listdir(source_content_dir):
            s = os.path.join(source_content_dir, item)
            d = os.path.join(target_dir, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)

        _ensure_errors_merged(target_dir)

    return target_dir


def get_decoy_bundle_files(decoy_id: str = "builtin", custom_url: str = "", randomize: bool = True) -> Dict[str, bytes]:
    decoy_id = (decoy_id or "builtin").strip()
    if decoy_id == "custom" and not custom_url:
        decoy_id = "builtin"

    dir_path = ensure_decoy_cached(decoy_id, custom_url=custom_url)
    files_map: Dict[str, bytes] = {}

    for root, _, files in os.walk(dir_path):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, dir_path).replace(os.sep, "/")
            try:
                with open(full, "rb") as fp:
                    content = fp.read()
                files_map[rel] = content
            except Exception:
                pass

    if randomize and "index.html" in files_map:
        raw_html = files_map["index.html"].decode("utf-8", errors="replace")
        alphabet = string.ascii_letters + string.digits + string.punctuation.replace("-", "")
        nonce_len = secrets.randbelow(45) + 20
        nonce = "".join(secrets.choice(alphabet) for _ in range(nonce_len))
        nonce_tag = f"\n<!-- {nonce} -->\n"
        if "</body>" in raw_html:
            raw_html = raw_html.replace("</body>", f"{nonce_tag}</body>", 1)
        elif "</html>" in raw_html:
            raw_html = raw_html.replace("</html>", f"{nonce_tag}</html>", 1)
        else:
            raw_html += nonce_tag
        files_map["index.html"] = raw_html.encode("utf-8")

    return files_map
