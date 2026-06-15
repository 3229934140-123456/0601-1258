import os
import click
import re
from typing import Dict, List
from pathlib import Path

from ..database import AssetDatabase
from ..utils.file_ops import (
    scan_directory_for_assets, safe_copy_file,
    batch_rename_files, write_json_file, is_image_file
)
from ..utils.undo import create_batch_rename_undo_data


@click.group()
def avatar():
    """头像资产管理命令"""
    pass


@avatar.command('create')
@click.option('--name', '-n', required=True, help='角色名称')
@click.option('--gender', '-g', type=click.Choice(['male', 'female', 'neutral']), help='性别')
@click.option('--style', '-s', help='风格标签，如：卡通、写实、科幻等')
@click.option('--model', '-m', 'model_path', type=click.Path(exists=True), help='模型文件路径')
@click.option('--preview', '-p', 'preview_path', type=click.Path(exists=True), help='预览图路径')
def create_avatar(name, gender, style, model_path, preview_path):
    """创建新角色"""
    db = AssetDatabase()
    try:
        avatar_id = db.add_avatar(
            name=name,
            gender=gender,
            style=style,
            model_path=model_path,
            preview_image=preview_path
        )
        click.echo(f"[OK] 成功创建角色: {name} (ID: {avatar_id})")
    except Exception as e:
        click.echo(f"[ERROR] 创建失败: {e}", err=True)


@avatar.command('list')
@click.option('--gender', '-g', type=click.Choice(['male', 'female', 'neutral']), help='按性别筛选')
@click.option('--style', '-s', help='按风格筛选')
@click.option('--format', '-f', 'output_format', type=click.Choice(['table', 'json', 'csv']), default='table',
              help='输出格式')
@click.option('--output', '-o', type=click.Path(), help='输出到文件')
def list_avatars(gender, style, output_format, output):
    """列出所有角色"""
    db = AssetDatabase()
    avatars = db.list_avatars(gender=gender, style=style)

    if not avatars:
        click.echo("未找到角色")
        return

    if output_format == 'table':
        _print_avatar_table(avatars)
    elif output_format == 'json':
        content = _format_avatars_json(avatars)
        if output:
            write_json_file(output, {'avatars': avatars})
            click.echo(f"已保存到 {output}")
        else:
            click.echo(content)
    elif output_format == 'csv':
        content = _format_avatars_csv(avatars)
        if output:
            with open(output, 'w', encoding='utf-8') as f:
                f.write(content)
            click.echo(f"已保存到 {output}")
        else:
            click.echo(content)


@avatar.command('import')
@click.argument('directory', type=click.Path(exists=True, file_okay=False))
@click.option('--gender', '-g', type=click.Choice(['male', 'female', 'neutral']), help='默认性别')
@click.option('--style', '-s', help='默认风格')
@click.option('--dry-run', is_flag=True, help='仅预览，不实际导入')
def import_from_dir(directory, gender, style, dry_run):
    """从目录批量导入角色"""
    assets = scan_directory_for_assets(directory)

    if not assets['models']:
        click.echo("未找到模型文件")
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
            click.echo(f"  [预览] 导入: {model_name} | 模型: {model_path} | 预览: {preview_image or '无'}")
            continue

        db = AssetDatabase()
        try:
            avatar_id = db.add_avatar(
                name=model_name,
                gender=gender,
                style=style,
                model_path=model_path,
                preview_image=preview_image
            )
            imported.append((avatar_id, model_name))
            click.echo(f"[OK] 导入 {model_name} (ID: {avatar_id})")
        except Exception as e:
            click.echo(f"[ERROR] 导入 {model_name} 失败: {e}", err=True)

    if not dry_run:
        click.echo(f"\n共导入 {len(imported)} 个角色")


@avatar.command('set-preview')
@click.argument('avatar_id', type=int)
@click.argument('image_path', type=click.Path(exists=True))
def set_preview(avatar_id, image_path):
    """设置角色预览图"""
    db = AssetDatabase()
    avatar = db.get_avatar(avatar_id)
    if not avatar:
        click.echo(f"[ERROR] 角色 {avatar_id} 不存在", err=True)
        return

    if not is_image_file(image_path):
        click.echo(f"[ERROR] 不是有效的图片文件", err=True)
        return

    db.update_avatar(avatar_id, preview_image=image_path)
    click.echo(f"[OK] 已设置预览图: {image_path}")


