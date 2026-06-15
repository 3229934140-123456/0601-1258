import os
from typing import Tuple, Optional
from pathlib import Path

try:
    from PIL import Image, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


THUMBNAIL_SIZES = {
    'icon': (64, 64),
    'small': (128, 128),
    'medium': (256, 256),
    'large': (512, 512),
    'xlarge': (1024, 1024),
}


def is_pil_available() -> bool:
    return PIL_AVAILABLE


def generate_thumbnail(source_path: str, output_path: str,
                       size: Tuple[int, int] = (256, 256),
                       crop: bool = True,
                       quality: int = 85) -> bool:
    if not PIL_AVAILABLE:
        return False

    if not os.path.exists(source_path):
        return False

    try:
        with Image.open(source_path) as img:
            if crop:
                img = ImageOps.fit(img, size, method=Image.LANCZOS)
            else:
                img.thumbnail(size, Image.LANCZOS)

            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background

            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            ext = Path(output_path).suffix.lower()
            if ext in ('.jpg', '.jpeg'):
                img.save(output_path, 'JPEG', quality=quality, optimize=True)
            elif ext == '.png':
                img.save(output_path, 'PNG', optimize=True)
            elif ext == '.webp':
                img.save(output_path, 'WEBP', quality=quality)
            else:
                img.save(output_path, quality=quality)

        return True
    except Exception:
        return False


def generate_multiple_thumbnails(source_path: str, output_dir: str,
                                 sizes: dict = None) -> dict:
    if not PIL_AVAILABLE:
        return {}

    sizes = sizes or THUMBNAIL_SIZES
    results = {}

    for name, size in sizes.items():
        output_path = os.path.join(
            output_dir,
            f"{Path(source_path).stem}_{name}{Path(source_path).suffix}"
        )
        if generate_thumbnail(source_path, output_path, size):
            results[name] = output_path

    return results


def get_image_info(file_path: str) -> Optional[dict]:
    if not PIL_AVAILABLE or not os.path.exists(file_path):
        return None

    try:
        with Image.open(file_path) as img:
            return {
                'width': img.width,
                'height': img.height,
                'mode': img.mode,
                'format': img.format,
                'size': os.path.getsize(file_path),
                'aspect_ratio': img.width / img.height if img.height > 0 else 0
            }
    except Exception:
        return None


def validate_image(file_path: str) -> dict:
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

    if not PIL_AVAILABLE:
        result['warnings'].append('Pillow库未安装，无法进行高级图像验证')
        result['info']['extension'] = Path(file_path).suffix.lower()
        result['info']['size_bytes'] = os.path.getsize(file_path)
        return result

    try:
        with Image.open(file_path) as img:
            img.verify()

        with Image.open(file_path) as img:
            result['info'] = {
                'width': img.width,
                'height': img.height,
                'mode': img.mode,
                'format': img.format,
                'size_bytes': os.path.getsize(file_path)
            }

            if img.width < 64 or img.height < 64:
                result['warnings'].append('图像尺寸过小')

            power_of_two = (img.width & (img.width - 1)) == 0 and (img.height & (img.height - 1)) == 0
            if not power_of_two:
                result['warnings'].append('图像尺寸不是2的幂次方（可能影响渲染性能）')

            if img.mode not in ('RGB', 'RGBA', 'L', 'LA'):
                result['warnings'].append(f'图像模式 {img.mode} 不常见，建议转换为RGB/RGBA')

    except Exception as e:
        result['errors'].append(f'图像验证失败: {e}')
        result['valid'] = False

    return result
