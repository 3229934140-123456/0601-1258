import click
import sys
from . import __version__

from .commands.avatar import avatar
from .commands.wardrobe import wardrobe
from .commands.motion import motion
from .commands.scene import scene
from .commands.check import check
from .commands.pack import pack
from .commands.report import report
from .commands.project import project
from .commands.manifest import manifest


@click.group(invoke_without_command=True)
@click.version_option(__version__, '-v', '--version', prog_name='mvcli')
@click.pass_context
def cli(ctx):
    """
    元宇宙平台命令行工具 (Metaverse CLI)

    用于虚拟形象工作室管理大量头像资产，提供以下功能模块：

    \b
    avatar   - 头像资产管理（创建、导入、标签、改名等）
    wardrobe - 衣柜与服装管理（单品、套装、绑定角色）
    motion   - 动作文件管理（导入、验证、导出）
    scene    - 场景管理（创建、导入、更新）
    check    - 资产检查（贴图缺失、重复、版本差异、问题标记）
    pack     - 打包交付（缩略图、交付包、撤销、备份）
    report   - 报告生成（客户清单、验收报告、统计信息）
    project  - 项目工作区（创建项目、归集资产、按项目筛选）
    manifest - 批量导入（从CSV/JSON清单一次性导入多种资产）
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


cli.add_command(avatar, 'avatar')
cli.add_command(wardrobe, 'wardrobe')
cli.add_command(motion, 'motion')
cli.add_command(scene, 'scene')
cli.add_command(check, 'check')
cli.add_command(pack, 'pack')
cli.add_command(report, 'report')
cli.add_command(project, 'project')
cli.add_command(manifest, 'manifest')


def main():
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\n操作已取消")
        sys.exit(1)
    except Exception as e:
        click.echo(f"\n错误: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