@avatar.command('set-copyright')
@click.argument('avatar_id', type=int)
@click.option('--source', required=True, help='版权来源，如：原创、授权购买、外包等')
@click.option('--holder', help='版权持有者')
@click.option('--license', 'license_type', help='授权类型，如：商业使用、非商业使用等')
def set_copyright(avatar_id, source, holder, license_type):
    """设置角色版权信息"""
    db = AssetDatabase()
    avatar = db.get_avatar(avatar_id)
    if not avatar:
        click.echo(f"[ERROR] 角色 {avatar_id} 不存在", err=True)
        return

    updates = {'copyright_source': source}
    if holder:
        updates['copyright_holder'] = holder
    if license_type:
        updates['license_type'] = license_type

    db.update_avatar(avatar_id, **updates)
    click.echo(f"[OK] 已更新版权信息")


@avatar.command('tag')
@click.argument('avatar_id', type=int)
@click.argument('tag_names', nargs=-1, required=True)
@click.option('--category', default='general', help='标签分类')
def add_tags(avatar_id, tag_names, category):
    """为角色添加标签（性别、风格等）"""
    db = AssetDatabase()
    avatar = db.get_avatar(avatar_id)
    if not avatar:
        click.echo(f"[ERROR] 角色 {avatar_id} 不存在", err=True)
        return

    for tag in tag_names:
        db.tag_avatar(avatar_id, tag, category)
        click.echo(f"[OK] 已添加标签: {tag}")


@avatar.command('batch-tag')
@click.option('--gender', '-g', type=click.Choice(['male', 'female', 'neutral']), help='按性别筛选')
@click.option('--style', '-s', help='按风格筛选')
@click.argument('tag_names', nargs=-1, required=True)
@click.option('--category', default='general', help='标签分类')
@click.option('--dry-run', is_flag=True, help='仅预览')
def batch_tag(gender, style, tag_names, category, dry_run):
    """批量为角色打标签"""
    db = AssetDatabase()
    avatars = db.list_avatars(gender=gender, style=style)

    if not avatars:
        click.echo("未找到匹配的角色")
        return

    click.echo(f"将为 {len(avatars)} 个角色添加标签: {', '.join(tag_names)}")

    for avatar in avatars:
        if dry_run:
            click.echo(f"  [预览] {avatar['name']} (ID: {avatar['id']})")
            continue

        for tag in tag_names:
            db.tag_avatar(avatar['id'], tag, category)
        click.echo(f"[OK] {avatar['name']}")

    if not dry_run:
        click.echo(f"\n完成，共处理 {len(avatars)} 个角色")


@avatar.command('rename')
@click.argument('avatar_id', type=int)
@click.argument('new_name')
def rename_avatar(avatar_id, new_name):
    """重命名单个角色"""
    db = AssetDatabase()
    avatar = db.get_avatar(avatar_id)
    if not avatar:
        click.echo(f"[ERROR] 角色 {avatar_id} 不存在", err=True)
        return

    if db.rename_avatar(avatar_id, new_name):
        click.echo(f"[OK] 已重命名: {avatar['name']} → {new_name}")
    else:
        click.echo(f"[ERROR] 重命名失败，名称可能已存在", err=True)


@avatar.command('batch-rename')
@click.argument('directory', type=click.Path(exists=True, file_okay=False))
@click.option('--pattern', required=True, help='匹配模式，使用 {n} 表示序号')
@click.option('--start', type=int, default=1, help='起始序号')
@click.option('--pad', type=int, default=3, help='序号补零位数')
@click.option('--filter', 'name_filter', help='仅处理包含该字符串的文件')
@click.option('--dry-run', is_flag=True, help='仅预览')
def batch_rename(directory, pattern, start, pad, name_filter, dry_run):
    """批量重命名文件并更新数据库"""
    assets = scan_directory_for_assets(directory)
    all_files = assets['models'] + assets['images'] + assets['motions']

    if name_filter:
        all_files = [f for f in all_files if name_filter in os.path.basename(f)]

    if not all_files:
        click.echo("未找到可重命名的文件")
        return

    rename_map: Dict[str, str] = {}
    current_index = start

    for old_path in sorted(all_files):
        old_name = Path(old_path).name
        ext = Path(old_path).suffix

        new_filename = pattern.format(n=str(current_index).zfill(pad)) + ext
        new_path = os.path.join(os.path.dirname(old_path), new_filename)

        if old_path != new_path:
            rename_map[old_path] = new_path
        current_index += 1

    if not rename_map:
        click.echo("没有需要重命名的文件")
        return

    click.echo(f"将重命名 {len(rename_map)} 个文件:")
    for old, new in list(rename_map.items())[:10]:
        click.echo(f"  {Path(old).name} → {Path(new).name}")
    if len(rename_map) > 10:
        click.echo(f"  ... 还有 {len(rename_map) - 10} 个文件")

    if dry_run:
        return

    if not click.confirm("确认执行重命名？"):
        return

    successes, failures = batch_rename_files(rename_map)

    db = AssetDatabase()
    db.log_operation(
        'batch_rename',
        None,
        {'count': len(successes), 'failures': failures},
        create_batch_rename_undo_data(successes)
    )

    click.echo(f"\n[OK] 成功重命名 {len(successes)} 个文件")
    if failures:
        click.echo(f"[ERROR] {len(failures)} 个文件失败:")
        for f in failures[:5]:
            click.echo(f"   - {f}")


