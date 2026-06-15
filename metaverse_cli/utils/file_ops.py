import os
import re
import hashlib
import shutil
import json
import filetype
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from send2trash import send2trash


SUPPORTED_MODEL_EXTENSIONS = {'.fbx', '.obj', '.glb', '.gltf', '.ma', '.mb', '.max', '.blend'}
SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff', '.bmp', '.psd', '.hdr', '.exr'}
SUPPORTED_MOTION_EXTENSIONS = {'.fbx', '.bvh', '.glb', '.gltf', '.anim'}


def get_file_hash(file_path: str, chunk_size: int = 8192) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(chunk_size), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def is_model_file(file_path: str) -> bool:
    ext = Path(file_path).suffix.lower()
    if ext in SUPPORTED_MODEL_EXTENSIONS:
        return True
    try:
        kind = filetype.guess(file_path)
        if kind and kind.mime in {'application/octet-stream', 'model/obj', 'model/gltf-binary'}:
            return True
    except Exception:
        pass
    return False


def is_image_file(file_path: str) -> bool:
    ext = Path(file_path).suffix.lower()
    if ext in SUPPORTED_IMAGE_EXTENSIONS:
        return True
    try:
        kind = filetype.guess(file_path)
        if kind and kind.mime.startswith('image/'):
            return True
    except Exception:
        pass
    return False


def is_motion_file(file_path: str) -> bool:
    ext = Path(file_path).suffix.lower()
    return ext in SUPPORTED_MOTION_EXTENSIONS


def find_files_by_extension(directory: str, extensions: set) -> List[str]:
    found = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            if Path(f).suffix.lower() in extensions:
                found.append(os.path.join(root, f))
    return sorted(found)


def find_model_files(directory: str) -> List[str]:
    return find_files_by_extension(directory, SUPPORTED_MODEL_EXTENSIONS)


def find_image_files(directory: str) -> List[str]:
    return find_files_by_extension(directory, SUPPORTED_IMAGE_EXTENSIONS)


