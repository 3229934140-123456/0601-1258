import click
import json
from ..database import AssetDatabase
from ..utils.file_ops import write_json_file


@click.group()
def project():
    """项目工作区管理命令"""
    pass


@project.command('create')
@click.option('--name', '-n', required=True, help='项目名称')
@click.option('--description', '-d', help='项目描述')
@click.option('--customer', '-c', help='客户名称')
def create_project(name, description, customer):
    """创建项目"""
    db = AssetDatabase()
    try:
        project_id = db.create_project(name, description, customer)
        click.echo(f"[OK] 已创建项目 [{project_id}] {name}")
        if customer:
            click.echo(f"   客户: {customer}")
    except Exception as e:
        if 'UNIQUE constraint' in str(e):
            click.echo(f"[ERROR] 项目名称 '{name}' 已存在", err=True)
        else:
            click.echo(f"[ERROR] 创建失败: {e}", err=True)


@project.command('list')
@click.option('--status', help='按状态筛选')
def list_projects(status):
    """列出所有项目"""
    db = AssetDatabase()
    projects = db.list_projects(status=status)

    if not projects:
        click.echo("没有项目记录")
        return

    click.echo(f"\n=== 项目列表 ({len(projects)}) ===")
    for p in projects:
        counts = p.get('asset_counts', {})
        total = sum(counts.values())
        click.echo(f"  [{p['id']}] {p['name']}")
        click.echo(f"      客户: {p.get('customer') or '-'}")
        click.echo(f"      状态: {p['status']}")
        click.echo(f"      资产: {total} (角色:{counts.get('avatar',0)} 服装:{counts.get('wardrobe',0)} 动作:{counts.get('motion',0)} 场景:{counts.get('scene',0)})")
        click.echo(f"      创建: {p['created_at']}")


@project.command('show')
@click.argument('project_id', type=int)
def show_project(project_id):
    """显示项目详情及所含资产"""
    db = AssetDatabase()
    proj = db.get_project(project_id)
    if not proj:
        click.echo(f"[ERROR] 项目 {project_id} 不存在", err=True)
        return

    click.echo(f"\n=== 项目详情 ===")
    click.echo(f"ID: {proj['id']}")
    click.echo(f"名称: {proj['name']}")
    click.echo(f"描述: {proj.get('description') or '-'}")
    click.echo(f"客户: {proj.get('customer') or '-'}")
    click.echo(f"状态: {proj['status']}")
    click.echo(f"创建: {proj['created_at']}")

    assets = db.get_project_assets(project_id)
    click.echo(f"\n--- 角色 ({len(assets['avatars'])}) ---")
    for a in assets['avatars']:
        click.echo(f"  [{a['id']}] {a['name']} ({a.get('gender','?')}/{a.get('style','?')})")
    click.echo(f"\n--- 服装 ({len(assets['wardrobe'])}) ---")
    for w in assets['wardrobe']:
        click.echo(f"  [{w['id']}] {w['name']} ({w['category']})")
    click.echo(f"\n--- 动作 ({len(assets['motions'])}) ---")
    for m in assets['motions']:
        val = '[OK]' if m['validated'] else '[--]'
        click.echo(f"  [{m['id']}] {m['name']} {val}")
    click.echo(f"\n--- 场景 ({len(assets['scenes'])}) ---")
    for s in assets['scenes']:
        click.echo(f"  [{s['id']}] {s['name']}")


