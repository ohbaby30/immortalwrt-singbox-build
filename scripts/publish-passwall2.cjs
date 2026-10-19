// Called by actions/github-script after a successful default x86_64 build.
// APKs live in immutable Releases; the common JSON changes in one Git ref update.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const branch = 'passwall2-update';
const manifestPath = 'passwall2-release-api.json';

function compareVersions(left, right) {
  const parse = (value) => {
    if (!/^\d+\.\d+\.\d+-1$/.test(value)) throw new Error(`Invalid build version: ${value}`);
    return value.split(/[.-]/).map(BigInt);
  };
  const a = parse(left), b = parse(right);
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return a[i] > b[i] ? 1 : -1;
  }
  return 0;
}

async function readPointer(github, repo) {
  let ref;
  try {
    ref = (await github.rest.git.getRef({...repo, ref: `heads/${branch}`})).data;
  } catch (error) {
    if (error.status === 404) return null;
    throw error;
  }
  const file = (await github.rest.repos.getContent({...repo, path: manifestPath, ref: ref.object.sha})).data;
  if (file.type !== 'file' || file.encoding !== 'base64') throw new Error('Invalid manifest file');
  const manifest = JSON.parse(Buffer.from(file.content, 'base64').toString('utf8'));
  compareVersions(manifest.tag_name, manifest.tag_name);
  return {sha: ref.object.sha, manifest};
}

async function advancePointer(github, repo, manifest, core) {
  for (let attempt = 0; attempt < 5; attempt++) {
    const previous = await readPointer(github, repo);
    if (previous) {
      const order = compareVersions(manifest.tag_name, previous.manifest.tag_name);
      if (order < 0) {
        core.info(`Kept newer PassWall2 build ${previous.manifest.tag_name}`);
        return false;
      }
      if (order === 0) {
        if (JSON.stringify(manifest.assets) !== JSON.stringify(previous.manifest.assets)) {
          throw new Error('The same version points to different APKs');
        }
        core.info('PassWall2 manifest is already current');
        return false;
      }
    }
    const tree = (await github.rest.git.createTree({...repo, tree: [
      {path: manifestPath, mode: '100644', type: 'blob', content: JSON.stringify(manifest, null, 2) + '\n'},
    ]})).data;
    const commit = (await github.rest.git.createCommit({...repo,
      message: `Publish PassWall2 ${manifest.tag_name}`,
      tree: tree.sha, parents: previous ? [previous.sha] : [],
    })).data;
    try {
      if (previous) {
        await github.rest.git.updateRef({...repo, ref: `heads/${branch}`, sha: commit.sha, force: false});
      } else {
        await github.rest.git.createRef({...repo, ref: `refs/heads/${branch}`, sha: commit.sha});
      }
    } catch (error) {
      if (error.status === 409 || error.status === 422) continue; // Re-read after another build wins.
      throw error;
    }
    const readback = await readPointer(github, repo);
    if (!readback || compareVersions(readback.manifest.tag_name, manifest.tag_name) < 0) {
      throw new Error('Manifest readback failed');
    }
    if (readback.manifest.tag_name === manifest.tag_name &&
        JSON.stringify(readback.manifest.assets) !== JSON.stringify(manifest.assets)) {
      throw new Error('Manifest asset readback failed');
    }
    core.info(`PassWall2 update pointer verified: ${readback.manifest.tag_name}`);
    return true;
  }
  throw new Error('Could not update manifest after five attempts; previous pointer remains valid');
}

