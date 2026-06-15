import os
import click
from pathlib import Path

from ..database import AssetDatabase
from ..utils.file_ops import (
    find_files_by_extension, validate_motion_file,
    write_json_file, is_motion_file, SUPPORTED_MOTION_EXTENSIONS
)


@click.group()
def motion():
    """动作文件管理命令"""
    pass


@motion.command('add')
@click.option('--name', '-n', required=True, help='动作名称')
@click.option('--file', '-f', 'file_path', required=True, type=click.Path(exists=True),
              help='动作文件路径')
@click.option('--category', '-c', help='动作类别，如：行走、跑步、攻击等')
@click.option('--target-rig', help='目标骨骼，如：Humanoid、Custom等')
@click.option('--duration', type=float, help='动作时长（秒）')
@click.option('--frames', 'frame_count', type=int, help='帧数')
@click.option('--fps', type=int, help='帧率')
@click.option('--copyright', 'copyright_source', help='版权来源')
@click.option('--project', 'project_id', type=int, help='所属项目ID')
def add_motion(name, file_path, category, target_rig, duration, frame_count, fps, copyright_source, project_id):
    """添加动作文件"""
    db = AssetDatabase()

    validation = validate_motion_file(file_path)
    if not validation['valid']:
        click.echo("[WARN]  动作文件验证警告:")
        for error in validation['errors']:
            click.echo(f"   - {error}")
        if not click.confirm("是否继续添加？"):
            return

    duration = duration or validation['info'].get('duration')
    frame_count = frame_count or validation['info'].get('frame_count')
    fps = fps or validation['info'].get('fps')

    try:
        motion_id = db.add_motion(
            name=name,
            file_path=file_path,
            category=category,
            duration=duration,
            frame_count=frame_count,
            fps=fps,
            target_rig=target_rig,
            project_id=project_id
        )

        if copyright_source:
            with db._get_connection() as conn:
                conn.execute(
                    'UPDATE motions SET copyright_source = ? WHERE id = ?',
                    (copyright_source, motion_id)
                )

        click.echo(f"[OK] 成功添加动作: {name} (ID: {motion_id})")
    except Exception as e:
        click.echo(f"[ERROR] 添加失败: {e}", err=True)


@motion.command('list')
@click.option('--category', '-c', help='按类别筛选')
@click.option('--validated', type=click.Choice(['yes', 'no', 'all']), default='all',
              help='按验证状态筛选')
@click.option('--project', 'project_id', type=int, help='按项目筛选')
@click.option('--format', '-f', 'output_format', type=click.Choice(['table', 'json']),
              default='table', help='输出格式')
def list_motions(category, validated, project_id, output_format):
    """列出动作文件"""
    db = AssetDatabase()

    validated_flag = None
    if validated == 'yes':
        validated_flag = True
    elif validated == 'no':
        validated_flag = False

    motions = db.list_motions(category=category, validated=validated_flag, project_id=project_id)

    if not motions:
        click.echo("未找到动作文件")
        return

    if output_format == 'table':
        header = f"{'ID':<6} {'名称':<20} {'类别':<12} {'时长':<8} {'帧率':<6} {'验证':<6}"
        click.echo(header)
        click.echo("-" * len(header))
        for m in motions:
            duration = f"{m['duration']:.1f}s" if m['duration'] else '-'
            fps = m['fps'] or '-'
            validated_str = '[OK]' if m['validated'] else '[ERROR]'
            click.echo(
                f"{m['id']:<6} {m['name']:<20} {(m['category'] or '-'):<12} "
                f"{duration:<8} {fps:<6} {validated_str:<6}"
            )
    else:
        import json
        click.echo(json.dumps({'count': len(motions), 'motions': motions},
                              indent=2, ensure_ascii=False))

    click.echo(f"\n共 {len(motions)} 个动作")


@motion.command('import')
@click.argument('directory', type=click.Path(exists=True, file_okay=False))
@click.option('--category', '-c', help='动作类别')
@click.option('--target-rig', help='目标骨骼')
@click.option('--auto-validate', is_flag=True, help='导入后自动验证')
@click.option('--dry-run', is_flag=True, help='仅预览')
def import_motions(directory, category, target_rig, auto_validate, dry_run):
    """从目录批量导入动作"""
    motion_files = find_files_by_extension(directory, SUPPORTED_MOTION_EXTENSIONS)

    if not motion_files:
        click.echo("未找到动作文件")
        click.echo(f"支持的格式: {', '.join(sorted(SUPPORTED_MOTION_EXTENSIONS))}")
        return

    click.echo(f"发现 {len(motion_files)} 个动作文件")

    imported = []
    for motion_path in motion_files:
        motion_name = Path(motion_path).stem

        if dry_run:
            click.echo(f"  [预览] {motion_name} | 文件: {Path(motion_path).name}")
            continue

        db = AssetDatabase()
        try:
            validation = validate_motion_file(motion_path)
            motion_id = db.add_motion(
                name=motion_name,
                file_path=motion_path,
                category=category,
                target_rig=target_rig,
                duration=validation['info'].get('duration'),
                frame_count=validation['info'].get('frame_count'),
                fps=validation['info'].get('fps')
            )

            if auto_validate:
                db.validate_motion(motion_id, validation['valid'],
                                   '; '.join(validation['errors']))

            imported.append((motion_id, motion_name, validation['valid']))
            status = '[OK]' if validation['valid'] else '[ERROR]'
            click.echo(f"[OK] {status} 导入 {motion_name} (ID: {motion_id})")
        except Exception as e:
            click.echo(f"[ERROR] 导入 {motion_name} 失败: {e}", err=True)

    if not dry_run:
        valid_count = sum(1 for _, _, valid in imported if valid)
        click.echo(f"\n共导入 {len(imported)} 个动作，{valid_count} 个验证通过")


