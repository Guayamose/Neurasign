import { spawnSync } from 'node:child_process';
import { copyFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('..', import.meta.url));
function run(command, args) {
  const result = spawnSync(command, args, { cwd: root, env: { ...process.env, NODE_ENV: 'production' }, stdio: 'inherit' });
  if (result.status !== 0) process.exit(result.status ?? 1);
}
run('npx', ['expo', 'prebuild', '--platform', 'android', '--no-install']);
run('./android/gradlew', ['-p', 'android', 'assembleRelease', '-PreactNativeArchitectures=arm64-v8a,x86_64', '--max-workers=4', '--console=plain']);
mkdirSync(new URL('../artifacts/', import.meta.url), { recursive: true });
const name = process.env.LOCAL_GATEWAY_HTTP === '1' ? 'neurasign-link-local.apk' : 'neurasign-link.apk';
copyFileSync(new URL('../android/app/build/outputs/apk/release/app-release.apk', import.meta.url), new URL(`../artifacts/${name}`, import.meta.url));
console.log(`APK: artifacts/${name} (development signing; configure release signing before store distribution)`);
