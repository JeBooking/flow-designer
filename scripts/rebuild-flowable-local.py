"""从已有可执行包的依赖重编译本项目 Java 类，不下载或替换依赖版本。"""
import argparse
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def rebuild(source, output):
    source, output = source.resolve(), output.resolve()
    with tempfile.TemporaryDirectory(prefix='diagnosis-java-build-') as directory:
        directory = Path(directory)
        libraries, classes = directory / 'lib', directory / 'classes'
        libraries.mkdir()
        classes.mkdir()
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                if name.startswith('BOOT-INF/lib/') and name.endswith('.jar'):
                    (libraries / Path(name).name).write_bytes(archive.read(name))
        sources = sorted((ROOT / 'flowable-runtime/src/main/java').rglob('*.java'))
        subprocess.run(['javac', '--release', '17', '-parameters', '-encoding', 'UTF-8', '-cp', str(libraries / '*'),
                        '-d', str(classes), *map(str, sources)], check=True)
        packaged = directory / 'diagnostic-flowable.jar'
        resources = {
            'BOOT-INF/classes/' + file.relative_to(ROOT / 'flowable-runtime/src/main/resources').as_posix(): file
            for file in (ROOT / 'flowable-runtime/src/main/resources').rglob('*') if file.is_file()
        }
        with zipfile.ZipFile(source) as archive, zipfile.ZipFile(packaged, 'w') as rebuilt:
            for info in archive.infolist():
                if info.filename not in resources and not (info.filename.startswith('BOOT-INF/classes/local/diagnosis/') and info.filename.endswith('.class')):
                    rebuilt.writestr(info, archive.read(info.filename))
            if 'BOOT-INF/classes/local/diagnosis/' not in archive.namelist():
                rebuilt.writestr('BOOT-INF/classes/local/diagnosis/', b'')
            for file in classes.rglob('*.class'):
                rebuilt.write(file, 'BOOT-INF/classes/' + file.relative_to(classes).as_posix())
            for name, file in resources.items():
                rebuilt.write(file, name)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(packaged.read_bytes())
    print('Compiled Java sources and rebuilt local executable:', output)


if __name__ == '__main__':
    default = ROOT / 'flowable-runtime/target/diagnostic-flowable-1.0.0.jar'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-jar', type=Path, default=default)
    parser.add_argument('--output', type=Path, default=default)
    args = parser.parse_args()
    rebuild(args.source_jar, args.output)
