import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from build_mirrors import china_mirror_environment, mirrored_pub_lockfile
from app_build import BuildVariant, add_variant_argument

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--cn-mirrors', action='store_true', help='使用 Flutter 中国镜像')
add_variant_argument(parser)
options = parser.parse_args()
variant = BuildVariant(options.all_sources)
environment = os.environ.copy()
environment.setdefault('GOPROXY', 'https://goproxy.cn,direct')
environment.setdefault('GOSUMDB', 'off')
flutter = shutil.which('flutter')
if not flutter:
    raise SystemExit('请先将 Flutter SDK 的 bin 目录加入 PATH。')

linux = root / 'linux'
generated_linux = not linux.exists()

try:
    with china_mirror_environment(environment, options.cn_mirrors, gradle=False) as env:
        with mirrored_pub_lockfile(root, env):
            if generated_linux:
                with tempfile.TemporaryDirectory(prefix='duanju-linux-host-') as temporary:
                    host_root = Path(temporary) / 'duanju_app'
                    subprocess.run([
                        flutter, 'create',
                        '--platforms=linux',
                        '--project-name', 'duanju_app',
                        '--org', 'com.duanju',
                        '--no-pub',
                        str(host_root),
                    ], cwd=root, env=env, check=True)
                    shutil.copytree(host_root / 'linux', linux)

            runner = linux / 'runner' / 'my_application.cc'
            if runner.is_file():
                source = runner.read_text(encoding='utf-8')
                source = source.replace('"duanju_app"', '"' + variant.slug + '"')
                runner.write_text(source, encoding='utf-8')

            subprocess.run([flutter, 'pub', 'get', '--enforce-lockfile'],
                           cwd=root, env=env, check=True)
            subprocess.run([
                sys.executable,
                str(root / 'scripts' / 'build_native.py'),
                '--platform', 'linux',
                *variant.arguments,
            ], cwd=root, env=env, check=True)
            subprocess.run([
                flutter, 'build', 'linux', '--release', '--no-pub',
                *variant.flutter_arguments,
            ], cwd=root, env=env, check=True)

            bundles = sorted((root / 'build' / 'linux').glob('*/release/bundle'))
            if len(bundles) != 1:
                raise SystemExit('无法定位唯一的 Linux Flutter bundle。')
            bundle = bundles[0]
            library = root / 'native' / 'build' / 'linux' / 'libduanju_core.so'
            if not library.is_file():
                raise SystemExit('缺少 Linux 原生核心：' + str(library))
            destination = bundle / 'lib' / 'libduanju_core.so'
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(library, destination)

            subprocess.run([
                sys.executable,
                str(root / 'scripts' / 'package_release.py'),
                '--platform', 'linux',
                *variant.arguments,
            ], cwd=root, env=env, check=True)
finally:
    if generated_linux:
        shutil.rmtree(linux, ignore_errors=True)
