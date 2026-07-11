from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from typing import Any

import httpx


DEFAULT_PASSWORD = "ClusterSmoke123!"


def main() -> None:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    email = f"{args.email_prefix}-{int(datetime.now(timezone.utc).timestamp())}@example.test"

    with httpx.Client(verify=not args.insecure, timeout=args.request_timeout_seconds) as client:
        token = register(client, base_url, email, args.password)
        headers = {"Authorization": f"Bearer {token}"}
        document_id = upload_document(client, base_url, headers)
        detail = wait_for_processing(
            client,
            base_url,
            headers,
            document_id,
            timeout_seconds=args.processing_timeout_seconds,
        )
        search_results = search_documents(client, base_url, headers, "searchable smoke document")

    extraction = detail.get("text_extraction") or {}
    ai_analysis = detail.get("ai_analysis") or {}
    print(f"registered={email}")
    print(f"document_id={document_id}")
    print(f"document_status={detail['document']['status']}")
    print(f"extraction_status={extraction.get('status')}")
    print(f"ai_category={ai_analysis.get('category')}")
    print(f"search_results={len(search_results)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a PaperVault deployed smoke test.")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000/api",
        help="API base URL, including the /api prefix when routed through the web host.",
    )
    parser.add_argument("--email-prefix", default="cluster-smoke")
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate checks.")
    parser.add_argument("--request-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--processing-timeout-seconds", type=float, default=90.0)
    return parser.parse_args()


def register(client: httpx.Client, base_url: str, email: str, password: str) -> str:
    response = client.post(
        f"{base_url}/auth/register",
        json={"email": email, "password": password, "display_name": "Cluster Smoke"},
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload["access_token"])


def upload_document(client: httpx.Client, base_url: str, headers: dict[str, str]) -> str:
    response = client.post(
        f"{base_url}/documents/uploads",
        headers=headers,
        data={"title": "Cluster Smoke PDF", "document_type": "generic_pdf"},
        files={
            "file": (
                "cluster-smoke.pdf",
                build_pdf("Synthetic searchable smoke document for PaperVault."),
                "application/pdf",
            ),
        },
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload["document"]["id"])


def wait_for_processing(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    document_id: str,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_detail: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"{base_url}/documents/{document_id}", headers=headers)
        response.raise_for_status()
        last_detail = response.json()
        status = last_detail["document"]["status"]
        if status in {"ready", "failed"}:
            return last_detail
        time.sleep(1)
    raise TimeoutError(f"Document {document_id} did not finish processing: {last_detail}")


def search_documents(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    query: str,
) -> list[dict[str, Any]]:
    response = client.post(
        f"{base_url}/search",
        headers=headers,
        json={"query": query, "mode": "hybrid", "filters": {}, "limit": 10, "offset": 0},
    )
    response.raise_for_status()
    payload = response.json()
    return list(payload["results"])


def build_pdf(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 24 Tf 72 720 Td ({escaped}) Tj ET\n".encode("ascii")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        ),
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        (
            b"5 0 obj\n<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"endstream\nendobj\n"
        ),
    ]
    output = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = []
    for obj in objects:
        offsets.append(len(output))
        output += obj
    xref_offset = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode("ascii")
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")
    return output


if __name__ == "__main__":
    main()