def find_missing_textures(model_path: str, texture_dir: str = None) -> List[str]:
    if not os.path.exists(model_path):
        return []

    texture_dir = texture_dir or os.path.dirname(model_path)
    missing = []

    try:
        with open(model_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        texture_refs = re.findall(r'[\'"]([^\'"]+\.(?:png|jpg|jpeg|tga|tif|tiff|bmp|psd|hdr|exr))[\'"]',
                                 content, re.IGNORECASE)

        for ref in texture_refs:
            texture_name = os.path.basename(ref)
            if not os.path.exists(os.path.join(texture_dir, texture_name)):
                missing.append(ref)
    except Exception:
        pass

    return list(set(missing))


def scan_directory_for_assets(directory: str) -> Dict[str, List[str]]:
    result = {
        'models': [],
        'images': [],
        'motions': [],
        'unknown': []
    }

    for root, dirs, files in os.walk(directory):
        for f in files:
            full_path = os.path.join(root, f)
            if is_model_file(full_path):
                result['models'].append(full_path)
            elif is_image_file(full_path):
                result['images'].append(full_path)
            else:
                ext = Path(f).suffix.lower()
                if ext in SUPPORTED_MOTION_EXTENSIONS:
                    result['motions'].append(full_path)
                else:
                    result['unknown'].append(full_path)

    for key in result:
        result[key].sort()

    return result


def safe_rename_file(old_path: str, new_path: str, use_trash: bool = True) -> bool:
    if not os.path.exists(old_path):
        return False
    if os.path.exists(new_path):
        return False
    try:
        os.rename(old_path, new_path)
        return True
    except Exception:
        return False


def safe_delete_file(file_path: str, use_trash: bool = True) -> bool:
    if not os.path.exists(file_path):
        return False
    try:
        if use_trash:
            send2trash(file_path)
        else:
            os.remove(file_path)
        return True
    except Exception:
        return False


def safe_copy_file(src: str, dst: str) -> bool:
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return True
    except Exception:
        return False


def batch_rename_files(file_map: Dict[str, str], use_trash: bool = True) -> Tuple[List[Tuple[str, str]], List[str]]:
    successes = []
    failures = []

    for old_path, new_path in file_map.items():
        if safe_rename_file(old_path, new_path, use_trash):
            successes.append((old_path, new_path))
        else:
            failures.append(old_path)

    return successes, failures


def find_duplicate_files(directory: str) -> Dict[str, List[str]]:
    hash_map: Dict[str, List[str]] = {}

    for root, dirs, files in os.walk(directory):
        for f in files:
            full_path = os.path.join(root, f)
            try:
                file_hash = get_file_hash(full_path)
                if file_hash not in hash_map:
                    hash_map[file_hash] = []
                hash_map[file_hash].append(full_path)
            except Exception:
                continue

    return {k: v for k, v in hash_map.items() if len(v) > 1}


def get_file_size_mb(file_path: str) -> float:
    if not os.path.exists(file_path):
        return 0.0
    size_bytes = os.path.getsize(file_path)
    return size_bytes / (1024 * 1024)


def ensure_directory(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def read_json_file(file_path: str) -> Optional[Dict]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def write_json_file(file_path: str, data: Dict, indent: int = 2) -> bool:
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        return True
    except Exception:
        return False


def validate_motion_file(file_path: str) -> Dict:
    result = {
        'valid': True,
        'errors': [],
        'warnings': [],
        'info': {}
    }

    if not os.path.exists(file_path):
        result['errors'].append('文件不存在')
        result['valid'] = False
        return result

    ext = Path(file_path).suffix.lower()

    if ext not in SUPPORTED_MOTION_EXTENSIONS:
        result['errors'].append(f'不支持的文件格式: {ext}')
        result['valid'] = False
        return result

    file_size = os.path.getsize(file_path)
    result['info']['file_size_bytes'] = file_size

    if file_size == 0:
        result['errors'].append('文件为空')
        result['valid'] = False
        return result

    if ext == '.bvh':
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            if 'HIERARCHY' not in content:
                result['errors'].append('BVH文件缺少HIERARCHY部分')
            if 'MOTION' not in content:
                result['errors'].append('BVH文件缺少MOTION部分')

            frame_match = re.search(r'Frames:\s*(\d+)', content)
            if frame_match:
                result['info']['frame_count'] = int(frame_match.group(1))

            fps_match = re.search(r'Frame Time:\s*([\d.]+)', content)
            if fps_match:
                result['info']['fps'] = 1.0 / float(fps_match.group(1))

        except Exception as e:
            result['errors'].append(f'解析BVH文件失败: {e}')

    result['valid'] = len(result['errors']) == 0
    return result


def copy_assets_to_delivery(assets: List[Dict], delivery_dir: str) -> Tuple[List[str], List[str]]:
    copied = []
    failed = []

    for asset in assets:
        if 'file_path' in asset and asset['file_path']:
            src = asset['file_path']
            dst = os.path.join(delivery_dir, os.path.basename(src))
            if safe_copy_file(src, dst):
                copied.append(dst)
            else:
                failed.append(src)

        if 'texture_paths' in asset and asset['texture_paths']:
            texture_dir = os.path.join(delivery_dir, 'textures')
            for tex_path in asset['texture_paths']:
                if os.path.exists(tex_path):
                    dst = os.path.join(texture_dir, os.path.basename(tex_path))
                    if safe_copy_file(tex_path, dst):
                        copied.append(dst)
                    else:
                        failed.append(tex_path)

        if 'preview_image' in asset and asset['preview_image']:
            preview_dir = os.path.join(delivery_dir, 'previews')
            src = asset['preview_image']
            dst = os.path.join(preview_dir, os.path.basename(src))
            if safe_copy_file(src, dst):
                copied.append(dst)
            else:
                failed.append(src)

    return copied, failed