@motion.command('validate')
@click.argument('motion_id', type=int)
@click.option('--notes', help='验证备注')
def validate_motion(motion_id, notes):
    """验证动作文件"""
    db = AssetDatabase()
    motion = db.get_motion(motion_id)
    if not motion:
        click.echo(f"[ERROR] 动作 {motion_id} 不存在", err=True)
        return

    click.echo(f"正在验证: {motion['name']}")
    click.echo(f"文件: {motion['file_path']}")

    validation = validate_motion_file(motion['file_path'])

    click.echo(f"\n=== 验证结果 ===")
    click.echo(f"有效: {'[OK]' if validation['valid'] else '[ERROR]'}")

    if validation['info']:
        click.echo("\n=== 文件信息 ===")
        for key, value in validation['info'].items():
            click.echo(f"  {key}: {value}")

    if validation['errors']:
        click.echo("\n=== 错误 ===")
        for error in validation['errors']:
            click.echo(f"  [ERROR] {error}")

    if validation['warnings']:
        click.echo("\n=== 警告 ===")
        for warning in validation['warnings']:
            click.echo(f"  [WARN]  {warning}")

    if notes is None:
        notes = '; '.join(validation['errors']) if validation['errors'] else None

    db.validate_motion(motion_id, validation['valid'], notes)
    click.echo(f"\n[OK] 已更新验证状态")


@motion.command('validate-all')
@click.option('--category', '-c', help='仅验证指定类别')
@click.option('--only-unvalidated', is_flag=True, help='仅验证未验证的')
def validate_all(category, only_unvalidated):
    """批量验证所有动作文件"""
    db = AssetDatabase()

    validated_flag = False if only_unvalidated else None
    motions = db.list_motions(category=category, validated=validated_flag)

    if not motions:
        click.echo("没有需要验证的动作")
        return

    click.echo(f"将验证 {len(motions)} 个动作文件\n")

    results = []
    with click.progressbar(motions, label='验证中') as bar:
        for motion in bar:
            validation = validate_motion_file(motion['file_path'])
            notes = '; '.join(validation['errors']) if validation['errors'] else None
            db.validate_motion(motion['id'], validation['valid'], notes)
            results.append((motion['id'], motion['name'], validation['valid']))

    valid_count = sum(1 for _, _, valid in results if valid)
    invalid_count = len(results) - valid_count

    click.echo(f"\n=== 验证完成 ===")
    click.echo(f"总计: {len(results)}")
    click.echo(f"通过: {valid_count}")
    click.echo(f"失败: {invalid_count}")

    if invalid_count > 0:
        click.echo("\n失败的动作:")
        for mid, name, valid in results:
            if not valid:
                click.echo(f"  [{mid}] {name}")


@motion.command('show')
@click.argument('motion_id', type=int)
def show_motion(motion_id):
    """显示动作详情"""
    db = AssetDatabase()
    motion = db.get_motion(motion_id)
    if not motion:
        click.echo(f"[ERROR] 动作 {motion_id} 不存在", err=True)
        return

    click.echo(f"\n=== 动作信息 ===")
    click.echo(f"ID: {motion['id']}")
    click.echo(f"名称: {motion['name']}")
    click.echo(f"类别: {motion['category'] or '未设置'}")
    click.echo(f"文件: {motion['file_path']}")
    click.echo(f"目标骨骼: {motion['target_rig'] or '未设置'}")
    click.echo(f"时长: {motion['duration'] or '未知'} 秒")
    click.echo(f"帧数: {motion['frame_count'] or '未知'}")
    click.echo(f"帧率: {motion['fps'] or '未知'}")
    click.echo(f"版本: {motion['version']}")
    click.echo(f"状态: {motion['status']}")
    click.echo(f"已验证: {'[OK]' if motion['validated'] else '[ERROR]'}")
    click.echo(f"创建时间: {motion['created_at']}")

    if motion['copyright_source']:
        click.echo(f"\n=== 版权信息 ===")
        click.echo(f"来源: {motion['copyright_source']}")

    version_history = db.get_version_history('motion', motion_id)
    if version_history:
        click.echo(f"\n=== 版本历史 ===")
        for v in version_history:
            click.echo(f"  v{v['version']} - {v['changes']} ({v['created_at']})")


@motion.command('export')
@click.argument('output_path', type=click.Path())
@click.option('--category', '-c', help='按类别筛选')
@click.option('--only-valid', is_flag=True, help='仅导出已验证的')
def export_motions(output_path, category, only_valid):
    """导出动作清单为JSON"""
    db = AssetDatabase()

    validated_flag = True if only_valid else None
    motions = db.list_motions(category=category, validated=validated_flag)

    if not motions:
        click.echo("未找到动作")
        return

    export_data = {
        'count': len(motions),
        'category_filter': category,
        'only_validated': only_valid,
        'motions': motions
    }

    if write_json_file(output_path, export_data):
        click.echo(f"[OK] 已导出 {len(motions)} 个动作到 {output_path}")
    else:
        click.echo(f"[ERROR] 导出失败", err=True)
