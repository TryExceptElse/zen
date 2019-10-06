#!/env/bin/python3
"""
This file contains a script to run inspections on the zen module.
"""
from pathlib import Path
import re
import subprocess as sub
import sys
import typing as ty


ROOT = Path(__file__).parent.parent

MYPY_IGNORED = (
    r'error\: Slice index must be an integer or None',
    r'Found .* errors in .* file \(checked .* source files?\)',
    r'Success\: no issues found in .* source file'
)


def mypy() -> int:
    """
    Runs mypy on the python files of the zen project
    (including this one).

    Notably, because of the false positives currently present when
    slice is used with values other than int or None, these errors will
    be filtered from the output.

    :return: int return code.
    """
    modules = Path(ROOT, 'zen.py'), Path(ROOT, 'scripts', 'check.py')

    def process_stderr(err: str) -> int:
        code_ = 0
        for line in err.split('\n'):
            if not line:
                continue
            if any(re.findall(ignored, line) for ignored in MYPY_IGNORED):
                continue
            print(line, file=sys.stderr)
            if 'error:' in line:
                code_ = 1
        return code_

    code = 0
    module_strings = [str(module) for module in modules]
    completed_process = sub.run(
        (sys.executable, '-m', 'mypy', *module_strings, '--strict'),
        stdout=sub.PIPE,
        stderr=sub.STDOUT,
        encoding='utf-8'
    )
    code = max(code, process_stderr(completed_process.stdout))

    return code


def check() -> ty.NoReturn:
    """
    Runs all checks.
    :return: None
    """
    code = mypy()
    exit(code)


if __name__ == '__main__':
    check()
