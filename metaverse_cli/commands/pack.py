import os
import shutil
import zipfile
import click
import json
from datetime import datetime
from pathlib import Path

from ..database import AssetDatabase
from ..utils.file_ops import (
    ensure_directory, copy_assets_to_delivery,
    write_json_file, safe_copy_file, get_file_size_mb
)
from ..utils.image_ops import (
    generate_thumbnail, generate_multiple_thumbnails,
    THUMBNAIL_SIZES, is_pil_available
)
from ..utils.undo import UndoManager


@click.group()
def pack():
    """打包与交付命令"""
    pass


@pack.command('thumbnails')
@click.option('--type', 'asset_type',
              type=click.Choice(['avatar', 'wardrobe', 'motion', 'scene', 'all']),
              default='all', help='资产类型')
@click.option('--size', 'sizes', multiple=True,
              type=click.Choice(['icon', 'small', 'medium', 'large', 'xlarge', 'all']),
              default=['medium'], help='缩略图尺寸')
@click.option('--output-dir', default='./thumbnails', help='输出目录')
@click.option('--force', is_flag=True, help='覆盖已存在的缩略图')
def generate_thumbnails_cmd(asset_type, sizes, output_dir, force):
    """生成缩略图"""
    if not is_pil_available():
        click.echo("[ERROR] Pillow 库未安装，无法生成缩略图")
        click.echo("   请运行: pip install Pillow")
        return

    db = AssetDatabase()
    ensure_directory(output_dir)

    all_assets = []
    if asset_type in ['avatar', 'all']:
        all_assets.extend([('avatar', a) for a in db.list_avatars()])
    if asset_type in ['wardrobe', 'all']:
        all_assets.extend([('wardrobe', w) for w in db.list_wardrobe_items()])
    if asset_type in ['scene', 'all']:
        all_assets.extend([('scene', s) for s in db.list_scenes()])

    if not all_assets:
        click.echo("没有可生成缩略图的资产")
        return

    target_sizes = {}
    if 'all' in sizes:
        target_sizes = THUMBNAIL_SIZES
    else:
        for s in sizes:
            if s in THUMBNAIL_SIZES:
                target_sizes[s] = THUMBNAIL_SIZES[s]

    click.echo(f"将为 {len(all_assets)} 个资产生成 {len(target_sizes)} 种尺寸的缩略图")
    click.echo(f"尺寸: {', '.join(target_sizes.keys())}")

    generated = 0
    failed = 0
    skipped = 0

    with click.progressbar(all_assets, label='生成中') as bar:
        for atype, asset in bar:
            preview_image = asset.get('preview_image')
            if not preview_image or not os.path.exists(preview_image):
                skipped += 1
                continue

            asset_dir = os.path.join(output_dir, atype, str(asset['id']))
            ensure_directory(asset_dir)

            for size_name, size_dim in target_sizes.items():
                out_path = os.path.join(
                    asset_dir,
                    f"{asset['name']}_{size_name}.png"
                )

                if os.path.exists(out_path) and not force:
                    continue

                if generate_thumbnail(preview_image, out_path, size_dim):
                    db.save_thumbnail(atype, asset['id'], out_path, size_name)
                    generated += 1
                else:
                    failed += 1

    click.echo(f"\n=== 完成 ===")
    click.echo(f"生成成功: {generated}")
    click.echo(f"生成失败: {failed}")
    click.echo(f"跳过(无预览图): {skipped}")


