import os
import click
import json
from typing import List, Dict, Tuple
from pathlib import Path

from ..database import AssetDatabase
from ..utils.file_ops import (
    find_missing_textures, find_duplicate_files,
    get_file_size_mb, write_json_file
)


@click.group()
def check():
    """资产检查与验证命令"""
    pass


@check.command('textures')
@click.option('--type', 'asset_type',
              type=click.Choice(['avatar', 'wardrobe', 'all']),
              default='all', help='资产类型')
@click.option('--fix', is_flag=True, help='自动标记问题')
@click.option('--output', '-o', type=click.Path(), help='输出报告到文件')
def check_textures(asset_type, fix, output):
    """检查缺失贴图"""
    db = AssetDatabase()
    all_issues = []

    if asset_type in ['avatar', 'all']:
        avatars = db.list_avatars()
        click.echo(f"检查 {len(avatars)} 个角色的贴图...")

        for avatar in avatars:
            if avatar['model_path'] and os.path.exists(avatar['model_path']):
                missing = find_missing_textures(avatar['model_path'])
                if missing:
                    issue = {
                        'asset_type': 'avatar',
                        'asset_id': avatar['id'],
                        'asset_name': avatar['name'],
                        'model_path': avatar['model_path'],
                        'missing_textures': missing
                    }
                    all_issues.append(issue)

                    if fix:
                        db.add_issue(
                            asset_type='avatar',
                            asset_id=avatar['id'],
                            issue_type='missing_textures',
                            description=f'缺失 {len(missing)} 张贴图: {", ".join(missing)}',
                            severity='high'
                        )

                    click.echo(f"  [ERROR] {avatar['name']} (ID: {avatar['id']}) - 缺失 {len(missing)} 张贴图")
                    for tex in missing:
                        click.echo(f"     - {tex}")
                else:
                    click.echo(f"  [OK] {avatar['name']}")

    if asset_type in ['wardrobe', 'all']:
        items = db.list_wardrobe_items()
        click.echo(f"\n检查 {len(items)} 件服装的贴图...")

        for item in items:
            if item['model_path'] and os.path.exists(item['model_path']):
                missing = find_missing_textures(item['model_path'])
                if missing:
                    issue = {
                        'asset_type': 'wardrobe',
                        'asset_id': item['id'],
                        'asset_name': item['name'],
                        'model_path': item['model_path'],
                        'missing_textures': missing
                    }
                    all_issues.append(issue)

                    if fix:
                        db.add_issue(
                            asset_type='wardrobe',
                            asset_id=item['id'],
                            issue_type='missing_textures',
                            description=f'缺失 {len(missing)} 张贴图: {", ".join(missing)}',
                            severity='high'
                        )

                    click.echo(f"  [ERROR] {item['name']} (ID: {item['id']}) - 缺失 {len(missing)} 张贴图")
                    for tex in missing:
                        click.echo(f"     - {tex}")
                else:
                    click.echo(f"  [OK] {item['name']}")

    click.echo(f"\n=== 检查完成 ===")
    click.echo(f"共发现 {len(all_issues)} 个贴图缺失问题")

    if output and all_issues:
        report = {
            'check_type': 'missing_textures',
            'total_issues': len(all_issues),
            'issues': all_issues
        }
        if write_json_file(output, report):
            click.echo(f"[OK] 报告已保存到 {output}")


@check.command('duplicates')
@click.option('--type', 'asset_type',
              type=click.Choice(['avatar', 'wardrobe', 'motion', 'all']),
              default='all', help='资产类型')
@click.option('--by-name', is_flag=True, help='按名称查重（数据库）')
@click.option('--by-content', is_flag=True, help='按内容查重（文件哈希）')
@click.option('--dir', 'directory', type=click.Path(exists=True, file_okay=False),
              help='按内容查重的目录')
