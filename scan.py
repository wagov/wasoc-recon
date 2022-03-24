#!/usr/bin/env python3
import os, json
from subprocess import run
from pathlib import Path
from time import time

cwd = Path(__file__).resolve(strict=True).parent

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
run(
    [
        "curl",
        "-o",
        cwd / "outputs" / "rumble_services.json",
        *header_args,
        f"{api}/export/org/services.json",
    ]
)
ips = {}
for row in json.load((cwd / "outputs" / "rumble_services.json").open()):
    if row["site_name"] not in ips:
        ips[row["site_name"]] = set()
    for ip in row["addresses"]:
        ips[row["site_name"]].add(ip)
json.dump(ips, (cwd / "outputs" / "rumble_ips.json").open("w"), default=list)
# Potentially insecure services export
search = """alive:t AND (not transport:icmp)
AND ((protocol:"tls" AND (tls.supportedVersionNames:"SSL" OR tls.supportedVersionNames:"TLSv1.0" OR tls.supportedVersionNames:"TLSv1.1")) OR (not protocol:tls))
AND ((protocol:http AND (http.code:<=300 OR http.code:>=400)) OR (not protocol:http))
"""
run(
    [
        "curl",
        "-o",
        cwd / "outputs" / "rumble_services_insecure.json",
        *header_args,
        "--data-urlencode",
        f"search={search}",
        f"{api}/export/org/services.json",
    ]
)


rumble_sites = {}
for site in json.loads(rumble_sites_file.open().read()):
    rumble_sites[site["name"]] = site["id"]


for site in cwd.glob("inputs/*.domains.txt"):
    name = site.name.split(".domains")[0]
    subdomains = cwd / "outputs" / f"{name}.subdomains.txt"
    print(f"Enumerating {name} subdomains...")
    new = subdomains.with_suffix(".new")
    cmd = ["docker", "run", "-v", f"{cwd}:{cwd}", "caffix/amass",
        "amass",
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