@pack.command('delivery')
@click.option('--customer', required=True, help='客户名称')
@click.option('--project', help='项目名称')
@click.option('--avatar', 'avatar_ids', multiple=True, type=int, help='角色ID（可多次指定）')
@click.option('--wardrobe', 'wardrobe_ids', multiple=True, type=int, help='服装ID（可多次指定）')
@click.option('--motion', 'motion_ids', multiple=True, type=int, help='动作ID（可多次指定）')
@click.option('--scene', 'scene_ids', multiple=True, type=int, help='场景ID（可多次指定）')
@click.option('--output-dir', default='./deliveries', help='输出根目录')
@click.option('--zip', 'create_zip', is_flag=True, help='打包为ZIP文件')
@click.option('--generate-thumbs', is_flag=True, help='生成缩略图')
def create_delivery(customer, project, avatar_ids, wardrobe_ids, motion_ids,
                    scene_ids, output_dir, create_zip, generate_thumbs):
    """打包交付目录"""
    db = AssetDatabase()

    items = []
    for aid in avatar_ids:
        items.append(('avatar', aid))
    for wid in wardrobe_ids:
        items.append(('wardrobe', wid))
    for mid in motion_ids:
        items.append(('motion', mid))
    for sid in scene_ids:
        items.append(('scene', sid))

    if not items:
        click.echo("[ERROR] 请至少指定一个要交付的资产", err=True)
        return

    delivery_id = db.create_delivery(
        customer_name=customer,
        project_name=project,
        items=items
    )

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_customer = "".join(c for c in customer if c.isalnum() or c in (' ', '_', '-')).strip()
    delivery_dir_name = f"{safe_customer}_{project or 'delivery'}_{timestamp}".replace(' ', '_')
    delivery_dir = os.path.join(output_dir, delivery_dir_name)

    ensure_directory(delivery_dir)

    click.echo(f"创建交付包 #{delivery_id}")
    click.echo(f"输出目录: {delivery_dir}")

    all_assets = []
    avatars_dir = os.path.join(delivery_dir, 'avatars')
    wardrobe_dir = os.path.join(delivery_dir, 'wardrobe')
    motions_dir = os.path.join(delivery_dir, 'motions')
    scenes_dir = os.path.join(delivery_dir, 'scenes')

    for atype, aid in items:
        if atype == 'avatar':
            asset = db.get_avatar(aid)
            if asset:
                all_assets.append(('avatar', asset, avatars_dir))
        elif atype == 'wardrobe':
            asset = db.get_wardrobe_item(aid)
            if asset:
                all_assets.append(('wardrobe', asset, wardrobe_dir))
        elif atype == 'motion':
            asset = db.get_motion(aid)
            if asset:
                all_assets.append(('motion', asset, motions_dir))
        elif atype == 'scene':
            asset = db.get_scene(aid)
            if asset:
                all_assets.append(('scene', asset, scenes_dir))

    total_copied = 0
    total_failed = 0

    for atype, asset, target_dir in all_assets:
        ensure_directory(target_dir)
        copied, failed = copy_assets_to_delivery([asset], target_dir)
        total_copied += len(copied)
        total_failed += len(failed)

    if generate_thumbs and is_pil_available():
        click.echo("\n生成缩略图...")
        thumbs_dir = os.path.join(delivery_dir, 'thumbnails')
        ensure_directory(thumbs_dir)

        for atype, asset, target_dir in all_assets:
            preview = asset.get('preview_image')
            if preview and os.path.exists(preview):
                thumb_path = os.path.join(
                    thumbs_dir,
                    f"{atype}_{asset['id']}_preview.png"
                )
                if generate_thumbnail(preview, thumb_path, (256, 256)):
                    click.echo(f"  [OK] {asset['name']}")

    manifest = db.get_delivery(delivery_id)
    if manifest and manifest.get('manifest'):
        manifest_path = os.path.join(delivery_dir, 'manifest.json')
        write_json_file(manifest_path, manifest['manifest'])
        click.echo(f"\n清单文件: {manifest_path}")

    readme_content = _generate_delivery_readme(customer, project, all_assets, timestamp)
    readme_path = os.path.join(delivery_dir, 'README.txt')
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)

    with db._get_connection() as conn:
        conn.execute(
            'UPDATE deliveries SET delivery_date = CURRENT_TIMESTAMP, status = ? WHERE id = ?',
            ('delivered', delivery_id)
        )

    click.echo(f"\n=== 交付完成 ===")
    click.echo(f"复制文件: {total_copied}")
    if total_failed:
        click.echo(f"复制失败: {total_failed}")

    if create_zip:
        zip_path = f"{delivery_dir}.zip"
        click.echo(f"\n创建ZIP包: {zip_path}")

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(delivery_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, delivery_dir)
                    zf.write(file_path, arcname)

        zip_size = get_file_size_mb(zip_path)
        click.echo(f"ZIP包大小: {zip_size:.2f} MB")

    db.log_operation('create_delivery', None, {
        'delivery_id': delivery_id,
        'customer': customer,
        'asset_count': len(all_assets)
    })

    click.echo(f"\n交付ID: {delivery_id}")
    return delivery_id


@pack.command('list-deliveries')
@click.option('--customer', help='按客户筛选')
def list_deliveries(customer):
    """列出所有交付记录"""
    db = AssetDatabase()
    deliveries = db.list_deliveries(customer_name=customer)

    if not deliveries:
        click.echo("没有交付记录")
        return

    header = f"{'ID':<6} {'客户':<20} {'项目':<20} {'日期':<20} {'状态':<10}"
    click.echo(header)
    click.echo("-" * len(header))

    for d in deliveries:
        date = d['delivery_date'] or d['created_at']
        click.echo(
            f"{d['id']:<6} {d['customer_name']:<20} "
            f"{(d['project_name'] or '-'):<20} {date:<20} {d['status']:<10}"
        )

    click.echo(f"\n共 {len(deliveries)} 条交付记录")