@project.command('assign')
@click.argument('project_id', type=int)
@click.option('--avatar', 'avatar_ids', multiple=True, type=int, help='角色ID')
@click.option('--wardrobe', 'wardrobe_ids', multiple=True, type=int, help='服装ID')
@click.option('--motion', 'motion_ids', multiple=True, type=int, help='动作ID')
@click.option('--scene', 'scene_ids', multiple=True, type=int, help='场景ID')
def assign_assets(project_id, avatar_ids, wardrobe_ids, motion_ids, scene_ids):
    """将资产归入项目"""
    db = AssetDatabase()
    proj = db.get_project(project_id)
    if not proj:
        click.echo(f"[ERROR] 项目 {project_id} 不存在", err=True)
        return

    count = 0
    for aid in avatar_ids:
        db.assign_asset_to_project(project_id, 'avatar', aid)
        count += 1
    for wid in wardrobe_ids:
        db.assign_asset_to_project(project_id, 'wardrobe', wid)
        count += 1
    for mid in motion_ids:
        db.assign_asset_to_project(project_id, 'motion', mid)
        count += 1
    for sid in scene_ids:
        db.assign_asset_to_project(project_id, 'scene', sid)
        count += 1

    click.echo(f"[OK] 已将 {count} 个资产归入项目 '{proj['name']}'")


@project.command('unassign')
@click.argument('project_id', type=int)
@click.option('--avatar', 'avatar_ids', multiple=True, type=int, help='角色ID')
@click.option('--wardrobe', 'wardrobe_ids', multiple=True, type=int, help='服装ID')
@click.option('--motion', 'motion_ids', multiple=True, type=int, help='动作ID')
@click.option('--scene', 'scene_ids', multiple=True, type=int, help='场景ID')
def unassign_assets(project_id, avatar_ids, wardrobe_ids, motion_ids, scene_ids):
    """将资产从项目中移除"""
    db = AssetDatabase()
    proj = db.get_project(project_id)
    if not proj:
        click.echo(f"[ERROR] 项目 {project_id} 不存在", err=True)
        return

    count = 0
    for aid in avatar_ids:
        db.unassign_asset_from_project(project_id, 'avatar', aid)
        count += 1
    for wid in wardrobe_ids:
        db.unassign_asset_from_project(project_id, 'wardrobe', wid)
        count += 1
    for mid in motion_ids:
        db.unassign_asset_from_project(project_id, 'motion', mid)
        count += 1
    for sid in scene_ids:
        db.unassign_asset_from_project(project_id, 'scene', sid)
        count += 1

    click.echo(f"[OK] 已从项目 '{proj['name']}' 移除 {count} 个资产")


@project.command('update')
@click.argument('project_id', type=int)
@click.option('--name', help='项目名称')
@click.option('--description', help='项目描述')
@click.option('--customer', help='客户名称')
@click.option('--status', type=click.Choice(['active', 'archived', 'delivered']), help='项目状态')
def update_project(project_id, name, description, customer, status):
    """更新项目信息"""
    db = AssetDatabase()
    updates = {}
    if name:
        updates['name'] = name
    if description:
        updates['description'] = description
    if customer:
        updates['customer'] = customer
    if status:
        updates['status'] = status

    if not updates:
        click.echo("[WARN] 没有指定要更新的字段")
        return

    try:
        db.update_project(project_id, **updates)
        click.echo(f"[OK] 已更新项目信息")
    except ValueError as e:
        click.echo(f"[ERROR] {e}", err=True)


@project.command('export')
@click.argument('project_id', type=int)
@click.argument('output_path', type=click.Path())
def export_project(project_id, output_path):
    """导出项目资产清单为JSON"""
    db = AssetDatabase()
    proj = db.get_project(project_id)
    if not proj:
        click.echo(f"[ERROR] 项目 {project_id} 不存在", err=True)
        return

    assets = db.get_project_assets(project_id)
    data = {
        'project': {
            'id': proj['id'],
            'name': proj['name'],
            'description': proj.get('description'),
            'customer': proj.get('customer'),
            'status': proj['status'],
            'created_at': proj['created_at']
        },
        'assets': assets
    }

    if write_json_file(output_path, data):
        total = sum(len(v) for v in assets.values())
        click.echo(f"[OK] 已导出 {total} 个资产到 {output_path}")
    else:
        click.echo("[ERROR] 导出失败", err=True)
