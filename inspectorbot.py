"""
Local inspection API consumed by browserscript.js.

Run:
    python inspectorbot.py

Endpoints:
    GET  /api/health
    GET  /browserscript.js
    POST /api/inspect/progress
    POST /api/inspect/report
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests


HOST = os.getenv("INSPECTORBOT_HOST", "127.0.0.1")
PORT = int(os.getenv("INSPECTORBOT_PORT", "8765"))
OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    "",
)
MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
REPORT_DIR = Path(os.getenv("INSPECTORBOT_REPORT_DIR", "inspector_reports"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    handler.end_headers()
    handler.wfile.write(body)


def text_response(
    handler: BaseHTTPRequestHandler,
    status: int,
    body_text: str,
    content_type: str = "text/plain; charset=utf-8",
) -> None:
    body = body_text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0") or "0")
    if content_length <= 0:
        return {}

    raw = handler.rfile.read(content_length)
    try:
        body = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON body: {exc}") from exc

    if not isinstance(body, dict):
        raise ValueError("JSON body must be an object")
    return body


def summarize_pages(pages: list[dict[str, Any]]) -> dict[str, Any]:
    unique_links = {
        link.get("href")
        for page in pages
        for link in page.get("navLinks", [])
        if isinstance(link, dict) and link.get("href")
    }
    return {
        "pages": len(pages),
        "forms": sum(len(page.get("forms", [])) for page in pages),
        "tables": sum(len(page.get("tables", [])) for page in pages),
        "buttons": sum(len(page.get("buttons", [])) for page in pages),
        "uniqueNavigationLinks": len(unique_links),
    }


def build_system_prompt(report: dict[str, Any]) -> str:
    target = report.get("target") or {}
    pages = report.get("pages") or []
    summary = summarize_pages(pages if isinstance(pages, list) else [])

    return f"""You are Codex, acting as a senior product engineer.
The browser has inspected an existing ISP/customer billing system in read-only
mode and sent you the structural report below.

Your job is to produce an implementation blueprint that is detailed enough to
rebuild the same ISP system: pages, navigation, data models, permissions,
API endpoints, workflows, and a practical build plan.

Do not claim the scraper clicked, submitted, deleted, or mutated anything.
Make careful inferences from the observed UI only, and label inferred details
as inferred.

Target:
{json.dumps(target, ensure_ascii=False, indent=2)}

Summary:
{json.dumps(summary, ensure_ascii=False, indent=2)}

