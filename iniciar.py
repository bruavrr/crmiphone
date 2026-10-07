"""Inicia a demonstração local no Windows, macOS ou Linux (Python 3.12+)."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import venv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true', help='Prepara sem iniciar os servidores.')
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error('Instale Python 3.12 ou superior.')
    if os.getenv('DATABASE_URL') or os.getenv('DEBUG', 'true').lower() != 'true':
        parser.error('Este iniciador é exclusivo para demonstração local, sem DATABASE_URL e com DEBUG=true.')
    root = Path(__file__).resolve().parent
    os.chdir(root)
    environment = os.environ.copy()
    environment.setdefault('SQLITE_PATH', str(root / 'demo.sqlite3'))
    environment['DEBUG'] = 'true'
    python = root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        venv.create(root / '.venv', with_pip=True)

    def run(*command):
        subprocess.run([str(python), *command], env=environment, check=True)

    run('-m', 'pip', 'install', '-r', 'requirements.txt')
    run('manage.py', 'migrate', '--noinput')
    run('manage.py', 'init_crm')
    run('manage.py', 'seed_demo', '--password', 'Demo@Premium2026!')
    run('manage.py', 'collectstatic', '--noinput')
    run('manage.py', 'check')
    if args.prepare_only:
        return
    print('Abra http://127.0.0.1:8000 no seu navegador. Login: admin / Demo@Premium2026!', flush=True)
    worker = subprocess.Popen([str(python), 'manage.py', 'automation_worker'], env=environment)
    try:
        run('manage.py', 'runserver', '127.0.0.1:8000', '--noreload')
    except KeyboardInterrupt:
        pass
    finally:
        if worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait()


if __name__ == '__main__':
    main()
