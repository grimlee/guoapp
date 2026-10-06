import argparse
import hashlib
import re
import shutil
import tarfile
import zipfile
from pathlib import Path

from app_build import BuildVariant, add_variant_argument

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--platform', choices=['android', 'windows', 'linux'], required=True)
parser.add_argument('--abi', action='append', choices=['arm64-v8a', 'armeabi-v7a', 'x86_64'])
add_variant_argument(parser)
options = parser.parse_args()
variant = BuildVariant(options.all_sources)
match = re.search(r'^version:\s*([\w.+-]+)\s*$', (root / 'pubspec.yaml').read_text(encoding='utf-8'), re.MULTILINE)
if not match:
    raise SystemExit('pubspec.yaml 缺少合法版本号。')
version = match.group(1)
output = root / 'dist' / options.platform
output.mkdir(parents=True, exist_ok=True)
artifacts = []

if options.platform == 'android':
    for abi in options.abi or ['arm64-v8a', 'armeabi-v7a', 'x86_64']:
        source = root / 'build' / 'app' / 'outputs' / 'flutter-apk' / f'app-{abi}-release.apk'
        if not source.is_file():
            raise SystemExit('缺少 APK：' + str(source))
        with zipfile.ZipFile(source) as archive:
            names = set(archive.namelist())
            required = [f'lib/{abi}/{library}' for library in
                        ['libduanju_core.so', 'libflutter.so', 'libapp.so', 'libmpv.so', 'libffmpegkit.so']]
            missing = set(required) - names
            if missing:
                raise SystemExit('APK 缺少原生库：' + ', '.join(sorted(missing)))
        target = output / f'{variant.slug}-{version}-{abi}.apk'
        shutil.copy2(source, target)
        artifacts.append(target)
elif options.platform == 'windows':
    bundle = root / 'build' / 'windows' / 'x64' / 'runner' / 'Release'
    required = ['zhenguojian.exe', 'duanju_core.dll', 'flutter_windows.dll', 'libffmpegkit.dll',
                'libmpv-2.dll', 'msvcp140.dll', 'vcruntime140.dll',
                'data/icudtl.dat', 'data/app.so']
    missing = [name for name in required if not (bundle / name).is_file()]
    if missing:
        raise SystemExit('Windows 安装包缺少文件：' + ', '.join(missing))
    target = output / f'{variant.slug}-{version}-windows-x64.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(bundle.rglob('*')):
            if source.is_file():
                relative = source.relative_to(bundle).as_posix()
                if relative == 'zhenguojian.exe':
                    relative = variant.slug + '.exe'
                archive.write(source, relative)
    artifacts.append(target)
else:
    bundles = sorted((root / 'build' / 'linux').glob('*/release/bundle'))
    if len(bundles) != 1:
        raise SystemExit('无法定位唯一的 Linux Flutter bundle。')
    bundle = bundles[0]
    required = ['duanju_app', 'data/icudtl.dat', 'lib/libapp.so',
                'lib/libflutter_linux_gtk.so', 'lib/libduanju_core.so']
    missing = [name for name in required if not (bundle / name).is_file()]
    if missing:
        raise SystemExit('Linux 安装包缺少文件：' + ', '.join(missing))
    architecture = bundle.parents[1].name
    architecture = {'x64': 'x86_64', 'arm64': 'aarch64'}.get(architecture, architecture)
    target = output / f'{variant.slug}-{version}-linux-{architecture}.tar.gz'
    with tarfile.open(target, 'w:gz') as archive:
        for source in sorted(bundle.rglob('*')):
            if not source.is_file():
                continue
            relative = source.relative_to(bundle)
            if relative.as_posix() == 'duanju_app':
                relative = Path(variant.slug)
            archive.add(
                source,
                arcname=(Path(variant.slug) / relative).as_posix(),
                recursive=False,
            )
    artifacts.append(target)

checksums = []
for artifact in sorted(output.glob(f'*-{version}-*')):
    digest = hashlib.sha256()
    with artifact.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    checksums.append(f'{digest.hexdigest()}  {artifact.name}')
    print(artifact)
(output / 'SHA256SUMS.txt').write_text('\n'.join(checksums) + '\n', encoding='ascii')
