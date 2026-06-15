import os
import shutil
import json
from datetime import datetime
from typing import Dict, Optional, Callable, Tuple
from pathlib import Path

from .file_ops import safe_rename_file, safe_copy_file


class UndoManager:
    def __init__(self, db):
        self.db = db
        self._undo_handlers = {
            'rename_avatar': self._undo_rename_avatar,
            'update_avatar': self._undo_update_avatar,
            'rename_file': self._undo_rename_file,
            'batch_rename': self._undo_batch_rename,
            'delete_file': self._undo_delete_file,
        }

    def can_undo(self) -> bool:
        last_op = self.db.get_last_operation()
        return last_op is not None and last_op['operation'] in self._undo_handlers

    def get_last_operation_info(self) -> Optional[Dict]:
        return self.db.get_last_operation()

    def undo_last(self) -> Tuple[bool, str]:
        last_op = self.db.get_last_operation()
        if not last_op:
            return False, '没有可撤销的操作'

        operation = last_op['operation']
        handler = self._undo_handlers.get(operation)

        if not handler:
            return False, f'不支持撤销操作: {operation}'

        try:
            success, message = handler(last_op)
            return success, message
        except Exception as e:
            return False, f'撤销失败: {e}'

    def _undo_rename_avatar(self, op: Dict) -> Tuple[bool, str]:
        undo_data = op.get('undo_data', {})
        avatar_id = undo_data.get('id')
        old_name = undo_data.get('old_name')

        if not avatar_id or not old_name:
            return False, '撤销数据不完整'

        try:
            self.db.rename_avatar(avatar_id, old_name)
            return True, f'已恢复头像名称为: {old_name}'
        except Exception as e:
            return False, f'恢复名称失败: {e}'

    def _undo_update_avatar(self, op: Dict) -> Tuple[bool, str]:
        undo_data = op.get('undo_data', {})
        avatar_id = undo_data.get('id')
        old_values = undo_data.get('old_values', {})

        if not avatar_id:
            return False, '撤销数据不完整'

        restorable_fields = {}
        for key in ['name', 'gender', 'style', 'preview_image', 'model_path',
                    'copyright_source', 'copyright_holder', 'license_type', 'version']:
            if key in old_values and old_values[key] is not None:
                restorable_fields[key] = old_values[key]

        try:
            self.db.update_avatar(avatar_id, **restorable_fields)
            return True, f'已恢复头像 #{avatar_id} 的属性'
        except Exception as e:
            return False, f'恢复属性失败: {e}'

    def _undo_rename_file(self, op: Dict) -> Tuple[bool, str]:
        undo_data = op.get('undo_data', {})
        old_path = undo_data.get('old_path')
        new_path = undo_data.get('new_path')

        if not old_path or not new_path:
            return False, '撤销数据不完整'

        if os.path.exists(new_path) and not os.path.exists(old_path):
            if safe_rename_file(new_path, old_path, use_trash=False):
                return True, f'已恢复文件: {old_path}'
            else:
                return False, '恢复文件失败'

        return False, '文件状态已改变，无法撤销'

    def _undo_batch_rename(self, op: Dict) -> Tuple[bool, str]:
        undo_data = op.get('undo_data', {})
        rename_map = undo_data.get('rename_map', {})

        if not rename_map:
            return False, '撤销数据不完整'

        restored = []
        failed = []

        for new_path, old_path in rename_map.items():
            if os.path.exists(new_path) and not os.path.exists(old_path):
                if safe_rename_file(new_path, old_path, use_trash=False):
                    restored.append(old_path)
                else:
                    failed.append(new_path)
            else:
                failed.append(new_path)

        if restored:
            message = f'已恢复 {len(restored)} 个文件'
            if failed:
                message += f', {len(failed)} 个文件恢复失败'
            return True, message
        else:
            return False, '没有文件可以恢复'

    def _undo_delete_file(self, op: Dict) -> Tuple[bool, str]:
        undo_data = op.get('undo_data', {})
        backup_path = undo_data.get('backup_path')
        original_path = undo_data.get('original_path')

        if not backup_path or not original_path:
            return False, '撤销数据不完整'

        if os.path.exists(backup_path):
            try:
                os.makedirs(os.path.dirname(original_path), exist_ok=True)
                shutil.copy2(backup_path, original_path)
                return True, f'已恢复文件: {original_path}'
            except Exception as e:
                return False, f'恢复文件失败: {e}'

        return False, '备份文件不存在，无法撤销删除'

    def register_undo_handler(self, operation: str, handler: Callable):
        self._undo_handlers[operation] = handler


def create_rename_undo_data(old_path: str, new_path: str) -> Dict:
    return {
        'old_path': old_path,
        'new_path': new_path,
        'timestamp': datetime.now().isoformat()
    }


def create_batch_rename_undo_data(successes: list) -> Dict:
    rename_map = {}
    for old_path, new_path in successes:
        rename_map[new_path] = old_path
    return {
        'rename_map': rename_map,
        'timestamp': datetime.now().isoformat()
    }
