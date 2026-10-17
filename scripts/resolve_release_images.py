"""Resolve public GHCR images and verify their source revision before deployment."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MEDIA_TYPES = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)


def resolve_image(repository: str, tag: str, revision: str) -> dict[str, str]:
    query = urlencode({"service": "ghcr.io", "scope": f"repository:{repository}:pull"})
    with urlopen(f"https://ghcr.io/token?{query}", timeout=30) as response:
        token = json.load(response)["token"]

    def get(path: str) -> tuple[dict[str, Any], str]:
        request = Request(
            f"https://ghcr.io/v2/{repository}/{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": MEDIA_TYPES},
        )
        with urlopen(request, timeout=30) as response:
            data = response.read()
            digest = response.headers.get("Docker-Content-Digest")
            return json.loads(
                data
            ), digest or f"sha256:{hashlib.sha256(data).hexdigest()}"

    manifest, digest = get(f"manifests/{tag}")
    platform_digest = digest
    if "manifests" in manifest:
        platform = next(
            item
            for item in manifest["manifests"]
            if item.get("platform", {}).get("os") == "linux"
            and item.get("platform", {}).get("architecture") == "amd64"
        )
        platform_digest = platform["digest"]
        manifest, _ = get(f"manifests/{platform_digest}")
    configuration, _ = get(f"blobs/{manifest['config']['digest']}")
    actual = (
        configuration.get("config", {})
        .get("Labels", {})
        .get("org.opencontainers.image.revision")
    )
    if actual != revision:
        raise ValueError(
            f"{repository}:{tag} source revision is {actual}, expected {revision}"
        )
    return {
        "repository": f"ghcr.io/{repository}",
        "tag": tag,
        "digest": digest,
        "platform_digest": platform_digest,
        "revision": revision,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="harish2k01/papervault")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--tag")
    parser.add_argument("--helm-values", action="store_true")
    args = parser.parse_args()
    tag = args.tag or f"sha-{args.revision[:7]}"
    resolved = {
        component: resolve_image(f"{args.repository}/{component}", tag, args.revision)
        for component in ("api", "worker", "web")
    }
    if args.helm_values:
        print(json.dumps({"image": resolved}, indent=2))
    else:
        print(json.dumps(resolved, indent=2))


if __name__ == "__main__":
    main()
