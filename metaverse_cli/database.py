import sqlite3
import os
import json
import shutil
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from contextlib import contextmanager


class AssetDatabase:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(os.getcwd(), '.metaverse_assets.db')
        self.db_path = db_path
        self._init_database()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_database(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS avatars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    gender TEXT,
                    style TEXT,
                    preview_image TEXT,
                    model_path TEXT,
                    copyright_source TEXT,
                    copyright_holder TEXT,
                    license_type TEXT,
                    version TEXT DEFAULT '1.0',
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS wardrobe_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    gender TEXT,
                    style TEXT,
                    model_path TEXT,
                    texture_paths TEXT,
                    preview_image TEXT,
                    copyright_source TEXT,
                    version TEXT DEFAULT '1.0',
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS outfits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    style TEXT,
                    gender TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS outfit_items (
                    outfit_id INTEGER,
                    wardrobe_item_id INTEGER,
                    FOREIGN KEY (outfit_id) REFERENCES outfits(id) ON DELETE CASCADE,
                    FOREIGN KEY (wardrobe_item_id) REFERENCES wardrobe_items(id) ON DELETE CASCADE,
                    PRIMARY KEY (outfit_id, wardrobe_item_id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS avatar_outfits (
                    avatar_id INTEGER,
                    outfit_id INTEGER,
                    FOREIGN KEY (avatar_id) REFERENCES avatars(id) ON DELETE CASCADE,
                    FOREIGN KEY (outfit_id) REFERENCES outfits(id) ON DELETE CASCADE,
                    PRIMARY KEY (avatar_id, outfit_id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS motions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category TEXT,
                    file_path TEXT NOT NULL,
                    duration REAL,
                    frame_count INTEGER,
                    fps INTEGER,
                    target_rig TEXT,
                    copyright_source TEXT,
                    version TEXT DEFAULT '1.0',
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    validated BOOLEAN DEFAULT 0
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scenes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    environment TEXT,
                    lighting TEXT,
                    model_path TEXT,
                    preview_image TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    category TEXT
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS avatar_tags (
                    avatar_id INTEGER,
                    tag_id INTEGER,
                    FOREIGN KEY (avatar_id) REFERENCES avatars(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
                    PRIMARY KEY (avatar_id, tag_id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_type TEXT NOT NULL,
                    asset_id INTEGER NOT NULL,
                    issue_type TEXT NOT NULL,
                    description TEXT,
                    severity TEXT DEFAULT 'medium',
                    fixed BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fixed_at TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS operation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation TEXT NOT NULL,
                    asset_type TEXT,
                    details TEXT,
                    undo_data TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS version_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_type TEXT NOT NULL,
                    asset_id INTEGER NOT NULL,
                    version TEXT NOT NULL,
                    changes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_name TEXT NOT NULL,
                    project_name TEXT,
                    delivery_date TIMESTAMP,
                    manifest TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS delivery_items (
                    delivery_id INTEGER,
                    asset_type TEXT,
                    asset_id INTEGER,
                    FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE,
                    PRIMARY KEY (delivery_id, asset_type, asset_id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS thumbnails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_type TEXT NOT NULL,
                    asset_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    size TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(asset_type, asset_id, size)
                )
            ''')

            conn.commit()

    def log_operation(self, operation: str, asset_type: str = None, details: Dict = None,
                      undo_data: Dict = None, conn=None):
        if conn is not None:
            conn.execute(
                'INSERT INTO operation_log (operation, asset_type, details, undo_data) VALUES (?, ?, ?, ?)',
                (operation, asset_type, json.dumps(details) if details else None,
                 json.dumps(undo_data) if undo_data else None)
            )
        else:
            with self._get_connection() as conn2:
                conn2.execute(
                    'INSERT INTO operation_log (operation, asset_type, details, undo_data) VALUES (?, ?, ?, ?)',
                    (operation, asset_type, json.dumps(details) if details else None,
                     json.dumps(undo_data) if undo_data else None)
                )

    def get_last_operation(self) -> Optional[Dict]:
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM operation_log ORDER BY id DESC LIMIT 1'
            ).fetchone()
            if row:
                result = dict(row)
                for field in ['details', 'undo_data']:
                    if result[field]:
                        result[field] = json.loads(result[field])
                return result
        return None

    def add_avatar(self, name: str, gender: str = None, style: str = None,
                   model_path: str = None, preview_image: str = None) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                '''INSERT INTO avatars (name, gender, style, model_path, preview_image)
                   VALUES (?, ?, ?, ?, ?)''',
                (name, gender, style, model_path, preview_image)
            )
            avatar_id = cursor.lastrowid
            self._log_version(conn, 'avatar', avatar_id, '1.0', 'Initial creation')
            self.log_operation('create_avatar', 'avatar', {'name': name, 'id': avatar_id}, conn=conn)
            return avatar_id

    def update_avatar(self, avatar_id: int, **kwargs):
        with self._get_connection() as conn:
            old_data = conn.execute(
                'SELECT * FROM avatars WHERE id = ?', (avatar_id,)
            ).fetchone()
            if not old_data:
                raise ValueError(f'Avatar {avatar_id} not found')

            old_dict = dict(old_data)
            set_clause = ', '.join([f'{k} = ?' for k in kwargs.keys()])
            values = list(kwargs.values()) + [avatar_id]
            conn.execute(f'UPDATE avatars SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?', values)

            next_version = self._get_next_version(conn, 'avatar', avatar_id)
            changes_desc = ', '.join(kwargs.keys())
            self._log_version(conn, 'avatar', avatar_id, next_version, f'Updated: {changes_desc}')

            self.log_operation('update_avatar', 'avatar',
                               {'id': avatar_id, 'changes': kwargs},
                               {'id': avatar_id, 'old_values': old_dict},
                               conn=conn)

    def get_avatar(self, avatar_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            row = conn.execute('SELECT * FROM avatars WHERE id = ?', (avatar_id,)).fetchone()
            return dict(row) if row else None

    def get_avatar_by_name(self, name: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            row = conn.execute('SELECT * FROM avatars WHERE name = ?', (name,)).fetchone()
            return dict(row) if row else None

    def list_avatars(self, gender: str = None, style: str = None, status: str = None) -> List[Dict]:
        query = 'SELECT * FROM avatars WHERE 1=1'
        params = []
        if gender:
            query += ' AND gender = ?'
            params.append(gender)
        if style:
            query += ' AND style = ?'
            params.append(style)
        if status:
            query += ' AND status = ?'
            params.append(status)
        query += ' ORDER BY name'

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def rename_avatar(self, avatar_id: int, new_name: str) -> bool:
        with self._get_connection() as conn:
            old = conn.execute('SELECT name FROM avatars WHERE id = ?', (avatar_id,)).fetchone()
            if not old:
                return False
            conn.execute('UPDATE avatars SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                        (new_name, avatar_id))
            next_version = self._get_next_version(conn, 'avatar', avatar_id)
            self._log_version(conn, 'avatar', avatar_id, next_version, f'Renamed: {old["name"]} -> {new_name}')
            self.log_operation('rename_avatar', 'avatar',
                               {'id': avatar_id, 'new_name': new_name},
                               {'id': avatar_id, 'old_name': old['name']},
                               conn=conn)
            return True

    def add_tag(self, name: str, category: str = None) -> int:
        with self._get_connection() as conn:
            existing = conn.execute('SELECT id FROM tags WHERE name = ?', (name,)).fetchone()
            if existing:
                return existing['id']
            cursor = conn.execute(
                'INSERT INTO tags (name, category) VALUES (?, ?)',
                (name, category)
            )
            return cursor.lastrowid

    def tag_avatar(self, avatar_id: int, tag_name: str, tag_category: str = None):
        tag_id = self.add_tag(tag_name, tag_category)
        with self._get_connection() as conn:
            conn.execute(
                'INSERT OR IGNORE INTO avatar_tags (avatar_id, tag_id) VALUES (?, ?)',
                (avatar_id, tag_id)
            )
            self.log_operation('tag_avatar', 'avatar',
                               {'avatar_id': avatar_id, 'tag': tag_name},
                               conn=conn)

    def get_avatar_tags(self, avatar_id: int) -> List[Dict]:
        with self._get_connection() as conn:
            rows = conn.execute(
                '''SELECT t.* FROM tags t
                   JOIN avatar_tags at ON t.id = at.tag_id
                   WHERE at.avatar_id = ?''',
                (avatar_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def add_wardrobe_item(self, name: str, category: str, gender: str = None,
                          style: str = None, model_path: str = None,
                          texture_paths: List[str] = None, preview_image: str = None) -> int:
        textures_json = json.dumps(texture_paths) if texture_paths else None
        with self._get_connection() as conn:
            cursor = conn.execute(
                '''INSERT INTO wardrobe_items (name, category, gender, style, model_path, texture_paths, preview_image)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (name, category, gender, style, model_path, textures_json, preview_image)
            )
            item_id = cursor.lastrowid
            self.log_operation('create_wardrobe_item', 'wardrobe',
                               {'name': name, 'id': item_id, 'category': category},
                               conn=conn)
            return item_id

    def get_wardrobe_item(self, item_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            row = conn.execute('SELECT * FROM wardrobe_items WHERE id = ?', (item_id,)).fetchone()
            if row:
                result = dict(row)
                if result['texture_paths']:
                    result['texture_paths'] = json.loads(result['texture_paths'])
                return result
        return None

    def list_wardrobe_items(self, category: str = None, gender: str = None, style: str = None) -> List[Dict]:
        query = 'SELECT * FROM wardrobe_items WHERE 1=1'
        params = []
        if category:
            query += ' AND category = ?'
            params.append(category)
        if gender:
            query += ' AND gender = ?'
            params.append(gender)
        if style:
            query += ' AND style = ?'
            params.append(style)
        query += ' ORDER BY category, name'

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                r = dict(row)
                if r['texture_paths']:
                    r['texture_paths'] = json.loads(r['texture_paths'])
                results.append(r)
            return results

    def create_outfit(self, name: str, description: str = None, style: str = None,
                      gender: str = None, item_ids: List[int] = None) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                'INSERT INTO outfits (name, description, style, gender) VALUES (?, ?, ?, ?)',
                (name, description, style, gender)
            )
            outfit_id = cursor.lastrowid

            if item_ids:
                for item_id in item_ids:
                    conn.execute(
                        'INSERT OR IGNORE INTO outfit_items (outfit_id, wardrobe_item_id) VALUES (?, ?)',
                        (outfit_id, item_id)
                    )

            self.log_operation('create_outfit', 'wardrobe',
                               {'name': name, 'id': outfit_id, 'item_count': len(item_ids or [])},
                               conn=conn)
            return outfit_id

    def bind_outfit_to_avatar(self, avatar_id: int, outfit_id: int):
        with self._get_connection() as conn:
            conn.execute(
                'INSERT OR IGNORE INTO avatar_outfits (avatar_id, outfit_id) VALUES (?, ?)',
                (avatar_id, outfit_id)
            )
            self.log_operation('bind_outfit', 'avatar',
                               {'avatar_id': avatar_id, 'outfit_id': outfit_id},
                               conn=conn)

    def get_avatar_outfits(self, avatar_id: int) -> List[Dict]:
        with self._get_connection() as conn:
            rows = conn.execute(
                '''SELECT o.* FROM outfits o
                   JOIN avatar_outfits ao ON o.id = ao.outfit_id
                   WHERE ao.avatar_id = ?''',
                (avatar_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_outfit_items(self, outfit_id: int) -> List[Dict]:
        with self._get_connection() as conn:
            rows = conn.execute(
                '''SELECT wi.* FROM wardrobe_items wi
                   JOIN outfit_items oi ON wi.id = oi.wardrobe_item_id
                   WHERE oi.outfit_id = ?''',
                (outfit_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def add_motion(self, name: str, file_path: str, category: str = None,
                   duration: float = None, frame_count: int = None, fps: int = None,
                   target_rig: str = None) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                '''INSERT INTO motions (name, file_path, category, duration, frame_count, fps, target_rig)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (name, file_path, category, duration, frame_count, fps, target_rig)
            )
            motion_id = cursor.lastrowid
            self._log_version(conn, 'motion', motion_id, '1.0', 'Initial creation')
            self.log_operation('create_motion', 'motion',
                               {'name': name, 'id': motion_id, 'file_path': file_path},
                               conn=conn)
            return motion_id

    def get_motion(self, motion_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            row = conn.execute('SELECT * FROM motions WHERE id = ?', (motion_id,)).fetchone()
            return dict(row) if row else None

    def list_motions(self, category: str = None, validated: bool = None) -> List[Dict]:
        query = 'SELECT * FROM motions WHERE 1=1'
        params = []
        if category:
            query += ' AND category = ?'
            params.append(category)
        if validated is not None:
            query += ' AND validated = ?'
            params.append(1 if validated else 0)
        query += ' ORDER BY name'

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def validate_motion(self, motion_id: int, is_valid: bool, notes: str = None):
        with self._get_connection() as conn:
            conn.execute(
                'UPDATE motions SET validated = ? WHERE id = ?',
                (1 if is_valid else 0, motion_id)
            )
            next_version = self._get_next_version(conn, 'motion', motion_id)
            status = 'passed' if is_valid else 'failed'
            self._log_version(conn, 'motion', motion_id, next_version, f'Validation {status}')
            self.log_operation('validate_motion', 'motion',
                               {'motion_id': motion_id, 'valid': is_valid, 'notes': notes},
                               conn=conn)

    def add_scene(self, name: str, description: str = None, environment: str = None,
                  lighting: str = None, model_path: str = None, preview_image: str = None) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                '''INSERT INTO scenes (name, description, environment, lighting, model_path, preview_image)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (name, description, environment, lighting, model_path, preview_image)
            )
            scene_id = cursor.lastrowid
            self._log_version(conn, 'scene', scene_id, '1.0', 'Initial creation')
            self.log_operation('create_scene', 'scene',
                               {'name': name, 'id': scene_id},
                               conn=conn)
            return scene_id

    def update_scene(self, scene_id: int, **kwargs):
        with self._get_connection() as conn:
            old_data = conn.execute(
                'SELECT * FROM scenes WHERE id = ?', (scene_id,)
            ).fetchone()
            if not old_data:
                raise ValueError(f'Scene {scene_id} not found')

            old_dict = dict(old_data)
            set_clause = ', '.join([f'{k} = ?' for k in kwargs.keys()])
            values = list(kwargs.values()) + [scene_id]
            conn.execute(f'UPDATE scenes SET {set_clause} WHERE id = ?', values)

            next_version = self._get_next_version(conn, 'scene', scene_id)
            changes_desc = ', '.join(kwargs.keys())
            self._log_version(conn, 'scene', scene_id, next_version, f'Updated: {changes_desc}')

            self.log_operation('update_scene', 'scene',
                               {'id': scene_id, 'changes': kwargs},
                               {'id': scene_id, 'old_values': old_dict},
                               conn=conn)

    def get_scene(self, scene_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            row = conn.execute('SELECT * FROM scenes WHERE id = ?', (scene_id,)).fetchone()
            return dict(row) if row else None

    def list_scenes(self) -> List[Dict]:
        with self._get_connection() as conn:
            rows = conn.execute('SELECT * FROM scenes ORDER BY name').fetchall()
            return [dict(row) for row in rows]

    def add_issue(self, asset_type: str, asset_id: int, issue_type: str,
                  description: str = None, severity: str = 'medium') -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                '''INSERT INTO issues (asset_type, asset_id, issue_type, description, severity)
                   VALUES (?, ?, ?, ?, ?)''',
                (asset_type, asset_id, issue_type, description, severity)
            )
            issue_id = cursor.lastrowid
            self.log_operation('mark_issue', asset_type,
                               {'asset_id': asset_id, 'issue_type': issue_type, 'severity': severity},
                               conn=conn)
            return issue_id

    def list_issues(self, asset_type: str = None, fixed: bool = False,
                    severity: str = None) -> List[Dict]:
        query = 'SELECT * FROM issues WHERE fixed = ?'
        params = [1 if fixed else 0]
        if asset_type:
            query += ' AND asset_type = ?'
            params.append(asset_type)
        if severity:
            query += ' AND severity = ?'
            params.append(severity)
        query += ' ORDER BY severity, created_at DESC'

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def fix_issue(self, issue_id: int):
        with self._get_connection() as conn:
            conn.execute(
                'UPDATE issues SET fixed = 1, fixed_at = CURRENT_TIMESTAMP WHERE id = ?',
                (issue_id,)
            )
            self.log_operation('fix_issue', None, {'issue_id': issue_id}, conn=conn)

    def save_thumbnail(self, asset_type: str, asset_id: int, file_path: str, size: str):
        with self._get_connection() as conn:
            conn.execute(
                '''INSERT OR REPLACE INTO thumbnails (asset_type, asset_id, file_path, size)
                   VALUES (?, ?, ?, ?)''',
                (asset_type, asset_id, file_path, size)
            )
            self.log_operation('generate_thumbnail', asset_type,
                               {'asset_id': asset_id, 'size': size, 'path': file_path},
                               conn=conn)

    def create_delivery(self, customer_name: str, project_name: str = None,
                        items: List[Tuple[str, int]] = None) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                'INSERT INTO deliveries (customer_name, project_name) VALUES (?, ?)',
                (customer_name, project_name)
            )
            delivery_id = cursor.lastrowid

            if items:
                for asset_type, asset_id in items:
                    conn.execute(
                        '''INSERT OR IGNORE INTO delivery_items (delivery_id, asset_type, asset_id)
                           VALUES (?, ?, ?)''',
                        (delivery_id, asset_type, asset_id)
                    )

            manifest = self._generate_manifest(conn, delivery_id)
            conn.execute(
                'UPDATE deliveries SET manifest = ? WHERE id = ?',
                (json.dumps(manifest, indent=2, ensure_ascii=False), delivery_id)
            )

            self.log_operation('create_delivery', None,
                               {'delivery_id': delivery_id, 'customer': customer_name,
                                'item_count': len(items or [])},
                               conn=conn)
            return delivery_id

    def _generate_manifest(self, conn, delivery_id: int) -> Dict:
        items = conn.execute(
            'SELECT asset_type, asset_id FROM delivery_items WHERE delivery_id = ?',
            (delivery_id,)
        ).fetchall()

        manifest = {'avatars': [], 'wardrobe': [], 'motions': [], 'scenes': []}

        for item in items:
            asset_type = item['asset_type']
            asset_id = item['asset_id']

            if asset_type == 'avatar':
                row = conn.execute('SELECT * FROM avatars WHERE id = ?', (asset_id,)).fetchone()
                if row:
                    manifest['avatars'].append(dict(row))
            elif asset_type == 'wardrobe':
                row = conn.execute('SELECT * FROM wardrobe_items WHERE id = ?', (asset_id,)).fetchone()
                if row:
                    manifest['wardrobe'].append(dict(row))
            elif asset_type == 'motion':
                row = conn.execute('SELECT * FROM motions WHERE id = ?', (asset_id,)).fetchone()
                if row:
                    manifest['motions'].append(dict(row))
            elif asset_type == 'scene':
                row = conn.execute('SELECT * FROM scenes WHERE id = ?', (asset_id,)).fetchone()
                if row:
                    manifest['scenes'].append(dict(row))

        return manifest

    def get_delivery(self, delivery_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            row = conn.execute('SELECT * FROM deliveries WHERE id = ?', (delivery_id,)).fetchone()
            if row:
                result = dict(row)
                if result['manifest']:
                    result['manifest'] = json.loads(result['manifest'])
                return result
        return None

    def list_deliveries(self, customer_name: str = None) -> List[Dict]:
        query = 'SELECT * FROM deliveries WHERE 1=1'
        params = []
        if customer_name:
            query += ' AND customer_name LIKE ?'
            params.append(f'%{customer_name}%')
        query += ' ORDER BY created_at DESC'

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                r = dict(row)
                if r['manifest']:
                    r['manifest'] = json.loads(r['manifest'])
                results.append(r)
            return results

    def _log_version(self, conn, asset_type: str, asset_id: int, version: str, changes: str):
        conn.execute(
            '''INSERT INTO version_history (asset_type, asset_id, version, changes)
               VALUES (?, ?, ?, ?)''',
            (asset_type, asset_id, version, changes)
        )

    def _get_next_version(self, conn, asset_type: str, asset_id: int) -> str:
        row = conn.execute(
            '''SELECT version FROM version_history
               WHERE asset_type = ? AND asset_id = ?
               ORDER BY id DESC LIMIT 1''',
            (asset_type, asset_id)
        ).fetchone()
        if row:
            try:
                major, minor = map(int, row['version'].split('.'))
                return f"{major}.{minor + 1}"
            except (ValueError, IndexError):
                return '1.1'
        return '1.0'

    def get_version_history(self, asset_type: str, asset_id: int) -> List[Dict]:
        with self._get_connection() as conn:
            rows = conn.execute(
                '''SELECT * FROM version_history
                   WHERE asset_type = ? AND asset_id = ?
                   ORDER BY created_at DESC''',
                (asset_type, asset_id)
            ).fetchall()
            return [dict(row) for row in rows]

    def find_duplicates(self, asset_type: str) -> List[List[Dict]]:
        with self._get_connection() as conn:
            if asset_type == 'avatar':
                rows = conn.execute(
                    '''SELECT a1.*, a2.id as duplicate_id, a2.name as duplicate_name
                       FROM avatars a1
                       JOIN avatars a2 ON a1.name = a2.name AND a1.id < a2.id'''
                ).fetchall()
            elif asset_type == 'wardrobe':
                rows = conn.execute(
                    '''SELECT w1.*, w2.id as duplicate_id, w2.name as duplicate_name
                       FROM wardrobe_items w1
                       JOIN wardrobe_items w2 ON w1.name = w2.name AND w1.category = w2.category AND w1.id < w2.id'''
                ).fetchall()
            elif asset_type == 'motion':
                rows = conn.execute(
                    '''SELECT m1.*, m2.id as duplicate_id, m2.name as duplicate_name
                       FROM motions m1
                       JOIN motions m2 ON m1.name = m2.name AND m1.id < m2.id'''
                ).fetchall()
            else:
                return []

            groups = []
            for row in rows:
                d = dict(row)
                duplicate = {'id': d.pop('duplicate_id'), 'name': d.pop('duplicate_name')}
                groups.append([d, duplicate])
            return groups

    def backup_database(self, backup_path: str) -> str:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        final_path = f"{backup_path}_{timestamp}.db"
        shutil.copy2(self.db_path, final_path)
        self.log_operation('backup_database', None, {'backup_path': final_path})
        return final_path
