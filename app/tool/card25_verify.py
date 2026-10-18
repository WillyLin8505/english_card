"""Reproduce card #25 checks, recording UTF-8 output in app/."""
from pathlib import Path
import shutil
import subprocess

app = Path(__file__).resolve().parents[1]
flutter = shutil.which('flutter')
if not flutter:
    raise SystemExit('flutter is not on PATH')
failed = False
for command, output in [('test', 'card25-tests.txt'), ('analyze', 'card25-analyze.txt')]:
    args = [flutter, command]
    if command == 'test':
        args += ['--reporter', 'expanded']
    result = subprocess.run(args, cwd=app, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    text = result.stdout.decode('utf-8', errors='replace')
    (app / output).write_text(text, encoding='utf-8')
    print(f'flutter {command}: exit {result.returncode}; {output}', flush=True)
    print('\n'.join(text.splitlines()[-5:]), flush=True)
    failed |= result.returncode != 0
raise SystemExit(1 if failed else 0)
