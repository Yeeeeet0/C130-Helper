"""C-130J ASC Airfield & Procedure Desk: packaged Windows desktop host.

Reads SQLite using Python's bundled sqlite3 and renders the existing HTML
interface in an embedded native window. All database reads are non-mutating.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import sqlite3
import sys
from pathlib import Path
from cdu_helper import CduApi

APP_TITLE = "C-130J | Route & CDU Desk"
ASC_SOURCE = "ASC_C130J_NAV_DATA"
TOKEN = "__EMBEDDED_DATABASE_JSON__"


def bundled_base() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def locate_files() -> tuple[Path, Path]:
    base = bundled_base()
    template = base / "assets" / "template.html"
    database = base / "assets" / "caucasus.sqlite"
    # Optional user-supplied database update, beside the packaged EXE.
    # The bundled DB stays the fallback, so the EXE works on its own.
    if getattr(sys, "frozen", False):
        override = Path(sys.executable).resolve().parent / "data" / "caucasus.sqlite"
        if override.is_file():
            database = override
    return database, template


def fetch_rows(connection: sqlite3.Connection, sql: str) -> list[dict]:
    return [dict(row) for row in connection.execute(sql)]


def table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name=?)", (name,)
    ).fetchone()[0] == 1


def build_page(database: Path, template: Path) -> tuple[str, dict]:
    if not database.is_file():
        raise FileNotFoundError(f"Missing database: {database}")
    if not template.is_file():
        raise FileNotFoundError(f"Missing app template: {template}")

    with sqlite3.connect(str(database)) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        required = ("airfields", "runways", "runway_ends", "comm_frequencies", "navaids", "procedures", "procedure_legs")
        absent = [name for name in required if not table_exists(con, name)]
        if absent:
            raise ValueError("SQLite database is missing required tables: " + ", ".join(absent))
        db = {
            "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "data_version": "ASC-only procedures / Caucasus / Desktop",
            "airfields": fetch_rows(con, "SELECT * FROM airfields ORDER BY dcs_name"),
            "runways": fetch_rows(con, "SELECT * FROM runways"),
            "runway_ends": fetch_rows(con, "SELECT * FROM runway_ends"),
            "comm_frequencies": fetch_rows(con, "SELECT * FROM comm_frequencies"),
        }
        if table_exists(con, "navaid_positions"):
            navaid_sql = "SELECT n.*, np.lat_deg, np.lon_deg FROM navaids n LEFT JOIN navaid_positions np ON np.navaid_id=n.navaid_id"
        else:
            navaid_sql = "SELECT n.*, NULL AS lat_deg, NULL AS lon_deg FROM navaids n"
        db["navaids"] = fetch_rows(con, navaid_sql)
        # Filter to ASC source even if the external SQLite contains old chart procedures.
        db["procedures"] = fetch_rows(con, "SELECT * FROM procedures WHERE source_id='ASC_C130J_NAV_DATA'")
        db["procedure_legs"] = fetch_rows(con, "SELECT l.* FROM procedure_legs l JOIN procedures p ON p.procedure_id=l.procedure_id WHERE p.source_id='ASC_C130J_NAV_DATA'")

    page = template.read_text(encoding="utf-8")
    display = (bundled_base() / 'assets' / 'display.js').read_text(encoding='utf-8')
    page = page.replace('<head>', '<head><script>' + display + '</script>', 1)
    airspeed=(bundled_base()/'assets'/'airspeed.js').read_text(encoding='utf-8')
    page=page.replace('<head>','<head><script>'+airspeed+'</script>',1)
    if page.count(TOKEN) != 1:
        raise ValueError("Invalid app template: expected exactly one embedded-data placeholder")
    payload = json.dumps(db, ensure_ascii=False, separators=(",", ":"))
    payload = (payload.replace("&", "\\u0026")
                      .replace("<", "\\u003c")
                      .replace(">", "\\u003e"))
    page = page.replace(TOKEN, payload)
    helper = bundled_base() / 'assets' / 'helper.html'
    if helper.is_file():
        page = page.replace('</body>', '<div class="container entry-workspace">' + helper.read_text(encoding='utf-8') + '</div></body>')
    map_html = bundled_base() / 'assets' / 'map.html'
    if map_html.is_file():
        page = page.replace('<main class="container">', '<main class="container reference-workspace">', 1)
        page = page.replace('<body>', '<body data-workspace="map">' + map_html.read_text(encoding='utf-8'), 1)
        map_js = (bundled_base() / 'assets' / 'map.js').read_text(encoding='utf-8')
        page = page.replace('</body>', '<script>' + map_js + '</script></body>')
        planner = (bundled_base() / 'assets' / 'planner.html').read_text(encoding='utf-8')
        for token,name in [('__HELPER_LICENCE__','LICENSE.txt'),
                           ('__HELPER_THIRD_PARTY__','THIRD_PARTY_NOTICES.txt')]:
            planner=planner.replace(token,html.escape((bundled_base()/name).read_text(encoding='utf-8')))
        planner_js = (bundled_base() / 'assets' / 'planner.js').read_text(encoding='utf-8')
        page = page.replace('</body>', planner + '<script>' + planner_js + '</script></body>')
    return page, db


def show_error(message: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, APP_TITLE + " - error", 0x10)
    except Exception:
        print(message, file=sys.stderr)


def main() -> int:
    try:
        database, template = locate_files()
        page, records = build_page(database, template)
        if "--self-test" in sys.argv:
            from help_documents import TOPICS,document_path
            for topic in TOPICS:
                with document_path(topic).open('rb') as help_pdf:
                    assert help_pdf.read(5)==b'%PDF-'
            import io
            from PIL import Image,DdsImagePlugin,PngImagePlugin
            with Image.new('RGBA',(2,2)) as probe:
                target=io.BytesIO();probe.save(target,format='PNG')
                assert target.getvalue().startswith(b'\x89PNG')
            print("Database:", database)
            print("Airfields:", len(records["airfields"]))
            print("ASC SIDs:", sum(x.get("procedure_type") == "SID" for x in records["procedures"]))
            print("ASC STARs:", sum(x.get("procedure_type") == "STAR" for x in records["procedures"]))
            print("Embedded JSON length:", len(page))
            return 0
        import webview
        api = CduApi()
        window = webview.create_window(
            APP_TITLE,
            html=page,
            width=1460,
            height=900,
            min_size=(900, 640),
            resizable=True,
            text_select=True,
            js_api=api,
        )
        api._window = window
        window.events.closing += lambda: api.stop()
        # Force Chromium WebView2 rather than the legacy MSHTML renderer.
        webview.start(gui="edgechromium", private_mode=True)
        return 0
    except Exception as ex:
        show_error(str(ex) + "\n\nThe C-130J data was not changed. "
                   "Ensure Microsoft Edge WebView2 Runtime is installed if the window cannot start.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