@click.option('--output', '-o', type=click.Path(), help='输出报告到文件')
def check_duplicates(asset_type, by_name, by_content, directory, output):
    """搜索重复资产"""
    db = AssetDatabase()
    all_duplicates = []

    if by_name or not (by_name or by_content):
        types_to_check = []
        if asset_type in ['avatar', 'all']:
            types_to_check.append('avatar')
        if asset_type in ['wardrobe', 'all']:
            types_to_check.append('wardrobe')
        if asset_type in ['motion', 'all']:
            types_to_check.append('motion')

        for atype in types_to_check:
            click.echo(f"检查 {atype} 名称重复...")
            duplicates = db.find_duplicates(atype)
            if duplicates:
                for group in duplicates:
                    all_duplicates.append({
                        'type': 'name',
                        'asset_type': atype,
                        'items': group
                    })
                    names = [item.get('name', item.get('duplicate_name', '')) for item in group]
                    click.echo(f"  [ERROR] 重复名称: {names[0]}")
                    for item in group:
                        click.echo(f"     - ID: {item['id']}")

    if by_content and directory:
        click.echo(f"\n检查目录内容重复: {directory}")
        dup_files = find_duplicate_files(directory)
        if dup_files:
            for file_hash, files in dup_files.items():
                all_duplicates.append({
                    'type': 'content',
                    'file_hash': file_hash,
                    'files': files
                })
                click.echo(f"  [ERROR] 重复内容 (哈希: {file_hash[:16]}...)")
                for f in files:
                    size = get_file_size_mb(f)
                    click.echo(f"     - {f} ({size:.2f} MB)")

    click.echo(f"\n=== 检查完成 ===")
    click.echo(f"共发现 {len(all_duplicates)} 组重复")

    if output and all_duplicates:
        report = {
            'check_type': 'duplicates',
            'total_groups': len(all_duplicates),
            'duplicates': all_duplicates
        }
        if write_json_file(output, report):
            click.echo(f"[OK] 报告已保存到 {output}")


@check.command('versions')
@click.argument('asset_type', type=click.Choice(['avatar', 'wardrobe', 'motion', 'scene']))
@click.argument('asset_id', type=int)
@click.option('--compare-with', type=int, help='比较的版本ID（未指定则比较相邻版本）')
def compare_versions(asset_type, asset_id, compare_with):
    """比较版本差异"""
    db = AssetDatabase()
    history = db.get_version_history(asset_type, asset_id)

    if not history:
        click.echo("暂无版本历史")
        return

    click.echo(f"\n=== {asset_type} #{asset_id} 版本历史 ===")
    for i, v in enumerate(history):
        click.echo(f"  [ID:{v['id']}] v{v['version']} - {v['changes']} ({v['created_at']})")

    if len(history) < 2:
        click.echo("\n只有1个版本，无需比较")
        return

    if compare_with is not None and compare_with < len(history):
        v1 = history[0]
        v2 = history[compare_with]
        click.echo(f"\n=== 比较 v{v1['version']} 与 v{v2['version']} ===")
        click.echo(f"v{v1['version']}: {v1['changes']}")
        click.echo(f"v{v2['version']}: {v2['changes']}")
        click.echo(f"时间差: {v1['created_at']} -> {v2['created_at']}")
    else:
        if len(history) >= 2:
            v1 = history[0]
            v2 = history[1]
            click.echo(f"\n=== 比较最新两个版本 ===")
            click.echo(f"v{v1['version']}: {v1['changes']}")
            click.echo(f"v{v2['version']}: {v2['changes']}")


@check.command('rollback')
@click.argument('asset_type', type=click.Choice(['avatar', 'wardrobe', 'motion', 'scene']))
@click.argument('asset_id', type=int)
@click.argument('version_id', type=int)
def rollback_version(asset_type, asset_id, version_id):
    """恢复到指定版本"""
    db = AssetDatabase()

    history = db.get_version_history(asset_type, asset_id)
    target = None
    for v in history:
        if v['id'] == version_id:
            target = v
            break

    if not target:
        click.echo(f"[ERROR] 版本记录 {version_id} 不存在", err=True)
        return

    if target['asset_type'] != asset_type or target['asset_id'] != asset_id:
        click.echo(f"[ERROR] 版本 {version_id} 不属于该资产", err=True)
        return

    click.echo(f"即将回滚 {asset_type} #{asset_id} 到 v{target['version']}")
    click.echo(f"  版本描述: {target['changes']}")
    click.echo(f"  版本时间: {target['created_at']}")

    if not click.confirm("确认回滚？"):
        return

    if db.rollback_to_version(asset_type, asset_id, version_id):
        click.echo(f"[OK] 已回滚到 v{target['version']}")
    else:
        click.echo(f"[ERROR] 回滚失败", err=True)


