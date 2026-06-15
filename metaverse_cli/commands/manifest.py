import os
import json
import csv
import click
from ..database import AssetDatabase


@click.group()
def manifest():
    """批量导入命令（从CSV/JSON清单导入资产）"""
    pass


@manifest.command('import')
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--project', 'project_id', type=int, help='归入指定项目ID')
@click.option('--dry-run', is_flag=True, help='仅预览，不实际导入')
@click.option('--stop-on-error', is_flag=True, help='遇到错误即停止')
def import_manifest(file_path, project_id, dry_run, stop_on_error):
    """从CSV或JSON清单批量导入资产"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.json':
        records = _parse_json_manifest(file_path)
    elif ext == '.csv':
        records = _parse_csv_manifest(file_path)
    else:
        click.echo(f"[ERROR] 不支持的文件格式: {ext}，请使用 .json 或 .csv", err=True)
        return

    if not records:
        click.echo("[ERROR] 清单为空或格式有误", err=True)
        return

    click.echo(f"读取到 {len(records)} 条记录")

    if project_id:
        db_check = AssetDatabase()
        proj = db_check.get_project(project_id)
        if not proj:
            click.echo(f"[ERROR] 项目 {project_id} 不存在", err=True)
            return
        click.echo(f"目标项目: {proj['name']}")

    if dry_run:
        click.echo("\n=== 预览模式 ===")
        for i, rec in enumerate(records, 1):
            atype = rec.get('type', 'unknown')
            name = rec.get('name', 'unknown')
            click.echo(f"  [{i}] {atype}: {name}")
            _validate_record(rec, indent=4)
        click.echo(f"\n共 {len(records)} 条记录待导入")
        return

    db = AssetDatabase()
    succeeded = 0
    skipped = 0
    failed = 0
    errors = []

    for i, rec in enumerate(records, 1):
        atype = rec.get('type', '').lower()
        name = rec.get('name', '')

        if not atype or not name:
            click.echo(f"  [{i}] [SKIP] 缺少 type 或 name 字段")
            skipped += 1
            if stop_on_error:
                break
            continue

        try:
            asset_id = _import_single_asset(db, rec, project_id)
            if asset_id:
                succeeded += 1
                click.echo(f"  [{i}] [OK] {atype}: {name} (ID: {asset_id})")
            else:
                skipped += 1
                click.echo(f"  [{i}] [SKIP] {atype}: {name} - 已存在")
        except Exception as e:
            failed += 1
            err_msg = f"{atype} '{name}': {e}"
            errors.append(err_msg)
            click.echo(f"  [{i}] [ERROR] {err_msg}")
            if stop_on_error:
                break

    click.echo(f"\n=== 导入完成 ===")
    click.echo(f"成功: {succeeded}")
    click.echo(f"跳过: {skipped}")
    click.echo(f"失败: {failed}")

    if errors:
        click.echo("\n失败详情:")
        for err in errors:
            click.echo(f"  - {err}")


def _parse_json_manifest(file_path: str) -> list:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        if 'assets' in data:
            return data['assets']
        return [data]
    return []


def _parse_csv_manifest(file_path: str) -> list:
    records = []
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            record = {}
            for key, value in row.items():
                key = key.strip().lower()
                value = value.strip() if value else ''
                if key in ('tags', 'textures') and value:
                    record[key] = [t.strip() for t in value.split('|') if t.strip()]
                elif key == 'project_id' and value:
                    record[key] = int(value)
                else:
                    record[key] = value
            records.append(record)
    return records


def _validate_record(rec: dict, indent: int = 2):
    prefix = ' ' * indent
    atype = rec.get('type', '')

    if atype in ('avatar', 'wardrobe', 'motion', 'scene'):
        model = rec.get('model_path') or rec.get('file_path')
        if model and not os.path.exists(model):
            click.echo(f"{prefix}[WARN] 模型路径不存在: {model}")
        preview = rec.get('preview_image')
        if preview and not os.path.exists(preview):
            click.echo(f"{prefix}[WARN] 预览图不存在: {preview}")
    else:
        click.echo(f"{prefix}[WARN] 未知资产类型: {atype}")


def _import_single_asset(db: AssetDatabase, rec: dict, project_id: int = None) -> int:
    atype = rec.get('type', '').lower()
    pid = rec.get('project_id') or project_id

    if atype == 'avatar':
        existing = db.get_avatar_by_name(rec['name'])
        if existing:
            return 0
        return db.add_avatar(
            name=rec['name'],
            gender=rec.get('gender'),
            style=rec.get('style'),
            model_path=rec.get('model_path'),
            preview_image=rec.get('preview_image'),
            project_id=pid
        )

    elif atype == 'wardrobe':
        return db.add_wardrobe_item(
            name=rec['name'],
            category=rec.get('category', 'other'),
            gender=rec.get('gender'),
            style=rec.get('style'),
            model_path=rec.get('model_path'),
            texture_paths=rec.get('textures'),
            preview_image=rec.get('preview_image'),
            project_id=pid
        )

    elif atype == 'motion':
        return db.add_motion(
            name=rec['name'],
            file_path=rec.get('file_path', ''),
            category=rec.get('category'),
            duration=float(rec['duration']) if rec.get('duration') else None,
            frame_count=int(rec['frame_count']) if rec.get('frame_count') else None,
            fps=int(rec['fps']) if rec.get('fps') else None,
            target_rig=rec.get('target_rig'),
            project_id=pid
        )

    elif atype == 'scene':
        return db.add_scene(
            name=rec['name'],
            description=rec.get('description'),
            environment=rec.get('environment'),
            lighting=rec.get('lighting'),
            model_path=rec.get('model_path'),
            preview_image=rec.get('preview_image'),
            project_id=pid
        )

    else:
        raise ValueError(f"未知资产类型: {atype}")


@manifest.command('template')
@click.argument('output_path', type=click.Path())
@click.option('--format', 'output_format',
              type=click.Choice(['json', 'csv']),
              default='json', help='模板格式')
def generate_template(output_path, output_format):
    """生成批量导入清单模板"""
    if output_format == 'json':
        template = [
            {
                "type": "avatar",
                "name": "角色名称",
                "gender": "female",
                "style": "卡通",
                "model_path": "path/to/model.fbx",
                "preview_image": "path/to/preview.png",
                "copyright_source": "自研",
                "tags": ["标签1", "标签2"]
            },
            {
                "type": "wardrobe",
                "name": "服装名称",
                "category": "top",
                "gender": "neutral",
                "model_path": "path/to/model.obj",
                "preview_image": "path/to/preview.jpg",
                "textures": ["path/to/albedo.png", "path/to/normal.png"]
            },
            {
                "type": "motion",
                "name": "动作名称",
                "file_path": "path/to/motion.bvh",
                "category": "walk",
                "duration": 2.5,
                "fps": 30
            },
            {
                "type": "scene",
                "name": "场景名称",
                "description": "场景描述",
                "environment": "室外",
                "lighting": "白天",
                "model_path": "path/to/scene.glb",
                "preview_image": "path/to/preview.jpg"
            }
        ]
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=2, ensure_ascii=False)

    elif output_format == 'csv':
        headers = [
            'type', 'name', 'gender', 'style', 'category',
            'model_path', 'file_path', 'preview_image',
            'textures', 'description', 'environment', 'lighting',
            'copyright_source', 'tags', 'duration', 'fps', 'target_rig'
        ]
        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerow([
                'avatar', '角色名称', 'female', '卡通', '',
                'path/to/model.fbx', '', 'path/to/preview.png',
                '', '', '', '', '自研', '标签1|标签2', '', '', ''
            ])
            writer.writerow([
                'wardrobe', '服装名称', 'neutral', '', 'top',
                'path/to/model.obj', '', 'path/to/preview.jpg',
                'path/to/albedo.png|path/to/normal.png', '', '', '', '', '', '', '', ''
            ])
            writer.writerow([
                'motion', '动作名称', '', '', 'walk',
                '', 'path/to/motion.bvh', '',
                '', '', '', '', '', '', '2.5', '30', ''
            ])
            writer.writerow([
                'scene', '场景名称', '', '', '',
                'path/to/scene.glb', '', 'path/to/preview.jpg',
                '', '场景描述', '室外', '白天', '', '', '', '', ''
            ])

    click.echo(f"[OK] 模板已生成: {output_path}")
    click.echo("请按模板格式填写资产信息后使用 manifest import 导入")
