from setuptools import setup
from os import path
from pathlib import Path

# Get the long description from the README file
with Path(path.dirname(__file__), 'readme.md').resolve().open() as f:
    readme = f.read()

setup(
    # https://packaging.python.org/specifications/core-metadata/#name
    name='zen-compile',
    # Versions should comply with PEP 440:
    # https://www.python.org/dev/peps/pep-0440/
    version='0.0.3',
    description='Zen: Reducing recompilation times',
    long_description=readme,
    long_description_content_type='text/markdown',
    url='https://github.com/TryExceptElse/zen',
    author='TryExceptElse',
    # For a list of valid classifiers, see https://pypi.org/classifiers/
    classifiers=[
        'Development Status :: 3 - Alpha',

        # Audience / Project Category.
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'Topic :: Utilities',

        'License :: OSI Approved :: Apache Software License',

        'Operating System :: POSIX :: Linux',

        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    keywords='c++ cpp cxx zen compile compiler compilation recompilation '
             'static analysis optimization focus whitespace',
    install_requires=[],
    python_requires='>=3.6.0',
    entry_points={
        'console_scripts': [
            'zen=zen:main',
        ],
    },
    project_urls={
        'Source': 'https://github.com/TryExceptElse/zen',
    },
    py_modules=['zen']
)
