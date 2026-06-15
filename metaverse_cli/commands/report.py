import os
import click
import json
from datetime import datetime
from pathlib import Path

from ..database import AssetDatabase
from ..utils.file_ops import write_json_file, get_file_size_mb


@click.group()
def report():
    """报告生成命令"""
    pass


@report.command('customer-list')
@click.argument('output_path', type=click.Path())
@click.option('--format', 'output_format',
              type=click.Choice(['json', 'csv', 'txt']),
              default='json', help='输出格式')
@click.option('--include-deliveries', is_flag=True, help='包含交付历史')
def customer_list(output_path, output_format, include_deliveries):
    """输出客户清单"""
    db = AssetDatabase()

    with db._get_connection() as conn:
        rows = conn.execute(
            '''SELECT DISTINCT customer_name,
                     COUNT(*) as delivery_count,
                     MAX(created_at) as last_delivery
              FROM deliveries
              GROUP BY customer_name
              ORDER BY last_delivery DESC'''
        ).fetchall()

    customers = []
    for row in rows:
        customer = {
            'name': row['customer_name'],
            'delivery_count': row['delivery_count'],
            'last_delivery': row['last_delivery']
        }

        if include_deliveries:
            customer_deliveries = db.list_deliveries(customer_name=row['customer_name'])
            customer['deliveries'] = []
            for d in customer_deliveries:
                delivery_info = {
                    'id': d['id'],
                    'project': d.get('project_name'),
                    'date': d.get('delivery_date') or d['created_at'],
                    'status': d['status']
                }
                if d.get('manifest'):
                    manifest = d['manifest']
                    delivery_info['asset_count'] = (
                        len(manifest.get('avatars', [])) +
                        len(manifest.get('wardrobe', [])) +
                        len(manifest.get('motions', [])) +
                        len(manifest.get('scenes', []))
                    )
                customer['deliveries'].append(delivery_info)

        customers.append(customer)

    report = {
        'generated_at': datetime.now().isoformat(),
        'total_customers': len(customers),
        'customers': customers
    }

    if output_format == 'json':
        if write_json_file(output_path, report):
            click.echo(f"[OK] 客户清单已保存到 {output_path}")
            click.echo(f"   共 {len(customers)} 个客户")
        else:
            click.echo(f"[ERROR] 保存失败", err=True)

    elif output_format == 'csv':
        lines = ['客户名称,交付次数,最近交付日期']
        for c in customers:
            lines.append(
                f"{c['name']},{c['delivery_count']},{c['last_delivery']}"
            )
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        click.echo(f"[OK] 客户清单已保存到 {output_path}")

    elif output_format == 'txt':
        lines = []
        lines.append("=" * 60)
        lines.append("客户清单")
        lines.append("=" * 60)
        lines.append(f"生成时间: {report['generated_at']}")
        lines.append(f"客户总数: {report['total_customers']}")
        lines.append("")
        lines.append(f"{'序号':<6}{'客户名称':<25}{'交付次数':<10}{'最近交付':<20}")
        lines.append("-" * 60)

        for i, c in enumerate(customers, 1):
            lines.append(
                f"{i:<6}{c['name']:<25}{c['delivery_count']:<10}{c['last_delivery']:<20}"
            )

            if include_deliveries and c.get('deliveries'):
                lines.append("")
                lines.append(f"  交付历史:")
                for d in c['deliveries']:
                    asset_count = d.get('asset_count', 0)
                    lines.append(
                        f"    [{d['id']}] {d.get('project') or '未命名项目'} - "
                        f"{d['date']} ({asset_count}项资产) [{d['status']}]"
                    )
                lines.append("")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        click.echo(f"[OK] 客户清单已保存到 {output_path}")


@report.command('acceptance')
@click.argument('delivery_id', type=int)
@click.argument('output_path', type=click.Path())
@click.option('--format', 'output_format',
              type=click.Choice(['json', 'txt', 'html']),
              default='txt', help='输出格式')