@avatar.command('export-list')
@click.argument('output_path', type=click.Path())
@click.option('--gender', '-g', type=click.Choice(['male', 'female', 'neutral']), help='按性别筛选')
@click.option('--style', '-s', help='按风格筛选')
@click.option('--include-tags', is_flag=True, help='包含标签信息')
def export_list(output_path, gender, style, include_tags):
    """导出角色清单为JSON"""
    db = AssetDatabase()
    avatars = db.list_avatars(gender=gender, style=style)

    if not avatars:
        click.echo("未找到角色")
        return

    result = []
    for avatar in avatars:
        data = dict(avatar)
        if include_tags:
            tags = db.get_avatar_tags(avatar['id'])
            data['tags'] = [t['name'] for t in tags]
        result.append(data)

    output = {
        'exported_at': db._get_connection().__enter__().execute(
            "SELECT datetime('now')"
        ).fetchone()[0] if False else None,
        'count': len(result),
        'avatars': result
    }

    if write_json_file(output_path, output):
        click.echo(f"[OK] 已导出 {len(result)} 个角色到 {output_path}")
    else:
        click.echo(f"[ERROR] 导出失败", err=True)


@avatar.command('show')
@click.argument('avatar_id', type=int)
def show_avatar(avatar_id):
    """显示角色详细信息"""
    db = AssetDatabase()
    avatar = db.get_avatar(avatar_id)
    if not avatar:
        click.echo(f"[ERROR] 角色 {avatar_id} 不存在", err=True)
        return

    click.echo(f"\n=== 角色信息 ===")
    click.echo(f"ID: {avatar['id']}")
    click.echo(f"名称: {avatar['name']}")
    click.echo(f"性别: {avatar['gender'] or '未设置'}")
    click.echo(f"风格: {avatar['style'] or '未设置'}")
    click.echo(f"版本: {avatar['version']}")
    click.echo(f"状态: {avatar['status']}")
    click.echo(f"模型: {avatar['model_path'] or '未设置'}")
    click.echo(f"预览: {avatar['preview_image'] or '未设置'}")

    if avatar['copyright_source']:
        click.echo(f"\n=== 版权信息 ===")
        click.echo(f"来源: {avatar['copyright_source']}")
        if avatar['copyright_holder']:
            click.echo(f"持有者: {avatar['copyright_holder']}")
        if avatar['license_type']:
            click.echo(f"授权: {avatar['license_type']}")

    tags = db.get_avatar_tags(avatar_id)
    if tags:
        click.echo(f"\n=== 标签 ===")
        for tag in tags:
            click.echo(f"  - {tag['name']} ({tag['category'] or '通用'})")

    outfits = db.get_avatar_outfits(avatar_id)
    if outfits:
        click.echo(f"\n=== 绑定套装 ===")
        for outfit in outfits:
            items = db.get_outfit_items(outfit['id'])
            click.echo(f"  - {outfit['name']} ({len(items)} 件)")

    version_history = db.get_version_history('avatar', avatar_id)
    if version_history:
        click.echo(f"\n=== 版本历史 ===")
        for v in version_history:
            click.echo(f"  v{v['version']} - {v['changes']} ({v['created_at']})")


def _print_avatar_table(avatars):
    header = f"{'ID':<6} {'名称':<20} {'性别':<8} {'风格':<12} {'版本':<8} {'状态':<8}"
    click.echo(header)
    click.echo("-" * len(header))
    for a in avatars:
        click.echo(
            f"{a['id']:<6} {a['name']:<20} {(a['gender'] or '-'):<8} "
            f"{(a['style'] or '-'):<12} {a['version']:<8} {a['status']:<8}"
        )


def _format_avatars_json(avatars):
    import json
    return json.dumps({'count': len(avatars), 'avatars': avatars},
                      indent=2, ensure_ascii=False)


def _format_avatars_csv(avatars):
    lines = ['id,name,gender,style,version,status,model_path,preview_image']
    for a in avatars:
        line = ','.join([
            str(a['id']),
            a['name'],
            a['gender'] or '',
            a['style'] or '',
            a['version'],
            a['status'],
            a['model_path'] or '',
            a['preview_image'] or ''
        ])
        lines.append(line)
    return '\n'.join(lines)
