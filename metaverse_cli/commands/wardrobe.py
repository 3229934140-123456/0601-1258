import os
import click
import json
from typing import List
from pathlib import Path

from ..database import AssetDatabase
from ..utils.file_ops import scan_directory_for_assets, write_json_file, is_image_file


@click.group()
def wardrobe():
    """衣柜与服装资产管理命令"""
    pass


@wardrobe.command('add-item')
@click.option('--name', '-n', required=True, help='服装名称')
@click.option('--category', '-c', required=True,
              type=click.Choice(['top', 'bottom', 'shoes', 'hat', 'accessory', 'fullbody', 'hair']),
              help='服装类别')
@click.option('--gender', '-g', type=click.Choice(['male', 'female', 'neutral']), help='适用性别')
@click.option('--style', '-s', help='风格标签')
@click.option('--model', '-m', 'model_path', type=click.Path(exists=True), help='模型文件路径')
@click.option('--texture', '-t', 'texture_paths', multiple=True, type=click.Path(exists=True),
              help='贴图文件路径（可多次指定）')
@click.option('--preview', '-p', 'preview_path', type=click.Path(exists=True), help='预览图路径')
@click.option('--copyright', 'copyright_source', help='版权来源')
@click.option('--project', 'project_id', type=int, help='所属项目ID')
def add_item(name, category, gender, style, model_path, texture_paths, preview_path, copyright_source, project_id):
    """添加服装单品"""
    db = AssetDatabase()
    try:
        item_id = db.add_wardrobe_item(
            name=name,
            category=category,
            gender=gender,
            style=style,
            model_path=model_path,
            texture_paths=list(texture_paths) if texture_paths else None,
            preview_image=preview_path,
            project_id=project_id
        )
        if copyright_source:
            with db._get_connection() as conn:
                conn.execute(
                    'UPDATE wardrobe_items SET copyright_source = ? WHERE id = ?',
                    (copyright_source, item_id)
                )
        click.echo(f"[OK] 成功添加服装: {name} (ID: {item_id}, 类别: {category})")
    except Exception as e:
        click.echo(f"[ERROR] 添加失败: {e}", err=True)


@wardrobe.command('list-items')
@click.option('--category', '-c',
              type=click.Choice(['top', 'bottom', 'shoes', 'hat', 'accessory', 'fullbody', 'hair']),
              help='按类别筛选')
@click.option('--gender', '-g', type=click.Choice(['male', 'female', 'neutral']), help='按性别筛选')
@click.option('--style', '-s', help='按风格筛选')
@click.option('--project', 'project_id', type=int, help='按项目筛选')
def list_items(category, gender, style, project_id):
    """列出服装单品"""
    db = AssetDatabase()
    items = db.list_wardrobe_items(category=category, gender=gender, style=style, project_id=project_id)

    if not items:
        click.echo("未找到服装单品")
        return

    header = f"{'ID':<6} {'名称':<20} {'类别':<12} {'性别':<8} {'风格':<12} {'版本':<8}"
    click.echo(header)
    click.echo("-" * len(header))
    for item in items:
        click.echo(
            f"{item['id']:<6} {item['name']:<20} {item['category']:<12} "
            f"{(item['gender'] or '-'):<8} {(item['style'] or '-'):<12} {item['version']:<8}"
        )

    click.echo(f"\n共 {len(items)} 件服装")


@wardrobe.command('import')
@click.argument('directory', type=click.Path(exists=True, file_okay=False))
@click.option('--category', '-c', required=True,
              type=click.Choice(['top', 'bottom', 'shoes', 'hat', 'accessory', 'fullbody', 'hair']),
              help='服装类别')
@click.option('--gender', '-g', type=click.Choice(['male', 'female', 'neutral']), help='适用性别')
@click.option('--style', '-s', help='风格标签')
@click.option('--dry-run', is_flag=True, help='仅预览')
def import_items(directory, category, gender, style, dry_run):
    """从目录批量导入服装"""
    assets = scan_directory_for_assets(directory)

    if not assets['models']:
        click.echo("未找到模型文件")
        return

    click.echo(f"发现 {len(assets['models'])} 个模型文件")
    click.echo(f"发现 {len(assets['images'])} 个图片文件")

    imported = []
    for model_path in assets['models']:
        model_name = Path(model_path).stem

        textures = []
        preview = None

        for img in assets['images']:
            img_stem = Path(img).stem
            if img_stem == model_name:
                preview = img
            elif model_name in img_stem or img_stem in model_name:
                textures.append(img)

        if dry_run:
            click.echo(
                f"  [预览] {model_name} | 模型: {Path(model_path).name} | "
                f"贴图: {len(textures)} 张 | 预览: {'有' if preview else '无'}"
            )
            continue

        db = AssetDatabase()
        try:
            item_id = db.add_wardrobe_item(
                name=model_name,
                category=category,
                gender=gender,
                style=style,
                model_path=model_path,
                texture_paths=textures if textures else None,
                preview_image=preview
            )
            imported.append((item_id, model_name))
            click.echo(f"[OK] 导入 {model_name} (ID: {item_id})")
        except Exception as e:
            click.echo(f"[ERROR] 导入 {model_name} 失败: {e}", err=True)

    if not dry_run:
        click.echo(f"\n共导入 {len(imported)} 件服装")