def acceptance_report(delivery_id, output_path, output_format):
    """生成验收报告"""
    db = AssetDatabase()
    delivery = db.get_delivery(delivery_id)

    if not delivery:
        click.echo(f"[ERROR] 交付 {delivery_id} 不存在", err=True)
        return

    manifest = delivery.get('manifest', {})

    avatars = manifest.get('avatars', [])
    wardrobe = manifest.get('wardrobe', [])
    motions = manifest.get('motions', [])
    scenes = manifest.get('scenes', [])

    total_assets = len(avatars) + len(wardrobe) + len(motions) + len(scenes)

    checked_assets = []
    issues_found = []

    for a in avatars:
        result = _check_asset('avatar', a)
        checked_assets.append(result)
        if result['issues']:
            issues_found.extend(result['issues'])

    for w in wardrobe:
        result = _check_asset('wardrobe', w)
        checked_assets.append(result)
        if result['issues']:
            issues_found.extend(result['issues'])

    for m in motions:
        result = _check_asset('motion', m)
        checked_assets.append(result)
        if result['issues']:
            issues_found.extend(result['issues'])

    for s in scenes:
        result = _check_asset('scene', s)
        checked_assets.append(result)
        if result['issues']:
            issues_found.extend(result['issues'])

    open_issues = db.list_issues(fixed=False)
    related_issues = [
        i for i in open_issues
        if (i['asset_type'] == 'avatar' and any(a['id'] == i['asset_id'] for a in avatars)) or
           (i['asset_type'] == 'wardrobe' and any(w['id'] == i['asset_id'] for w in wardrobe)) or
           (i['asset_type'] == 'motion' and any(m['id'] == i['asset_id'] for m in motions)) or
           (i['asset_type'] == 'scene' and any(s['id'] == i['asset_id'] for s in scenes))
    ]

    report = {
        'generated_at': datetime.now().isoformat(),
        'delivery_id': delivery_id,
        'customer': delivery['customer_name'],
        'project': delivery.get('project_name'),
        'delivery_date': delivery.get('delivery_date') or delivery['created_at'],
        'summary': {
            'total_assets': total_assets,
            'avatars': len(avatars),
            'wardrobe': len(wardrobe),
            'motions': len(motions),
            'scenes': len(scenes),
            'issues_found': len(issues_found),
            'open_issues': len(related_issues),
            'pass_rate': f"{((total_assets - len(related_issues)) / total_assets * 100):.1f}%" if total_assets > 0 else "N/A"
        },
        'assets': checked_assets,
        'open_issues': related_issues,
        'recommendations': _generate_recommendations(related_issues, issues_found)
    }

    if output_format == 'json':
        if write_json_file(output_path, report):
            click.echo(f"[OK] 验收报告已保存到 {output_path}")
        else:
            click.echo(f"[ERROR] 保存失败", err=True)

    elif output_format == 'txt':
        content = _format_acceptance_txt(report)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        click.echo(f"[OK] 验收报告已保存到 {output_path}")

    elif output_format == 'html':
        content = _format_acceptance_html(report)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        click.echo(f"[OK] 验收报告已保存到 {output_path}")

    click.echo(f"")
    click.echo(f"=== 验收摘要 ===")
    click.echo(f"资产总数: {total_assets}")
    click.echo(f"待修复问题: {len(related_issues)}")
    click.echo(f"通过率: {report['summary']['pass_rate']}")


