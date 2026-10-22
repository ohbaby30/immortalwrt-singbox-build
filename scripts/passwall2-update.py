#!/usr/bin/env python3
"""Prepare and verify the repository's universal PassWall2 APKs."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from zoneinfo import ZoneInfo


def update_url(repository):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid GitHub repository")
    return f"https://raw.githubusercontent.com/{repository}/passwall2-update/passwall2-release-api.json"


def replace_once(text, pattern, replacement):
    result, count = re.subn(pattern, lambda _: replacement, text, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"Upstream layout changed: expected one match for {pattern!r}, got {count}")
    return result


def prepare(source, repository, created_at, run_id, attempt, upstream_commit, output, build_number=1):
    # Version all three numeric components, including i18n, independently of upstream.
    # A rerun gets a new language version too, even when upstream PKG_VERSION is unchanged.
    started = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    if started.tzinfo is None or run_id < 1 or attempt < 1 or build_number < 1:
        raise ValueError("Expected a timezone-aware run timestamp and positive run identifiers")
    if not re.fullmatch(r"[0-9a-f]{40}", upstream_commit):
        raise ValueError("Expected an exact upstream commit SHA")
    local_date = started.astimezone(ZoneInfo("Asia/Shanghai"))
    day = local_date.strftime("%Y%m%d")
    version = f"{day}.{run_id}.{attempt}"
    url = update_url(repository)
    makefile = source / "Makefile"
    comfile = source / "luasrc/passwall2/com.lua"
    apifile = source / "luasrc/passwall2/api.lua"
    viewfile = source / "luasrc/view/passwall2/app_update/app_version.htm"
    make, com, api = makefile.read_text(), comfile.read_text(), apifile.read_text()
    if not re.search(r"^LUCI_PKGARCH\s*:?=\s*all\s*$", make, re.MULTILINE):
        raise ValueError("PassWall2 is no longer a universal LuCI package")
    # Fail closed if the self updater or exact-name selection contract disappears.
    for marker in ("function to_check_self()", "com[appname]:get_url()", "release.tag_name",
                   'asset.name == main_name', 'release.assets', 'function to_install_self('):
        if marker not in api:
            raise ValueError(f"Upstream self updater changed: missing {marker}")
    if not (source / "root/usr/share/passwall2/luci_update.sh").is_file():
        raise ValueError("Upstream self installer is missing")
    upstream_version = re.search(r"^PKG_VERSION\s*:?=\s*(\S+)", make, re.MULTILINE)
    if not upstream_version:
        raise ValueError("Upstream version is missing")
    upstream_version = upstream_version[1]
    upstream_release = re.search(r"^PKG_RELEASE\s*:?=\s*(\d+)\s*$", make, re.MULTILINE)
    if not re.fullmatch(r"\d+\.\d+\.\d+", upstream_version) or not upstream_release:
        raise ValueError("Unrecognized upstream version/revision")
    upstream_version += "-" + upstream_release[1]
    build_date = f"{local_date.year % 100}.{local_date.month}.{local_date.day}"
    display_version = f"{build_date}-{build_number} · 上游 {upstream_version}"
    make = replace_once(make, r"^PKG_VERSION\s*:?=.*$", f"PKG_VERSION:={version}")
    make = replace_once(make, r"^PKG_RELEASE\s*:?=.*$", "PKG_RELEASE:=1")
    make = replace_once(make, r"^PKG_PO_VERSION\s*:?=.*$", "PKG_PO_VERSION:=$(PKG_VERSION)")
    com = replace_once(
        com, r"^_M\.passwall2\s*=\s*\{\s*name\s*=\s*\"PassWall2\",\s*get_url\s*=\s*gh_release_url\s*\}",
        '_M.passwall2 = {\n\tname = "PassWall2",\n\tget_url = function(self)\n'
        f'\t\treturn "{url}"\n\tend\n}}',
    )
    # Keep get_version() and update comparisons numeric for existing installations.
    # Only UI-facing fields use the compact label stored inside this exact package.
    display_function = '''function get_display_version()
	local version = get_version()
	local info = jsonc.parse(fs.readfile("/usr/share/passwall2/build-info.json") or "{}")
	if type(info) == "table" and info.version == version and type(info.display_version) == "string" then
		return info.display_version
	end
	return version
end

'''
    api = replace_once(api, r"^local function self_update_languages\(\)",
                       display_function + "local function self_update_languages()")
    api = replace_once(
        api, r"^\t\tlocal_version = local_version, remote_version = remote_version, html_url = release.html_url,$",
        "\t\tlocal_version = get_display_version(), remote_version = release.display_version or remote_version, html_url = release.html_url,",
    )
    view = viewfile.read_text()
    if view.count("api.get_version()") != 1:
        raise ValueError("Upstream version display template changed")
    # Keep metadata plain text; color only the upstream suffix in the local UI.
    view = replace_once(view, r"^local com = self.com$", '''local com = self.com
local display_version = api.get_display_version()
local build_version, upstream_version = display_version:match("^(.-) · (上游 %d+%.%d+%.%d+%-%d+)$")
local version_html = luci.util.pcdata(display_version)
if build_version then
    local month_colors = {
        "#ED174C", "#E000A3", "#803DE8", "#008F68",
        "#548E00", "#008DA8", "#0068ED", "#4140E8",
        "#AA7900", "#E65400", "#BF4126", "#AB22CE"
    }
    local color = month_colors[tonumber(os.date("%m"))] or "#ED174C"
    version_html = luci.util.pcdata(build_version) .. ' · <span style="color: ' .. color .. '">' .. luci.util.pcdata(upstream_version) .. '</span>'
end''')
    view = view.replace("api.get_version()", "version_html")
    metadata = {
        "repository": repository, "version": version, "tag_name": f"{version}-1",
        "package_version": f"{version}-r1", "update_url": url,
        "upstream_version": upstream_version,
        "display_version": display_version, "build_date": build_date, "build_number": build_number,
        "upstream_commit": upstream_commit,
        "run_id": run_id, "run_attempt": attempt, "created_at": created_at,
    }
    # Validate every transformation before touching the feed.
    makefile.write_text(make)
    comfile.write_text(com)
    apifile.write_text(api)
    viewfile.write_text(view)
    infofile = source / "root/usr/share/passwall2/build-info.json"
    infofile.write_text(json.dumps({"version": metadata["tag_name"],
                                   "display_version": display_version}, indent=2) + "\n")
    output.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Prepared PassWall2 {metadata['package_version']} -> {url}")


def apk_info(apk, package):
    data = json.loads(subprocess.check_output(
        [str(apk), "adbdump", "--format", "json", str(package)], text=True))
    return data["info"]


def collect(build, metadata_file, destination):
    meta = json.loads(metadata_file.read_text())
    apk = build / "staging_dir/host/bin/apk"
    names = {
        "luci-app-passwall2": meta["package_version"],
        "luci-i18n-passwall2-zh-cn": meta["version"],
    }
    selected = []
    # Both search roots can contain identical hardlinks/copies. Reject differing copies.
    for name, version in names.items():
        filename = f"{name}-{version}.apk"
        candidates = sorted({p.resolve() for root in (build / "bin/packages", build / "bin/targets")
                             for p in root.rglob(filename)})
        if not candidates:
            raise ValueError(f"Missing built package: {filename}")
        digests = {hashlib.sha256(p.read_bytes()).hexdigest() for p in candidates}
        if len(digests) != 1:
            raise ValueError(f"Conflicting built packages: {filename}")
        package = candidates[0]
        info = apk_info(apk, package)
        if (info.get("name"), info.get("version"), info.get("arch")) != (name, version, "noarch"):
            raise ValueError(f"Unexpected APK metadata: {info}")
        if name == "luci-app-passwall2":
            with tempfile.TemporaryDirectory(prefix="passwall2-verify-") as tmp:
                subprocess.run([str(apk), "extract", "--allow-untrusted", "--no-chown",
                                "--destination", tmp, str(package)], check=True)
                packed = Path(tmp) / "usr/lib/lua/luci/passwall2/com.lua"
                if meta["update_url"] not in packed.read_text():
                    raise ValueError("Built APK does not contain the repository update URL")
                info = json.loads((Path(tmp) / "usr/share/passwall2/build-info.json").read_text())
                if info != {"version": meta["tag_name"], "display_version": meta["display_version"]}:
                    raise ValueError("Built APK contains incorrect display version metadata")
        selected.append((package, next(iter(digests))))
    destination.mkdir(parents=True, exist_ok=True)
    for package, digest in selected:
        shutil.copyfile(package, destination / package.name)
        print(f"Verified {package.name}: sha256:{digest}")
    # Preserve exact checksums and provenance for publication and readback.
    meta["assets"] = [
        {"name": p.name, "size": p.stat().st_size, "digest": f"sha256:{digest}"}
        for p, digest in selected
    ]
    (destination / "passwall2-build.json").write_text(json.dumps(meta, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    patch = subs.add_parser("prepare")
    patch.add_argument("--source", type=Path, required=True)
    patch.add_argument("--repository", required=True)
    patch.add_argument("--created-at", required=True)
    patch.add_argument("--run-id", type=int, required=True)
    patch.add_argument("--attempt", type=int, required=True)
    patch.add_argument("--build-number", type=int, required=True)
    patch.add_argument("--upstream-commit", required=True)
    patch.add_argument("--output", type=Path, required=True)
    gather = subs.add_parser("collect")
    gather.add_argument("--build", type=Path, required=True)
    gather.add_argument("--metadata", type=Path, required=True)
    gather.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.source, args.repository, args.created_at, args.run_id, args.attempt,
                args.upstream_commit, args.output, args.build_number)
    else:
        collect(args.build.resolve(), args.metadata, args.destination)


if __name__ == "__main__":
    main()