Full browser inspection report:
{json.dumps(report, ensure_ascii=False, indent=2)}
"""


def build_local_blueprint(report: dict[str, Any]) -> str:
    pages = report.get("pages") if isinstance(report.get("pages"), list) else []
    target = report.get("target") if isinstance(report.get("target"), dict) else {}
    summary = summarize_pages(pages)
    lines = [
        "# ISP System Rebuild Blueprint",
        "",
        "## Assessment Summary",
        f"- Target: {target.get('origin') or '-'}",
        f"- Current URL: {target.get('currentUrl') or '-'}",
        f"- Pages captured: {summary['pages']}",
        f"- Forms found: {summary['forms']}",
        f"- Tables found: {summary['tables']}",
        f"- Buttons found: {summary['buttons']}",
        f"- Unique navigation links: {summary['uniqueNavigationLinks']}",
        "",
        "## Observed Pages",
    ]

    for page in pages:
        lines.extend(
            [
                "",
                f"### {page.get('title') or page.get('url') or 'Untitled page'}",
                f"- URL: {page.get('url') or '-'}",
                f"- Headings: {', '.join(h.get('text', '') for h in page.get('headings', []) if h.get('text')) or '-'}",
                f"- Forms: {len(page.get('forms', []))}",
                f"- Tables: {len(page.get('tables', []))}",
                f"- Buttons: {', '.join(button.get('text', '') for button in page.get('buttons', [])[:12] if button.get('text')) or '-'}",
            ]
        )

        nav = page.get("navLinks", [])
        if nav:
            lines.append("- Navigation:")
            for link in nav[:30]:
                lines.append(f"  - {link.get('text') or link.get('path')}: {link.get('href')}")

        forms = page.get("forms", [])
        if forms:
            lines.append("- Form inventory:")
            for form in forms:
                field_names = [
                    field.get("label") or field.get("name") or field.get("placeholder") or field.get("type")
                    for field in form.get("fields", [])
                ]
                lines.append(f"  - {form.get('method', 'GET')} {form.get('action') or '-'}: {', '.join(field_names) or '-'}")

    lines.extend(
        [
            "",
            "## Build Notes",
            "- Recreate the ISP tenant dashboard with one Users page that includes active/inactive filtering.",
            "- Include packages, payments, vouchers, expenses, messages, email notices, tickets, leads, MikroTik routers, equipment, and tenant settings.",
            "- Exclude campaigns from the implementation.",
            "- Treat observed details as read-only evidence; inferred modules should be clearly modeled as admin workflows.",
        ]
    )
    return "\n".join(lines)


def call_openrouter(report: dict[str, Any]) -> str:
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY.endswith("YOUR_KEY_HERE"):
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Return only a clear Markdown rebuild blueprint.",
            },
            {"role": "user", "content": build_system_prompt(report)},
        ],
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=180,
    )

    if response.status_code != 200:
        raise RuntimeError(f"OpenRouter error {response.status_code}: {response.text[:500]}")

    result = response.json()
    if "error" in result:
        raise RuntimeError(f"OpenRouter API error: {result['error']}")

    return result["choices"][0]["message"].get("content", "")


def save_report(report: dict[str, Any], blueprint: str | None = None) -> dict[str, str]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = safe_timestamp()
    base = REPORT_DIR / f"inspection_{ts}"
    report_path = base.with_suffix(".json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    paths = {"reportPath": str(report_path)}
    if blueprint:
        blueprint_path = base.with_suffix(".md")
        blueprint_path.write_text(blueprint, encoding="utf-8")
        paths["blueprintPath"] = str(blueprint_path)
    return paths


def save_progress(event: dict[str, Any]) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    event.setdefault("receivedAt", utc_now())
    progress_path = REPORT_DIR / "progress.log"
    with progress_path.open("a", encoding="utf-8") as file:
      file.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(f"[progress] {event.get('event', 'unknown')} {event.get('url', '')}")
    return {"ok": True, "message": "Progress received.", "progressPath": str(progress_path)}


def handle_report(report: dict[str, Any]) -> dict[str, Any]:
    pages = report.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("Report must include a non-empty pages array")

    report.setdefault("receivedAt", utc_now())
    summary = summarize_pages(pages)
    blueprint = build_local_blueprint(report)
    paths = save_report(report, blueprint)

    return {
        "ok": True,
        "message": "Inspection report received and local blueprint generated.",
        "model": "local-blueprint",
        "summary": summary,
        "blueprint": blueprint,
        **paths,
    }


class InspectorBotHandler(BaseHTTPRequestHandler):
    server_version = "InspectorBot/1.0"

    def do_OPTIONS(self) -> None:
        json_response(self, 204, {})

    def do_GET(self) -> None:
        path = self.path.rstrip("/")
        if path == "/browserscript.js":
            script_path = Path(__file__).with_name("browserscript.js")
            if not script_path.exists():
                text_response(self, 404, "browserscript.js not found")
                return
            text_response(
                self,
                200,
                script_path.read_text(encoding="utf-8"),
                "application/javascript; charset=utf-8",
            )
            return

        if path == "/api/health":
            json_response(
                self,
                200,
                {
                    "ok": True,
                    "service": "inspectorbot",
                    "model": MODEL,
                    "time": utc_now(),
                },
            )
            return
        json_response(self, 404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:
        path = self.path.rstrip("/")
        if path not in ("/api/inspect/progress", "/api/inspect/report"):
            json_response(self, 404, {"ok": False, "error": "Not found"})
            return

        try:
            body = read_json_body(self)
            payload = save_progress(body) if path == "/api/inspect/progress" else handle_report(body)
        except ValueError as exc:
            json_response(self, 400, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            save_report(body if "body" in locals() else {"error": str(exc)})
            json_response(self, 502, {"ok": False, "error": str(exc)})
            return

        json_response(self, 200, payload)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{utc_now()}] {self.address_string()} {format % args}")


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), InspectorBotHandler)
    print(f"InspectorBot API running at http://{HOST}:{PORT}")
    print("Browser script endpoint: /api/inspect/report")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping InspectorBot API.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