@report.command('stats')
@click.option('--project', 'project_id', type=int, help='按项目筛选')
@click.option('--output', '-o', type=click.Path(), help='输出到文件')
def show_stats(project_id, output):
    """显示资产统计信息"""
    db = AssetDatabase()

    avatars = db.list_avatars(project_id=project_id)
    wardrobe = db.list_wardrobe_items(project_id=project_id)
    motions = db.list_motions(project_id=project_id)
    scenes = db.list_scenes(project_id=project_id)
    issues = db.list_issues(fixed=False)

    with db._get_connection() as conn:
        outfit_count = conn.execute('SELECT COUNT(*) as cnt FROM outfits').fetchone()['cnt']
        delivery_count = conn.execute('SELECT COUNT(*) as cnt FROM deliveries').fetchone()['cnt']
        tag_count = conn.execute('SELECT COUNT(*) as cnt FROM tags').fetchone()['cnt']

    gender_stats = {}
    style_stats = {}
    for a in avatars:
        g = a['gender'] or 'unknown'
        gender_stats[g] = gender_stats.get(g, 0) + 1
        s = a['style'] or 'unknown'
        style_stats[s] = style_stats.get(s, 0) + 1

    category_stats = {}
    for w in wardrobe:
        c = w['category']
        category_stats[c] = category_stats.get(c, 0) + 1

    motion_category_stats = {}
    motion_validated = 0
    for m in motions:
        c = m['category'] or 'unknown'
        motion_category_stats[c] = motion_category_stats.get(c, 0) + 1
        if m['validated']:
            motion_validated += 1

    stats = {
        'generated_at': datetime.now().isoformat(),
        'avatars': {
            'total': len(avatars),
            'by_gender': gender_stats,
            'by_style': style_stats
        },
        'wardrobe': {
            'total': len(wardrobe),
            'by_category': category_stats,
            'outfits': outfit_count
        },
        'motions': {
            'total': len(motions),
            'by_category': motion_category_stats,
            'validated': motion_validated,
            'validation_rate': f"{(motion_validated / len(motions) * 100):.1f}%" if motions else "N/A"
        },
        'scenes': {
            'total': len(scenes)
        },
        'issues': {
            'open': len(issues),
            'by_severity': {}
        },
        'deliveries': {
            'total': delivery_count
        },
        'tags': {
            'total': tag_count
        }
    }

    for issue in issues:
        sev = issue['severity']
        stats['issues']['by_severity'][sev] = stats['issues']['by_severity'].get(sev, 0) + 1

    click.echo(f"\n=== 资产统计 ===")
    click.echo(f"")
    click.echo(f"角色: {len(avatars)}")
    for g, cnt in sorted(gender_stats.items()):
        click.echo(f"  {g}: {cnt}")
    click.echo(f"")
    click.echo(f"服装: {len(wardrobe)}")
    for c, cnt in sorted(category_stats.items()):
        click.echo(f"  {c}: {cnt}")
    click.echo(f"套装: {outfit_count}")
    click.echo(f"")
    click.echo(f"动作: {len(motions)} (已验证: {motion_validated})")
    click.echo(f"场景: {len(scenes)}")
    click.echo(f"")
    click.echo(f"待修复问题: {len(issues)}")
    for sev in ['critical', 'high', 'medium', 'low']:
        if sev in stats['issues']['by_severity']:
            click.echo(f"  {sev}: {stats['issues']['by_severity'][sev]}")
    click.echo(f"")
    click.echo(f"交付记录: {delivery_count}")
    click.echo(f"标签数量: {tag_count}")

    if output:
        if write_json_file(output, stats):
            click.echo(f"\n[OK] 统计数据已保存到 {output}")


def _check_asset(asset_type, asset):
    result = {
        'type': asset_type,
        'id': asset['id'],
        'name': asset['name'],
        'version': asset.get('version', '1.0'),
        'status': 'pass',
        'checks': [],
        'issues': []
    }

    if asset.get('model_path'):
        exists = os.path.exists(asset['model_path'])
        result['checks'].append({
            'name': '模型文件',
            'pass': exists,
            'path': asset['model_path']
        })
        if not exists:
            result['status'] = 'fail'
            result['issues'].append('模型文件不存在')

    if asset.get('preview_image'):
        exists = os.path.exists(asset['preview_image'])
        result['checks'].append({
            'name': '预览图',
            'pass': exists,
            'path': asset['preview_image']
        })
        if not exists:
            result['issues'].append('预览图不存在')

    if asset.get('texture_paths'):
        for tex in asset['texture_paths']:
            exists = os.path.exists(tex)
            result['checks'].append({
                'name': '贴图',
                'pass': exists,
                'path': tex
            })
            if not exists:
                result['status'] = 'fail'
                result['issues'].append(f'贴图不存在: {tex}')

    if asset_type == 'motion':
        result['checks'].append({
            'name': '已验证',
            'pass': asset.get('validated', False)
        })
        if not asset.get('validated'):
            result['issues'].append('动作未验证')

    if asset.get('copyright_source'):
        result['checks'].append({
            'name': '版权信息',
            'pass': True,
            'source': asset['copyright_source']
        })

    return result


