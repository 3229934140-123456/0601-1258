import os
import click
from pathlib import Path

from ..database import AssetDatabase
from ..utils.file_ops import scan_directory_for_assets, write_json_file, is_image_file


@click.group()
def scene():
    """场景管理命令"""
    pass


@scene.command('create')
@click.option('--name', '-n', required=True, help='场景名称')
@click.option('--description', '-d', help='场景描述')
@click.option('--environment', '-e', help='环境类型，如：室内、室外、科幻、中世纪等')
@click.option('--lighting', '-l', help='光照方案，如：白天、夜晚、黄昏等')
@click.option('--model', '-m', 'model_path', type=click.Path(exists=True), help='场景模型路径')
@click.option('--preview', '-p', 'preview_path', type=click.Path(exists=True), help='预览图路径')
@click.option('--project', 'project_id', type=int, help='所属项目ID')
def create_scene(name, description, environment, lighting, model_path, preview_path, project_id):
    """创建新场景"""
    db = AssetDatabase()
    try:
        scene_id = db.add_scene(
            name=name,
            description=description,
            environment=environment,
            lighting=lighting,
            model_path=model_path,
            preview_image=preview_path,
            project_id=project_id
        )
        click.echo(f"[OK] 成功创建场景: {name} (ID: {scene_id})")
    except Exception as e:
        click.echo(f"[ERROR] 创建失败: {e}", err=True)


@scene.command('list')
@click.option('--environment', '-e', help='按环境类型筛选')
@click.option('--project', 'project_id', type=int, help='按项目筛选')
@click.option('--format', '-f', 'output_format', type=click.Choice(['table', 'json']),
              default='table', help='输出格式')
def list_scenes(environment, project_id, output_format):
    """列出所有场景"""
    db = AssetDatabase()
    scenes = db.list_scenes(project_id=project_id)

    if environment:
        scenes = [s for s in scenes if s['environment'] and environment.lower() in s['environment'].lower()]

    if not scenes:
        click.echo("未找到场景")
        return

    if output_format == 'table':
        header = f"{'ID':<6} {'名称':<20} {'环境':<12} {'光照':<12} {'模型':<8}"
        click.echo(header)
        click.echo("-" * len(header))
        for s in scenes:
            has_model = '[OK]' if s['model_path'] else '[ERROR]'
            click.echo(
                f"{s['id']:<6} {s['name']:<20} {(s['environment'] or '-'):<12} "
                f"{(s['lighting'] or '-'):<12} {has_model:<8}"
            )
    else:
        import json
        click.echo(json.dumps({'count': len(scenes), 'scenes': scenes},
                              indent=2, ensure_ascii=False))

    click.echo(f"\n共 {len(scenes)} 个场景")


@scene.command('import')
@click.argument('directory', type=click.Path(exists=True, file_okay=False))
@click.option('--environment', '-e', help='默认环境类型')
@click.option('--lighting', '-l', help='默认光照方案')
@click.option('--dry-run', is_flag=True, help='仅预览')
def import_scenes(directory, environment, lighting, dry_run):
    """从目录批量导入场景"""
    assets = scan_directory_for_assets(directory)

    if not assets['models']:
        click.echo("未找到场景模型文件")
        return

    click.echo(f"发现 {len(assets['models'])} 个模型文件")
    click.echo(f"发现 {len(assets['images'])} 个图片文件")

    imported = []
    for model_path in assets['models']:
        model_name = Path(model_path).stem

        preview_image = None
        for img in assets['images']:
            if Path(img).stem == model_name:
                preview_image = img
                break

        if dry_run:
            click.echo(
                f"  [预览] {model_name} | 模型: {Path(model_path).name} | "
                f"预览: {'有' if preview_image else '无'}"
            )
            continue

        db = AssetDatabase()
        try:
            scene_id = db.add_scene(
                name=model_name,
                environment=environment,
                lighting=lighting,
                model_path=model_path,
                preview_image=preview_image
            )
            imported.append((scene_id, model_name))
            click.echo(f"[OK] 导入 {model_name} (ID: {scene_id})")
        except Exception as e:
            click.echo(f"[ERROR] 导入 {model_name} 失败: {e}", err=True)

    if not dry_run:
        click.echo(f"\n共导入 {len(imported)} 个场景")


@scene.command('show')
@click.argument('scene_id', type=int)
def show_scene(scene_id):
    """显示场景详情"""
    db = AssetDatabase()
    scene = db.get_scene(scene_id)
    if not scene:
        click.echo(f"[ERROR] 场景 {scene_id} 不存在", err=True)
        return

    click.echo(f"\n=== 场景信息 ===")
    click.echo(f"ID: {scene['id']}")
    click.echo(f"名称: {scene['name']}")
    click.echo(f"描述: {scene['description'] or '无'}")
    click.echo(f"环境: {scene['environment'] or '未设置'}")
    click.echo(f"光照: {scene['lighting'] or '未设置'}")
    click.echo(f"模型: {scene['model_path'] or '未设置'}")
    click.echo(f"预览: {scene['preview_image'] or '未设置'}")
    click.echo(f"创建时间: {scene['created_at']}")


@scene.command('update')
@click.argument('scene_id', type=int)
@click.option('--name', help='场景名称')
@click.option('--description', help='场景描述')
@click.option('--environment', help='环境类型')
@click.option('--lighting', help='光照方案')
@click.option('--model', 'model_path', type=click.Path(exists=True), help='场景模型路径')
@click.option('--preview', 'preview_path', type=click.Path(exists=True), help='预览图路径')
def update_scene_cmd(scene_id, name, description, environment, lighting, model_path, preview_path):
    """更新场景信息"""
    db = AssetDatabase()
    scene = db.get_scene(scene_id)
    if not scene:
        click.echo(f"[ERROR] 场景 {scene_id} 不存在", err=True)
        return

    updates = {}
    if name:
        updates['name'] = name
    if description:
        updates['description'] = description
    if environment:
        updates['environment'] = environment
    if lighting:
        updates['lighting'] = lighting
    if model_path:
        updates['model_path'] = model_path
    if preview_path:
        updates['preview_image'] = preview_path

    if not updates:
        click.echo("[WARN]  没有指定要更新的字段")
        return

    try:
        db.update_scene(scene_id, **updates)
        click.echo(f"[OK] 已更新场景信息")
    except Exception as e:
        click.echo(f"[ERROR] 更新失败: {e}", err=True)


@scene.command('export')
@click.argument('output_path', type=click.Path())
@click.option('--environment', '-e', help='按环境类型筛选')
def export_scenes(output_path, environment):
    """导出场景清单为JSON"""
    db = AssetDatabase()
    scenes = db.list_scenes()

    if environment:
        scenes = [s for s in scenes if s['environment'] and environment.lower() in s['environment'].lower()]

    if not scenes:
        click.echo("未找到场景")
        return

    export_data = {
        'count': len(scenes),
        'environment_filter': environment,
        'scenes': scenes
    }

    if write_json_file(output_path, export_data):
        click.echo(f"[OK] 已导出 {len(scenes)} 个场景到 {output_path}")
    else:
        click.echo(f"[ERROR] 导出失败", err=True)
