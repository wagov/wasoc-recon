#!/usr/bin/env python3
import os, json
from subprocess import run
from pathlib import Path
from time import time

cwd = Path(__file__).resolve(strict=True).parent

# Load cached data from Blob Storage
run(["az", "storage", "blob", "download-batch", "-d", cwd.parent, 
    "-s", os.environ["BLOB_CONTAINER"],  "--connection-string", os.environ["AZURE_STORAGE_CONNECTION_STRING"],
    "--pattern",  "rumble/*"])
# Make amass executable
run(["chmod", "+x", cwd/"amass"])


RUMBLE_API_TOKEN = os.environ.get("RUMBLE_API_TOKEN", False)
if not RUMBLE_API_TOKEN:
    exec((cwd / ".env").open().read())

api = "https://console.rumble.run/api/v1.0"
header_args = [
    "-H",
    f"Authorization: Bearer {RUMBLE_API_TOKEN}",
    "-H",
    "Content-Type: application/json",
]

rumble_sites_file = cwd / "outputs" / "rumble_sites.json"
run(["curl", "-o", rumble_sites_file, *header_args, f"{api}/org/sites"])
# All services export
run(["curl", "-o", cwd / "outputs" / "rumble_services.json", *header_args, f"{api}/export/org/services.json"])


rumble_sites = {}
for site in json.loads(rumble_sites_file.open().read()):
    rumble_sites[site["name"]] = site["id"]


for site in cwd.glob("inputs/*.domains.txt"):
    name = site.name.split(".domains")[0]
    subdomains = cwd / "outputs" / f"{name}.subdomains.txt"
    print(f"Enumerating {name} subdomains...")
    new = subdomains.with_suffix(".new")
    cmd = [
        cwd / "amass",
        "enum",
        "-active",
        "-df",
        site,
        "-dir",
        cwd / "amassdb",
        "-o",
        new,
    ]
    if subdomains.exists():
        cmd += ["-nf", subdomains]
    run(cmd)
    new.replace(subdomains)
    data = json.dumps(
        {
            "name": name.upper(),
            "description": f"{name} scope amass enumerated subdomains",
            "scope": " ".join(subdomains.open().read().splitlines()),
        }
    )
    sitename = name.upper()
    if sitename in rumble_sites:
        url = f"{api}/org/sites/{rumble_sites[sitename]}"
        print(f"Updating existing site for {sitename} at {url}")
        run(["curl", *header_args, "-d", data, "-X", "PATCH", url])
    else:
        url = f"{api}/org/sites"
        print(f"Creating new site for {sitename} at {url}")
        run(["curl", *header_args, "-d", data, "-X", "PUT", url])

run(["az", "storage", "blob", "upload-batch", "-d", os.environ["BLOB_CONTAINER"], "-s", cwd.parent, "--overwrite", "true"
    "--connection-string", os.environ["AZURE_STORAGE_CONNECTION_STRING"], "--pattern",  "rumble/*"])