async function publish({github, context, core, directory = 'artifact'}) {
  const repo = {owner: context.repo.owner, repo: context.repo.repo};
  const repository = `${repo.owner}/${repo.repo}`;
  const meta = JSON.parse(fs.readFileSync(path.join(directory, 'passwall2-build.json'), 'utf8'));
  compareVersions(meta.tag_name, meta.tag_name);
  if (meta.repository !== repository || meta.tag_name !== `${meta.version}-1` ||
      meta.package_version !== `${meta.version}-r1` || !Array.isArray(meta.assets) || meta.assets.length !== 2) {
    throw new Error('Invalid build metadata');
  }
  const expected = [
    `luci-app-passwall2-${meta.package_version}.apk`,
    `luci-i18n-passwall2-zh-cn-${meta.version}.apk`,
  ];
  for (const [i, asset] of meta.assets.entries()) {
    if (asset.name !== expected[i]) throw new Error('Unexpected APK filename');
    const data = fs.readFileSync(path.join(directory, asset.name));
    if (data.length !== asset.size || `sha256:${crypto.createHash('sha256').update(data).digest('hex')}` !== asset.digest) {
      throw new Error(`Local APK verification failed: ${asset.name}`);
    }
  }
  const current = await readPointer(github, repo);
  if (current && compareVersions(meta.tag_name, current.manifest.tag_name) < 0) {
    core.info('Skipped publication of an older build');
    return;
  }
  // This tag prefix is deliberately outside the existing firmware cleanup prefixes.
  const tag = `passwall2-${meta.tag_name}`;
  let release;
  try {
    release = (await github.rest.repos.getReleaseByTag({...repo, tag})).data;
  } catch (error) {
    if (error.status !== 404) throw error;
    release = (await github.rest.repos.createRelease({...repo, tag_name: tag,
      target_commitish: context.sha, name: `PassWall2 ${meta.tag_name} (universal APK)`,
      body: `Built from ${repository}, Actions run ${meta.run_id}, attempt ${meta.run_attempt}.\n` +
        `Upstream source: ${meta.upstream_commit}\nUpstream version: ${meta.upstream_version}\n` +
        'Universal LuCI APK and Simplified Chinese translation. Firmware is published separately.',
      draft: true, prerelease: false, make_latest: 'false',
    })).data;
  }
  for (const asset of meta.assets) {
    const existing = release.assets.find((item) => item.name === asset.name);
    if (!existing) {
      if (!release.draft) throw new Error('Refusing to change an already published Release');
      await github.rest.repos.uploadReleaseAsset({url: release.upload_url, name: asset.name,
        data: fs.readFileSync(path.join(directory, asset.name)),
        headers: {'content-type': 'application/vnd.android.package-archive'},
      });
    }
  }
  release = (await github.rest.repos.getRelease({...repo, release_id: release.id})).data;
  // Check content before publishing. Draft asset URLs can use a temporary tag;
  // verify their final public URLs only after the Release is published.
  for (const expectedAsset of meta.assets) {
    const asset = release.assets.find((item) => item.name === expectedAsset.name);
    if (!asset || asset.state !== 'uploaded' || asset.size !== expectedAsset.size ||
        asset.digest !== expectedAsset.digest) {
      throw new Error(`Remote APK verification failed: ${expectedAsset.name}`);
    }
  }
  if (release.draft) {
    release = (await github.rest.repos.updateRelease({...repo, release_id: release.id,
      draft: false, make_latest: 'false',
    })).data;
  }
  release = (await github.rest.repos.getRelease({...repo, release_id: release.id})).data;
  if (release.draft || release.prerelease) throw new Error('Release is not public and stable');
  const assets = meta.assets.map((expectedAsset) => {
    const asset = release.assets.find((item) => item.name === expectedAsset.name);
    const url = `https://github.com/${repository}/releases/download/${tag}/${expectedAsset.name}`;
    if (!asset || asset.state !== 'uploaded' || asset.size !== expectedAsset.size ||
        asset.digest !== expectedAsset.digest || asset.browser_download_url !== url) {
      throw new Error(`Published APK verification failed: ${expectedAsset.name}`);
    }
    return {name: asset.name, size: asset.size, digest: asset.digest, browser_download_url: url};
  });
  const manifest = {tag_name: meta.tag_name, html_url: release.html_url, assets,
    build: {repository, run_id: meta.run_id, run_attempt: meta.run_attempt,
      upstream_commit: meta.upstream_commit, upstream_version: meta.upstream_version}};
  await advancePointer(github, repo, manifest, core);
  core.info(`Update source: https://raw.githubusercontent.com/${repository}/${branch}/${manifestPath}`);
}

module.exports = {publish, compareVersions, advancePointer};
