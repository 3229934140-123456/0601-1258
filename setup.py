from setuptools import setup, find_packages

setup(
    name='metaverse-cli',
    version='1.0.0',
    description='元宇宙平台命令行工具 - 虚拟形象工作室资产管理',
    packages=find_packages(),
    python_requires='>=3.8',
    install_requires=[
        'click>=8.1.0',
        'Pillow>=10.0.0',
        'filetype>=1.2.0',
        'send2trash>=1.8.2',
    ],
    entry_points={
        'console_scripts': [
            'mvcli=metaverse_cli.main:cli',
        ],
    },
)