@check.command('export-versions')
@click.argument('asset_type', type=click.Choice(['avatar', 'wardrobe', 'motion', 'scene']))
@click.argument('asset_id', type=int)
@click.argument('output_path', type=click.Path())
def export_versions(asset_type, asset_id, output_path):
    """导出版本变化记录为JSON"""
    db = AssetDatabase()
    history = db.get_version_history(asset_type, asset_id)

    if not history:
        click.echo("暂无版本历史")
        return

    data = {
        'asset_type': asset_type,
        'asset_id': asset_id,
        'total_versions': len(history),
        'versions': []
    }

    for i, v in enumerate(history):
        entry = {
            'id': v['id'],
            'version': v['version'],
            'changes': v['changes'],
            'created_at': v['created_at']
        }
        if i < len(history) - 1:
            prev = history[i + 1]
            entry['diff_from_previous'] = {
                'from_version': prev['version'],
                'from_changes': prev['changes'],
                'to_version': v['version'],
                'to_changes': v['changes']
            }
        data['versions'].append(entry)

    if write_json_file(output_path, data):
        click.echo(f"[OK] 版本记录已导出到 {output_path}")
        click.echo(f"   共 {len(history)} 个版本")
    else:
        click.echo("[ERROR] 导出失败", err=True)


@check.command('mark-issue')
@click.argument('asset_type', type=click.Choice(['avatar', 'wardrobe', 'motion', 'scene']))
@click.argument('asset_id', type=int)
@click.option('--issue-type', required=True,
              type=click.Choice(['missing_textures', 'invalid_model', 'invalid_motion',
                                 'bad_uv', 'high_poly', 'naming_issue', 'other']),
              help='问题类型')
@click.option('--description', help='问题描述')
@click.option('--severity', type=click.Choice(['low', 'medium', 'high', 'critical']),
              default='medium', help='严重程度')
def mark_issue(asset_type, asset_id, issue_type, description, severity):
    """标记待修复项"""
    db = AssetDatabase()

    asset_name = None
    if asset_type == 'avatar':
        avatar = db.get_avatar(asset_id)
        if avatar:
            asset_name = avatar['name']
    elif asset_type == 'wardrobe':
        item = db.get_wardrobe_item(asset_id)
        if item:
            asset_name = item['name']
    elif asset_type == 'motion':
        motion = db.get_motion(asset_id)
        if motion:
            asset_name = motion['name']
    elif asset_type == 'scene':
        scene = db.get_scene(asset_id)
        if scene:
            asset_name = scene['name']

    if not asset_name:
        click.echo(f"[ERROR] {asset_type} {asset_id} 不存在", err=True)
        return

    issue_id = db.add_issue(
        asset_type=asset_type,
        asset_id=asset_id,
        issue_type=issue_type,
        description=description,
        severity=severity
    )

    click.echo(f"[OK] 已标记问题 (ID: {issue_id})")
    click.echo(f"   资产: {asset_name} ({asset_type} #{asset_id})")
    click.echo(f"   类型: {issue_type}")
    click.echo(f"   严重: {severity}")
    if description:
        click.echo(f"   描述: {description}")


@check.command('list-issues')
@click.option('--type', 'asset_type',
              type=click.Choice(['avatar', 'wardrobe', 'motion', 'scene', 'all']),
              default='all', help='资产类型')
@click.option('--severity', type=click.Choice(['low', 'medium', 'high', 'critical', 'all']),
              default='all', help='严重程度')
@click.option('--fixed', is_flag=True, help='显示已修复的')
def list_issues(asset_type, severity, fixed):
    """列出待修复项"""
    db = AssetDatabase()

    atype = None if asset_type == 'all' else asset_type
    sev = None if severity == 'all' else severity

    issues = db.list_issues(asset_type=atype, fixed=fixed, severity=sev)

    if not issues:
        click.echo("没有问题记录")
        return

    status_str = '已修复' if fixed else '待修复'
    click.echo(f"\n=== {status_str}问题列表 ({len(issues)} 条) ===")

    severity_symbols = {'low': '[LOW]', 'medium': '[MED]', 'high': '[HIGH]', 'critical': '[CRIT]'}
    severity_colors = {'low': 'white', 'medium': 'yellow', 'high': 'red', 'critical': 'bright_red'}

    for issue in issues:
        sym = severity_symbols.get(issue['severity'], '[INFO]')
        click.echo(
            f"  [{issue['id']}] {sym} [{issue['severity']}] {issue['asset_type']} "
            f"#{issue['asset_id']} - {issue['issue_type']}"
        )
        if issue['description']:
            click.echo(f"      {issue['description']}")
        click.echo(f"      创建: {issue['created_at']}")
        if issue['fixed_at']:
            click.echo(f"      修复: {issue['fixed_at']}")

    counts = {}
    for issue in issues:
        sev = issue['severity']
        counts[sev] = counts.get(sev, 0) + 1

    click.echo(f"\n=== 统计 ===")
    for sev in ['critical', 'high', 'medium', 'low']:
        if sev in counts:
            click.echo(f"  {sev}: {counts[sev]}")