@wardrobe.command('create-outfit')
@click.option('--name', '-n', required=True, help='套装名称')
@click.option('--description', '-d', help='套装描述')
@click.option('--style', '-s', help='风格标签')
@click.option('--gender', '-g', type=click.Choice(['male', 'female', 'neutral']), help='适用性别')
@click.option('--item', '-i', 'item_ids', multiple=True, type=int, help='服装单品ID（可多次指定）')
def create_outfit(name, description, style, gender, item_ids):
    """创建服装套装"""
    db = AssetDatabase()

    valid_items = []
    for item_id in item_ids:
        item = db.get_wardrobe_item(item_id)
        if item:
            valid_items.append(item_id)
        else:
            click.echo(f"[WARN]  服装单品 {item_id} 不存在，已跳过")

    if not valid_items and item_ids:
        click.echo("[ERROR] 没有有效的服装单品", err=True)
        return

    try:
        outfit_id = db.create_outfit(
            name=name,
            description=description,
            style=style,
            gender=gender,
            item_ids=valid_items
        )
        click.echo(f"[OK] 成功创建套装: {name} (ID: {outfit_id}, 包含 {len(valid_items)} 件)")
    except Exception as e:
        click.echo(f"[ERROR] 创建失败: {e}", err=True)


@wardrobe.command('list-outfits')
@click.option('--gender', '-g', type=click.Choice(['male', 'female', 'neutral']), help='按性别筛选')
@click.option('--style', '-s', help='按风格筛选')
def list_outfits(gender, style):
    """列出所有套装"""
    db = AssetDatabase()

    with db._get_connection() as conn:
        query = 'SELECT * FROM outfits WHERE 1=1'
        params = []
        if gender:
            query += ' AND gender = ?'
            params.append(gender)
        if style:
            query += ' AND style LIKE ?'
            params.append(f'%{style}%')
        query += ' ORDER BY name'

        rows = conn.execute(query, params).fetchall()
        outfits = [dict(row) for row in rows]

    if not outfits:
        click.echo("未找到套装")
        return

    header = f"{'ID':<6} {'名称':<20} {'性别':<8} {'风格':<12} {'单品数':<8}"
    click.echo(header)
    click.echo("-" * len(header))
    for outfit in outfits:
        items = db.get_outfit_items(outfit['id'])
        click.echo(
            f"{outfit['id']:<6} {outfit['name']:<20} "
            f"{(outfit['gender'] or '-'):<8} {(outfit['style'] or '-'):<12} {len(items):<8}"
        )

    click.echo(f"\n共 {len(outfits)} 个套装")


@wardrobe.command('show-outfit')
@click.argument('outfit_id', type=int)
def show_outfit(outfit_id):
    """显示套装详情"""
    db = AssetDatabase()

    with db._get_connection() as conn:
        row = conn.execute('SELECT * FROM outfits WHERE id = ?', (outfit_id,)).fetchone()
        if not row:
            click.echo(f"[ERROR] 套装 {outfit_id} 不存在", err=True)
            return
        outfit = dict(row)

    items = db.get_outfit_items(outfit_id)

    click.echo(f"\n=== 套装信息 ===")
    click.echo(f"ID: {outfit['id']}")
    click.echo(f"名称: {outfit['name']}")
    click.echo(f"描述: {outfit['description'] or '无'}")
    click.echo(f"性别: {outfit['gender'] or '通用'}")
    click.echo(f"风格: {outfit['style'] or '未设置'}")
    click.echo(f"创建时间: {outfit['created_at']}")

    if items:
        click.echo(f"\n=== 包含单品 ({len(items)} 件) ===")
        for item in items:
            click.echo(
                f"  [{item['id']}] {item['name']} ({item['category']}) "
                f"- 性别: {item['gender'] or '通用'}, 风格: {item['style'] or '未设置'}"
            )


@wardrobe.command('bind-to-avatar')
@click.argument('avatar_id', type=int)
@click.argument('outfit_id', type=int)
def bind_to_avatar(avatar_id, outfit_id):
    """将套装绑定到角色"""
    db = AssetDatabase()

    avatar = db.get_avatar(avatar_id)
    if not avatar:
        click.echo(f"[ERROR] 角色 {avatar_id} 不存在", err=True)
        return

    with db._get_connection() as conn:
        outfit = conn.execute('SELECT * FROM outfits WHERE id = ?', (outfit_id,)).fetchone()
        if not outfit:
            click.echo(f"[ERROR] 套装 {outfit_id} 不存在", err=True)
            return

    db.bind_outfit_to_avatar(avatar_id, outfit_id)
    click.echo(f"[OK] 已将套装 '{outfit['name']}' 绑定到角色 '{avatar['name']}'")