def _generate_recommendations(open_issues, file_issues):
    recommendations = []

    if open_issues:
        recommendations.append(
            f"存在 {len(open_issues)} 个待修复的问题，建议修复后再交付"
        )

    critical_count = sum(1 for i in open_issues if i['severity'] == 'critical')
    high_count = sum(1 for i in open_issues if i['severity'] == 'high')

    if critical_count > 0:
        recommendations.append(f"存在 {critical_count} 个严重问题，必须修复")
    if high_count > 0:
        recommendations.append(f"存在 {high_count} 个高危问题，建议修复")

    if file_issues:
        recommendations.append(
            f"发现 {len(file_issues)} 个文件问题，建议检查文件路径"
        )

    if not recommendations:
        recommendations.append("所有检查通过，资产符合交付标准")

    return recommendations


def _format_acceptance_txt(report):
    lines = []
    lines.append("=" * 70)
    lines.append("元宇宙资产验收报告")
    lines.append("=" * 70)
    lines.append(f"")
    lines.append(f"报告编号: ACC-{report['delivery_id']:06d}")
    lines.append(f"生成时间: {report['generated_at']}")
    lines.append(f"")
    lines.append(f"客户: {report['customer']}")
    if report['project']:
        lines.append(f"项目: {report['project']}")
    lines.append(f"交付日期: {report['delivery_date']}")
    lines.append(f"")
    lines.append("-" * 70)
    lines.append("验收摘要")
    lines.append("-" * 70)
    lines.append(f"")
    s = report['summary']
    lines.append(f"资产总数: {s['total_assets']}")
    lines.append(f"  - 角色: {s['avatars']}")
    lines.append(f"  - 服装: {s['wardrobe']}")
    lines.append(f"  - 动作: {s['motions']}")
    lines.append(f"  - 场景: {s['scenes']}")
    lines.append(f"发现问题: {s['issues_found']}")
    lines.append(f"待修复: {s['open_issues']}")
    lines.append(f"验收通过率: {s['pass_rate']}")
    lines.append(f"")

    if report['open_issues']:
        lines.append("-" * 70)
        lines.append("待修复问题")
        lines.append("-" * 70)
        lines.append(f"")
        for issue in report['open_issues']:
            lines.append(
                f"[{issue['id']}] [{issue['severity']}] {issue['asset_type']} "
                f"#{issue['asset_id']} - {issue['issue_type']}"
            )
            if issue['description']:
                lines.append(f"      {issue['description']}")
            lines.append(f"")

    lines.append("-" * 70)
    lines.append("资产详情")
    lines.append("-" * 70)
    lines.append(f"")

    for asset in report['assets']:
        status = '[OK]' if asset['status'] == 'pass' else '[ERROR]'
        lines.append(
            f"{status} [{asset['type']}] {asset['name']} (ID: {asset['id']}, v{asset['version']})"
        )
        for check in asset['checks']:
            check_status = '[OK]' if check['pass'] else '[ERROR]'
            line = f"    {check_status} {check['name']}"
            if check.get('path'):
                line += f": {check['path']}"
            lines.append(line)
        if asset['issues']:
            for issue in asset['issues']:
                lines.append(f"    [ERROR] {issue}")
        lines.append(f"")

    lines.append("-" * 70)
    lines.append("建议")
    lines.append("-" * 70)
    lines.append(f"")
    for i, rec in enumerate(report['recommendations'], 1):
        lines.append(f"{i}. {rec}")
    lines.append(f"")
    lines.append("=" * 70)

    return '\n'.join(lines)