@pack.command('show-delivery')
@click.argument('delivery_id', type=int)
def show_delivery(delivery_id):
    """显示交付详情"""
    db = AssetDatabase()
    delivery = db.get_delivery(delivery_id)

    if not delivery:
        click.echo(f"[ERROR] 交付 {delivery_id} 不存在", err=True)
        return

    click.echo(f"\n=== 交付信息 ===")
    click.echo(f"ID: {delivery['id']}")
    click.echo(f"客户: {delivery['customer_name']}")
    click.echo(f"项目: {delivery['project_name'] or '未设置'}")
    click.echo(f"状态: {delivery['status']}")
    click.echo(f"创建时间: {delivery['created_at']}")
    if delivery['delivery_date']:
        click.echo(f"交付时间: {delivery['delivery_date']}")

    if delivery.get('manifest'):
        manifest = delivery['manifest']
        click.echo(f"\n=== 交付内容 ===")
        if manifest.get('avatars'):
            click.echo(f"角色 ({len(manifest['avatars'])}):")
            for a in manifest['avatars']:
                click.echo(f"  - [{a['id']}] {a['name']}")
        if manifest.get('wardrobe'):
            click.echo(f"服装 ({len(manifest['wardrobe'])}):")
            for w in manifest['wardrobe']:
                click.echo(f"  - [{w['id']}] {w['name']} ({w['category']})")
        if manifest.get('motions'):
            click.echo(f"动作 ({len(manifest['motions'])}):")
            for m in manifest['motions']:
                click.echo(f"  - [{m['id']}] {m['name']}")
        if manifest.get('scenes'):
            click.echo(f"场景 ({len(manifest['scenes'])}):")
            for s in manifest['scenes']:
                click.echo(f"  - [{s['id']}] {s['name']}")


@pack.command('undo')
def undo_last():
    """撤销上一次批处理"""
    db = AssetDatabase()
    undo_manager = UndoManager(db)

    last_op = undo_manager.get_last_operation_info()
    if not last_op:
        click.echo("没有可撤销的操作")
        return

    click.echo(f"上一次操作: {last_op['operation']}")
    if last_op.get('details'):
        click.echo(f"详情: {json.dumps(last_op['details'], ensure_ascii=False)}")
    click.echo(f"时间: {last_op['timestamp']}")

    if not click.confirm("确认撤销此操作？"):
        return

    success, message = undo_manager.undo_last()
    if success:
        click.echo(f"[OK] {message}")
    else:
        click.echo(f"[ERROR] {message}", err=True)


@pack.command('backup-db')
@click.option('--output-dir', default='./backups', help='备份输出目录')
def backup_database(output_dir):
    """备份数据库"""
    db = AssetDatabase()
    ensure_directory(output_dir)

    backup_base = os.path.join(output_dir, 'metaverse_backup')
    backup_path = db.backup_database(backup_base)

    size = get_file_size_mb(backup_path)
    click.echo(f"[OK] 数据库已备份")
    click.echo(f"   路径: {backup_path}")
    click.echo(f"   大小: {size:.2f} MB")


def _generate_delivery_readme(customer, project, assets, timestamp):
    lines = []
    lines.append("=" * 60)
    lines.append("元宇宙资产交付清单")
    lines.append("=" * 60)
    lines.append(f"")
    lines.append(f"客户: {customer}")
    if project:
        lines.append(f"项目: {project}")
    lines.append(f"交付时间: {timestamp}")
    lines.append(f"")
    lines.append("-" * 60)
    lines.append("交付内容:")
    lines.append("-" * 60)

    asset_counts = {}
    for atype, asset, _ in assets:
        if atype not in asset_counts:
            asset_counts[atype] = []
        asset_counts[atype].append(asset)

    type_names = {
        'avatar': '角色',
        'wardrobe': '服装',
        'motion': '动作',
        'scene': '场景'
    }

    for atype, type_name in type_names.items():
        if atype in asset_counts:
            lines.append(f"")
            lines.append(f"{type_name} ({len(asset_counts[atype])}):")
            for asset in asset_counts[atype]:
                line = f"  [{asset['id']}] {asset['name']}"
                if asset.get('version'):
                    line += f" (v{asset['version']})"
                lines.append(line)

    lines.append(f"")
    lines.append("-" * 60)
    lines.append("文件结构:")
    lines.append("-" * 60)
    lines.append(f"avatars/      - 角色模型和预览图")
    lines.append(f"wardrobe/     - 服装模型和贴图")
    lines.append(f"motions/      - 动作文件")
    lines.append(f"scenes/       - 场景文件")
    if is_pil_available():
        lines.append(f"thumbnails/   - 缩略图")
    lines.append(f"manifest.json - 详细清单（JSON格式）")
    lines.append(f"README.txt    - 本文件")
    lines.append(f"")
    lines.append("=" * 60)

    return '\n'.join(lines)
