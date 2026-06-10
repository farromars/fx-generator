"""douyinfx 命令行入口。

用法：
  douyinfx          # 启动 Web UI（默认）
  douyinfx ui       # 启动 Web UI
"""

import click


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """douyinfx - 抖音面部特效素材生成工具（Web UI）。"""
    if ctx.invoked_subcommand is None:
        from app import launch
        launch()


@main.command()
def ui():
    """启动 Web UI。"""
    from app import launch
    launch()