@wardrobe.command('unbind-from-avatar')
@click.argument('avatar_id', type=int)
@click.argument('outfit_id', type=int)
def unbind_from_avatar(avatar_id, outfit_id):
    """解除角色与套装的绑定"""
    db = AssetDatabase()

    avatar = db.get_avatar(avatar_id)
    if not avatar:
        click.echo(f"[ERROR] 角色 {avatar_id} 不存在", err=True)
        return

    try:
        with db._get_connection() as conn:
            conn.execute(
                'DELETE FROM avatar_outfits WHERE avatar_id = ? AND outfit_id = ?',
                (avatar_id, outfit_id)
            )
        click.echo(f"[OK] 已解除绑定")
        db.log_operation('unbind_outfit', 'avatar',
                         {'avatar_id': avatar_id, 'outfit_id': outfit_id})
    except Exception as e:
        click.echo(f"[ERROR] 解除绑定失败: {e}", err=True)


@wardrobe.command('show-item')
@click.argument('item_id', type=int)
def show_item(item_id):
    """显示服装单品详情"""
    db = AssetDatabase()
    item = db.get_wardrobe_item(item_id)
    if not item:
        click.echo(f"[ERROR] 服装单品 {item_id} 不存在", err=True)
        return

    click.echo(f"\n=== 服装单品 ===")
    click.echo(f"ID: {item['id']}")
    click.echo(f"名称: {item['name']}")
    click.echo(f"类别: {item['category']}")
    click.echo(f"性别: {item['gender'] or '通用'}")
    click.echo(f"风格: {item['style'] or '未设置'}")
    click.echo(f"版本: {item['version']}")
    click.echo(f"状态: {item['status']}")
    click.echo(f"模型: {item['model_path'] or '未设置'}")
    click.echo(f"预览: {item['preview_image'] or '未设置'}")

    if item['texture_paths']:
        click.echo(f"\n=== 贴图 ({len(item['texture_paths'])} 张) ===")
        for tex in item['texture_paths']:
            click.echo(f"  - {tex}")

    if item['copyright_source']:
        click.echo(f"\n=== 版权信息 ===")
        click.echo(f"来源: {item['copyright_source']}")

    with db._get_connection() as conn:
        rows = conn.execute(
            '''SELECT o.name, o.id FROM outfits o
               JOIN outfit_items oi ON o.id = oi.outfit_id
               WHERE oi.wardrobe_item_id = ?''',
            (item_id,)
        ).fetchall()
        if rows:
            click.echo(f"\n=== 所属套装 ===")
            for row in rows:
                click.echo(f"  - {row['name']} (ID: {row['id']})")


@wardrobe.command('set-textures')
@click.argument('item_id', type=int)
@click.argument('texture_paths', nargs=-1, type=click.Path(exists=True))
def set_textures(item_id, texture_paths):
    """设置服装单品的贴图"""
    db = AssetDatabase()
    item = db.get_wardrobe_item(item_id)
    if not item:
        click.echo(f"[ERROR] 服装单品 {item_id} 不存在", err=True)
        return

    textures_json = json.dumps(list(texture_paths)) if texture_paths else None

    with db._get_connection() as conn:
        conn.execute(
            'UPDATE wardrobe_items SET texture_paths = ? WHERE id = ?',
            (textures_json, item_id)
        )

    db.log_operation('set_textures', 'wardrobe',
                     {'item_id': item_id, 'texture_count': len(texture_paths)})
    click.echo(f"[OK] 已设置 {len(texture_paths)} 张贴图")


@wardrobe.command('export-outfit')
@click.argument('outfit_id', type=int)
@click.argument('output_path', type=click.Path())
def export_outfit(outfit_id, output_path):
    """导出套装配置为JSON"""
    db = AssetDatabase()

    with db._get_connection() as conn:
        outfit_row = conn.execute('SELECT * FROM outfits WHERE id = ?', (outfit_id,)).fetchone()
        if not outfit_row:
            click.echo(f"[ERROR] 套装 {outfit_id} 不存在", err=True)
            return
        outfit = dict(outfit_row)

    items = db.get_outfit_items(outfit_id)

    export_data = {
        'outfit': outfit,
        'items': items,
        'item_count': len(items),
        'exported_at': None
    }

    if write_json_file(output_path, export_data):
        click.echo(f"[OK] 已导出套装 '{outfit['name']}' 到 {output_path}")
    else:
        click.echo(f"[ERROR] 导出失败", err=True)