@check.command('fix-issue')
@click.argument('issue_id', type=int)
def fix_issue(issue_id):
    """标记问题为已修复"""
    db = AssetDatabase()

    issues = db.list_issues(fixed=False)
    issue = next((i for i in issues if i['id'] == issue_id), None)

    if not issue:
        issues_all = db.list_issues(fixed=True)
        issue = next((i for i in issues_all if i['id'] == issue_id), None)
        if issue:
            click.echo(f"[WARN]  问题 {issue_id} 已经修复")
            return
        click.echo(f"[ERROR] 问题 {issue_id} 不存在", err=True)
        return

    db.fix_issue(issue_id)
    click.echo(f"[OK] 已标记问题 {issue_id} 为已修复")
    click.echo(f"   {issue['asset_type']} #{issue['asset_id']} - {issue['issue_type']}")


@check.command('integrity')
@click.option('--auto-fix', is_flag=True, help='自动标记发现的问题')
def check_integrity(auto_fix):
    """检查资产完整性（文件存在性）"""
    db = AssetDatabase()
    issues = []

    click.echo("检查角色资产完整性...")
    avatars = db.list_avatars()
    for avatar in avatars:
        avatar_issues = []
        if avatar['model_path'] and not os.path.exists(avatar['model_path']):
            avatar_issues.append(f'模型文件不存在: {avatar["model_path"]}')
        if avatar['preview_image'] and not os.path.exists(avatar['preview_image']):
            avatar_issues.append(f'预览图不存在: {avatar["preview_image"]}')

        if avatar_issues:
            issues.append({
                'asset_type': 'avatar',
                'asset_id': avatar['id'],
                'asset_name': avatar['name'],
                'problems': avatar_issues
            })
            if auto_fix:
                for problem in avatar_issues:
                    db.add_issue(
                        asset_type='avatar',
                        asset_id=avatar['id'],
                        issue_type='missing_file',
                        description=problem,
                        severity='high'
                    )
            click.echo(f"  [ERROR] {avatar['name']}:")
            for p in avatar_issues:
                click.echo(f"     - {p}")

    click.echo("\n检查服装资产完整性...")
    items = db.list_wardrobe_items()
    for item in items:
        item_issues = []
        if item['model_path'] and not os.path.exists(item['model_path']):
            item_issues.append(f'模型文件不存在: {item["model_path"]}')
        if item['preview_image'] and not os.path.exists(item['preview_image']):
            item_issues.append(f'预览图不存在: {item["preview_image"]}')
        if item['texture_paths']:
            for tex in item['texture_paths']:
                if not os.path.exists(tex):
                    item_issues.append(f'贴图不存在: {tex}')

        if item_issues:
            issues.append({
                'asset_type': 'wardrobe',
                'asset_id': item['id'],
                'asset_name': item['name'],
                'problems': item_issues
            })
            if auto_fix:
                for problem in item_issues:
                    db.add_issue(
                        asset_type='wardrobe',
                        asset_id=item['id'],
                        issue_type='missing_file',
                        description=problem,
                        severity='high'
                    )
            click.echo(f"  [ERROR] {item['name']}:")
            for p in item_issues:
                click.echo(f"     - {p}")

    click.echo("\n检查动作资产完整性...")
    motions = db.list_motions()
    for motion in motions:
        if motion['file_path'] and not os.path.exists(motion['file_path']):
            issues.append({
                'asset_type': 'motion',
                'asset_id': motion['id'],
                'asset_name': motion['name'],
                'problems': [f'动作文件不存在: {motion["file_path"]}']
            })
            if auto_fix:
                db.add_issue(
                    asset_type='motion',
                    asset_id=motion['id'],
                    issue_type='missing_file',
                    description=f'动作文件不存在: {motion["file_path"]}',
                    severity='high'
                )
            click.echo(f"  [ERROR] {motion['name']}: 动作文件不存在")

    click.echo(f"\n=== 检查完成 ===")
    click.echo(f"共发现 {len(issues)} 个完整性问题")
