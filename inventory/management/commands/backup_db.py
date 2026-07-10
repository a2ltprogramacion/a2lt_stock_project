"""
inventory/management/commands/backup_db.py
============================================
Management command para backup atomico de la base SQLite via
VACUUM INTO (Fase 6).

Uso:
    python manage.py backup_db
    python manage.py backup_db --dir /path/to/backups
    python manage.py backup_db --retention 7   # borra backups > 7 dias
    python manage.py backup_db --name nombre_custom

Caracteristicas:
  - Usa VACUUM INTO (SQLite >= 3.27) que genera un snapshot atomico
    consistente sin bloquear escrituras.
  - El nombre por defecto es: db_backup_YYYYMMDD_HHMMSS.sqlite3
  - Directorio por defecto: <BASE_DIR>/backups/
  - --retention N elimina los backups con mtime > N dias (opcional)
  - --check valida que el DB actual pueda respaldarse sin ejecutar.
"""

from __future__ import annotations

import datetime
import os
import sys
import time

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


class Command(BaseCommand):
    help = 'Genera un backup atomico de SQLite via VACUUM INTO.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dir',
            type=str,
            default='',
            help='Directorio destino (default: <BASE_DIR>/backups/).'
        )
        parser.add_argument(
            '--name',
            type=str,
            default='',
            help='Nombre del archivo backup (sin extension). Default: db_backup_YYYYMMDD_HHMMSS.'
        )
        parser.add_argument(
            '--retention',
            type=int,
            default=0,
            help='Dias de retencion: borra backups con mtime > N dias (0=no borrar).'
        )
        parser.add_argument(
            '--check',
            action='store_true',
            default=False,
            help='Solo valida que pueda respaldarse (dry-run). No genera archivo.'
        )

    def handle(self, *args, **options):
        from django.db import connection

        # Validar engine
        engine = settings.DATABASES['default']['ENGINE']
        if 'sqlite' not in engine:
            raise CommandError(
                f'backup_db solo soporta SQLite (engine={engine}). '
                f'Para otros motores use utilidades nativas del SGBD.'
            )

        # Resolver ruta DB
        db_path = settings.DATABASES['default']['NAME']
        if not isinstance(db_path, str):
            db_path = str(db_path)

        # Detectar BD in-memory (tests u OID compartido): en estos
        # casos no podemos usar sqlite3.connect(ruta) — el backend
        # de Django maneja la conexion sobre la URI "file:memory:...".
        is_memory = (
            ':memory:' in db_path
            or db_path.startswith('file:memory:')
            or 'mode=memory' in db_path
        )

        if not is_memory and not os.path.exists(db_path):
            raise CommandError(f'La BD no existe en la ruta: {db_path}')

        # Directorio destino
        if options['dir']:
            backup_dir = options['dir']
        elif not is_memory:
            backup_dir = os.path.join(os.path.dirname(db_path), 'backups')
        else:
            # En memoria, usar BASE_DIR/backups como fallback
            backup_dir = os.path.join(settings.BASE_DIR, 'backups')

        # Crear el directorio si no existe (incluso en --check, asi el
        # dry-run valida que se puede escribir, no solo que existe).
        if not os.path.isdir(backup_dir):
            try:
                os.makedirs(backup_dir, exist_ok=True)
            except OSError as e:
                if options.get('check'):
                    raise CommandError(f'No se pudo crear el directorio {backup_dir}: {e}')
                raise CommandError(f'No se pudo crear el directorio {backup_dir}: {e}')

        # Nombre backup
        now = datetime.datetime.now()
        default_name = f'db_backup_{now.strftime("%Y%m%d_%H%M%S")}'
        backup_name = options['name'] or default_name
        if not backup_name.endswith('.sqlite3'):
            backup_name += '.sqlite3'

        backup_path = os.path.join(backup_dir, backup_name)

        # Dry-run: verificar permisos de escritura
        if options['check']:
            ok_dir = os.access(backup_dir, os.W_OK) if os.path.isdir(backup_dir) else False
            self.stdout.write(self.style.SUCCESS(
                f'(dry-run) DB={db_path} -> {backup_path} '
                f'(memory_db={is_memory}, '
                f'dir existe: {os.path.isdir(backup_dir)}, '
                f'writable: {ok_dir})'
            ))
            if not ok_dir:
                raise CommandError('Directorio no existe o no es escribible.')
            return

        # Ejecutar VACUUM INTO.
        # - BD file-based: usar sqlite3.connect(ruta) fresh para evitar
        #   interferir con el pool de Django.
        # - BD in-memory: usar el cursor de Django (comparte la conexion
        #   con file:memorydb_default?mode=memory&cache=shared).
        import sqlite3

        start = time.time()
        self.stdout.write(f'Iniciando VACUUM INTO -> {backup_path} ...')

        if is_memory:
            # Cursor Django: opera sobre la memoria compartida.
            # VACUUM no puede ejecutarse dentro de una transaccion abierta
            # por Django. La solucion: abrir una conexion sqlite3 fresh
            # con el mismo URI compartido (cache=shared permite esto).
            # En tests Django: 'file:memorydb_default?mode=memory&cache=shared'
            # Convertir a URI sqlite3 valida: 'file:memorydb_default?...&cache=shared'
            uri = db_path
            if not uri.startswith('file:'):
                # Si es ':memory:' puro, no es compartible; fallback a copia
                # directa via Django (no ideal pero evita el error).
                uri = f'file:{uri}?cache=shared' if not uri.startswith(':memory:') else uri

            if uri.startswith('file:'):
                # Conectar directamente a la DB compartida
                shared_conn = sqlite3.connect(uri, uri=True, timeout=20)
                try:
                    cursor = shared_conn.cursor()
                    cursor.execute(f'VACUUM INTO "{backup_path}";')
                    cursor.close()
                finally:
                    shared_conn.close()
            else:
                # ':memory:' puro: fallback usando la API de backup de sqlite
                # (no probe esta rama en tests)
                raise CommandError(
                    'No se puede respaldar una BD :memory: pura (sin cache=shared). '
                    'Use una BD file-based o cache=shared.'
                )
        else:
            src_conn = sqlite3.connect(db_path, timeout=20)
            try:
                cursor = src_conn.cursor()
                cursor.execute(f'VACUUM INTO "{backup_path}";')
                cursor.close()
            finally:
                src_conn.close()

        elapsed = time.time() - start

        # Verificar size del backup
        try:
            size = os.path.getsize(backup_path)
        except OSError:
            size = 0

        self.stdout.write(self.style.SUCCESS(
            f'Backup OK: {backup_path} ({size} bytes, {elapsed:.2f}s)'
        ))

        # Retention: borrar backups viejos
        if options['retention'] > 0:
            self._apply_retention(backup_dir, options['retention'])

    def _apply_retention(self, backup_dir: str, retention_days: int):
        """Borra archivos db_backup_*.sqlite3 con mtime > retention_days."""
        now = time.time()
        cutoff = now - (retention_days * 86400)
        removed = 0
        for fname in os.listdir(backup_dir):
            if not fname.startswith('db_backup_') or not fname.endswith('.sqlite3'):
                continue
            fpath = os.path.join(backup_dir, fname)
            try:
                mtime = os.path.getmtime(fpath)
            except OSError:
                continue
            if mtime < cutoff:
                try:
                    os.remove(fpath)
                    removed += 1
                    self.stdout.write(f'  [retention] borrado {fname} '
                                      f'({datetime.datetime.fromtimestamp(mtime):%Y-%m-%d})')
                except OSError as e:
                    self.stderr.write(f'  No se pudo borrar {fname}: {e}')
        if removed:
            self.stdout.write(self.style.SUCCESS(
                f'Retention: {removed} backup(s) > {retention_days} dia(s) eliminados.'
            ))