def _format_acceptance_html(report):
    s = report['summary']
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>验收报告 - {report['customer']}</title>
    <style>
        body {{ font-family: 'Microsoft YaHei', sans-serif; margin: 40px; }}
        h1 {{ color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; }}
        .summary {{ background: #f8f9fa; padding: 20px; border-radius: 8px; }}
        .pass {{ color: #28a745; }}
        .fail {{ color: #dc3545; }}
        .asset {{ margin: 15px 0; padding: 15px; border: 1px solid #ddd; border-radius: 8px; }}
        .issue {{ background: #fff3cd; padding: 10px; margin: 5px 0; border-radius: 4px; }}
        .critical {{ background: #f8d7da; }}
        .high {{ background: #ffeeba; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #007bff; color: white; }}
    </style>
</head>
<body>
    <h1>元宇宙资产验收报告</h1>
    <p><strong>报告编号:</strong> ACC-{report['delivery_id']:06d}</p>
    <p><strong>生成时间:</strong> {report['generated_at']}</p>
    <p><strong>客户:</strong> {report['customer']}</p>
    {f'<p><strong>项目:</strong> {report["project"]}</p>' if report['project'] else ''}
    <p><strong>交付日期:</strong> {report['delivery_date']}</p>

    <h2>验收摘要</h2>
    <div class="summary">
        <table>
            <tr><th>类别</th><th>数量</th></tr>
            <tr><td>角色</td><td>{s['avatars']}</td></tr>
            <tr><td>服装</td><td>{s['wardrobe']}</td></tr>
            <tr><td>动作</td><td>{s['motions']}</td></tr>
            <tr><td>场景</td><td>{s['scenes']}</td></tr>
            <tr><td><strong>总计</strong></td><td><strong>{s['total_assets']}</strong></td></tr>
        </table>
        <p><strong>发现问题:</strong> <span class="fail">{s['issues_found']}</span></p>
        <p><strong>待修复:</strong> <span class="fail">{s['open_issues']}</span></p>
        <p><strong>验收通过率:</strong> {s['pass_rate']}</p>
    </div>
"""

    if report['open_issues']:
        html += """
    <h2>待修复问题</h2>
"""
        for issue in report['open_issues']:
            severity_class = issue['severity']
            html += f"""
    <div class="issue {severity_class}">
        <strong>[{issue['severity']}]</strong> {issue['asset_type']} #{issue['asset_id']} - {issue['issue_type']}
        {f'<br><small>{issue["description"]}</small>' if issue['description'] else ''}
    </div>
"""

    html += """
    <h2>资产详情</h2>
"""

    for asset in report['assets']:
        status_class = 'pass' if asset['status'] == 'pass' else 'fail'
        status_icon = '[OK]' if asset['status'] == 'pass' else '[ERROR]'
        html += f"""
    <div class="asset">
        <h3><span class="{status_class}">{status_icon}</span> [{asset['type']}] {asset['name']} <small>(ID: {asset['id']}, v{asset['version']})</small></h3>
"""
        for check in asset['checks']:
            check_status = '[OK]' if check['pass'] else '[ERROR]'
            check_class = 'pass' if check['pass'] else 'fail'
            extra = f": {check['path']}" if check.get('path') else ''
            html += f"""
        <p><span class="{check_class}">{check_status}</span> {check['name']}{extra}</p>
"""
        if asset['issues']:
            for issue in asset['issues']:
                html += f"""
        <p class="issue">[ERROR] {issue}</p>
"""
        html += "    </div>\n"

    html += """
    <h2>建议</h2>
    <ol>
"""
    for rec in report['recommendations']:
        html += f"        <li>{rec}</li>\n"

    html += """
    </ol>
</body>
</html>
"""
    return html
