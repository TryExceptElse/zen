"""
Zen: Reducing recompilation times.
"""
import argparse
import enum
import hashlib
import json
import os
from pathlib import Path
import re
import string
import subprocess as sub
import sys
import time
import typing as ty


class ParsingException(Exception):
    """
    Exception class used to indicate problems parsing file content.
    """


class ComponentCreationError(ValueError):
    """
    Exception thrown when a component cannot be instantiated from a
    specified location in source.
    """


class Status(enum.IntEnum):
    UNCHECKED = 1
    NO_CHANGE = 2
    MINOR_CHANGE = 3
    CHANGED = 4


class TargetType(enum.Enum):
    EXECUTABLE = 1
    STATIC_LIB = 2
    SHARED_LIB = 3
    UNKNOWN = 4


LIB_TYPES = {TargetType.STATIC_LIB, TargetType.SHARED_LIB}

BRACKETS = {
    '(': ')',
    '{': '}',
    '[': ']',
    '<': '>'
}


#######################################################################
# Build constructs


class BuildDir:
    """
    Root build data class.
    """

    CACHE_NAME = 'zen_cache'

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.targets = self._find_targets()
        self.targets_by_path = {
            target.file_path.absolute(): target
            for target in self.targets.values()
        }
        self.sources = self._find_sources()

    def meditate(self) -> None:
        """
        Minimizes number of objects and targets that need to
        be rebuilt.
        :return: None
        """
        [target.meditate() for target in self.targets.values()]

    def remember(self) -> None:
        [self.get_cache(dep).cache(dep) for dep in self.sources]

    def _find_targets(self) -> ty.Dict[str, 'Target']:
        """
        Gets list of previously built targets.
        :return: List[Target]
        """
        targets = {}
        for target_dir in self.path.rglob('*.dir'):
            name: str = os.path.splitext(target_dir.name)[0]
            if name in targets:
                raise ValueError(f'Multiple targets with name: {name} found.')
            targets[name] = Target(name, target_dir, self)
        return targets

    def _find_sources(self) -> ty.Set['SourceFile']:
        dependencies = set()
        for target in self.targets.values():
            for compile_object in target.objects:
                for dependency in compile_object.sources:
                    dependencies.add(dependency)
        return dependencies

    def get_cache(self, src: 'SourceFile') -> 'SourceCache':
        """
        Gets SourceCache storing previously compiled values.
        :param src: SourceFile
        :return: SourceCache
        """
        if not self.cache_path.exists():
            self.cache_path.mkdir()
        return SourceCache(Path(self.cache_path, src.hex))

    @property
    def cache_path(self) -> Path:
        return Path(self.path, self.CACHE_NAME)

    def __repr__(self) -> str:
        return f'BuildDir[{self.path}]'


class Target:
    """
    Class handling interaction with build files of a single target.
    """
    def __init__(self, name: str, path: Path, build_dir: 'BuildDir') -> None:
        """
        Initializes a new target handler.
        :param name: name of target.
        :param path: path to target build directory.
        :param build_dir: BuildDir instance.
        """
        self.name = name
        self.path = path
        self.build_dir = build_dir
        self.objects = self._find_objects()
        self.file_path: ty.Optional[Path] = None
        self.type: 'TargetType' = TargetType.UNKNOWN
        self.file_path, self.type = self._identify_target()
        self.dependency_paths: ty.Set[Path] = self._find_dependencies()
        self.status = Status.UNCHECKED

    def meditate(self) -> None:
        if self.status != Status.UNCHECKED:
            return  # Already meditated.

        # Run on lib dependencies first; the status of the target will
        # be determined in part by their change status.
        if self.lib_dependencies:
            for lib in self.lib_dependencies:
                lib.meditate()
            max_lib_status = max(lib.status for lib in self.lib_dependencies)
        else:
            max_lib_status = Status.NO_CHANGE

        # Run on object dependencies.
        if self.objects:
            [o.meditate() for o in self.objects]
            max_obj_status = max(o.status for o in self.objects)
        else:
            max_obj_status = Status.NO_CHANGE

        # If file_path does not exist: the target must be built,
        # and so should be considered changed.
        if self.file_path.exists():
            self.status = max((
                max_obj_status,
                max_lib_status,
                self.other_status
            ))
        else:
            self.status = Status.CHANGED

        if self.status == Status.MINOR_CHANGE and \
                self.type != TargetType.UNKNOWN:
            self.avoid_build()

    def avoid_build(self) -> None:
        """
        Un-Marks this target for re-linking.
        This method should only be called if target is known.
        :return: None
        """
        sub.call(['touch', '-c', str(self.file_path.absolute())])

    @staticmethod
    def type_from_path(path: str) -> TargetType:
        ext = os.path.splitext(path)[1]
        # noinspection PyTypeChecker
        return {
            '': TargetType.EXECUTABLE,
            '.a': TargetType.STATIC_LIB,
            '.so': TargetType.SHARED_LIB
        }.get(ext, TargetType.UNKNOWN)

    def _find_objects(self) -> ty.List['CompileObject']:
        """
        Finds objects belonging to target.
        :return: List[Object]
        """
        depend_internal_path = Path(self.path, 'depend.internal')
        if not depend_internal_path.exists():
            return []
        objects = []
        with depend_internal_path.open() as f:
            object_path: ty.Optional[Path] = None
            dependencies: ty.Set[Path] = []
            for line in f.readlines():
                line = line.rstrip()
                # Check if line indicates object dependency.
                if object_path and line and line.startswith(' '):
                    dependencies.append(Path(line.strip()))
                # Check if object description has ended.
                if object_path and line.endswith('.o'):
                    objects.append(CompileObject(
                        object_path, dependencies, self.build_dir))
                    dependencies = []
                # If a new object description has begun, set object.
                if line.endswith('.o'):
                    object_path = Path(self.build_dir.path, line.strip())
            objects.append(CompileObject(
                object_path, dependencies, self.build_dir))
        return objects

    def _identify_target(self) -> ty.Tuple[ty.Optional[Path], 'TargetType']:
        """
        Attempts to locate and identify the target file produced by
        the Target.
        :return: Tuple[Path, TargetType]
        """
        clean_file_path = Path(self.path, 'cmake_clean.cmake')

        # Get last line of remove recurse command,
        # which should be target.
        with clean_file_path.open() as f:
            s = f.read()
        start_key = 'file(REMOVE_RECURSE'
        start = s.find(start_key)
        if start == -1:
            # noinspection PyTypeChecker
            return None, TargetType.UNKNOWN
        start += len(start_key)
        end = s.find('\n)\n', start)
        files = s[start:end].splitlines()
        target_name = files[-1].strip()
        assert target_name[0] == '"'
        assert target_name[-1] == '"'
        target_name = target_name[1:-1]

        # Attempt to determine type from extension.
        target_type = self.type_from_path(target_name)

        # If target type is unknown, don't presume that the path
        # that was found represents the target file.
        if target_type == TargetType.UNKNOWN:
            path = None
        else:
            path = Path(self.path, '..', '..', target_name).resolve()
        # noinspection PyTypeChecker
        return path, target_type

    def _find_dependencies(self) -> ty.Set[Path]:
        build_make_path = Path(self.path, 'build.make')
        paths = set()
        with build_make_path.open() as f:
            prefix = f'{self.name}:'
            for line in f.readlines():
                if line.startswith(prefix):
                    rel_path = line[len(prefix):].strip()
                    paths.add(Path(self.build_dir.path, rel_path))
        return paths

    @property
    def m_time(self):
        """
        Gets modification time of compiled object.
        :return: float time in seconds since epoch.
        """
        return os.path.getmtime(self.file_path)

    @property
    def other_status(self) -> Status:
        if any(os.path.getmtime(other) > self.m_time for
               other in self.other_dependencies):
            return Status.CHANGED
        return Status.NO_CHANGE

    @property
    def lib_dependencies(self) -> ty.Set['Target']:
        libraries = set()
        for dep in self.dependency_paths:
            if self.type_from_path(dep.absolute()) not in LIB_TYPES:
                continue
            try:
                target = self.build_dir.targets_by_path[dep]
                libraries.add(target)
            except KeyError as e:
                raise ValueError(
                    f'Could not find target with path: {dep}') from e
        return libraries

    @property
    def other_dependencies(self) -> ty.Set[Path]:
        """
        Finds dependencies other than objects and libraries,
        such as build files.
        :return: Set[Path]
        """
        others = set()
        for dep in self.dependency_paths:
            if self.type_from_path(dep.absolute()) in LIB_TYPES:
                continue
            if os.path.splitext(dep)[1] == '.o':
                continue
            others.add(dep)
        return others

    def __repr__(self) -> str:
        return f'Target[{self.name}]'


class CompileObject:
    """
    Class handling specific compiled object.
    """
    def __init__(
            self,
            path: Path,
            sources: ty.List[Path],
            build_dir: 'BuildDir'
    ) -> None:
        """
        Create a handler for a compilation object.

        :param path: Path to .o object.
        :param sources: absolute paths to source
                    file dependencies.
        :param build_dir: BuildDir instance.
        """
        self.path = path
        self.sources = [SourceFile(src) for src in sources]
        self.build_dir = build_dir
        self.status = Status.UNCHECKED
        self.non_source_change = False  # Set if build file, etc, changes.

    def meditate(self) -> None:
        """
        Determine whether the managed compilation object should be
        rebuilt or whether compilation can be avoided.
        :return: None
        """
        if self.sources_modified:
            verbose(f'{repr(self)} sources modified. Checking source.')
        else:
            self.status = Status.NO_CHANGE
            return
        substantive_changes = False
        for dep in self.sources:
            try:
                cache = self.build_dir.get_cache(dep)
            except KeyError:
                self.status = Status.CHANGED
                return
            if dep.substantive_changes(cache):
                substantive_changes = True
                self.status = Status.CHANGED
                break
        if not substantive_changes:
            self.status = Status.MINOR_CHANGE
            self.avoid_build()

    def avoid_build(self) -> None:
        """
        Un-Marks this object for re-compilation.
        :return: None
        """
        sub.call(['touch', '-c', str(self.path.absolute())])

    @property
    def m_time(self):
        """
        Gets modification time of compiled object.
        :return: float time in seconds since epoch.
        """
        return os.path.getmtime(self.path.absolute())

    @property
    def sources_modified(self) -> bool:
        """
        Checks whether any of the sources for this object are more
        recent than this object's latest modification.
        :return: bool
        """
        try:
            own_m_time = self.m_time
        except FileNotFoundError:
            return True
        return any([own_m_time <= dep.m_time for dep in self.sources])

    def __repr__(self) -> str:
        return f'Object[{os.path.basename(self.path)}]'


class SourceFile:
    """
    Handler for a specific source file on disk.

    Only one SourceFile instance should exist for a given
    absolute path. Instantiating SourceFile multiple times using the
    same path will result in references to the same SourceFile instance
    being returned.
    """
    _source_files = {}

    def __new__(cls, path: Path) -> 'SourceFile':
        try:
            src = cls._source_files[path.absolute()]
        except KeyError:
            src = cls._source_files[path.absolute()] = object.__new__(cls)
        return src

    def __init__(self, path: Path) -> None:
        if hasattr(self, '_initialized'):
            return
        self.path = path
        self._access_time: ty.Optional[float] = None
        self._content: ty.Optional['SourceContent'] = None
        self._initialized = True

    @classmethod
    def clear(cls) -> None:
        cls._source_files.clear()

    def substantive_changes(self, cache: 'SourceCache') -> bool:
        """
        Check for changes against cache.

        :param cache: SourceCache
        :return: bool which is True if changes have occurred.
        """
        if self.stripped_hash != cache.stripped_hash:
            return True

    @property
    def m_time(self) -> float:
        """
        Gets modification time of source file.
        :return: float time in seconds since epoch.
        """
        return os.path.getmtime(self.path.absolute())

    @property
    def content(self) -> 'SourceContent':
        if self._content is None or self.m_time > self._access_time:
            self._access_time = time.time()
            with self.path.open() as f:
                self._content = SourceContent(f)
        # noinspection PyTypeChecker
        return self._content

    @property
    def stripped_hash(self) -> int:
        return self.content.stripped_hash

    @property
    def hex(self) -> str:
        """
        Gets hex representation of source path hash.
        :return: str
        """
        return hashlib.md5(str(self.path).encode()).hexdigest()

    def __repr__(self) -> str:
        return f'SourceFile[{os.path.basename(self.path)}]'


class SourceCache:
    """
    Handles access of previously cached source file information.
    """
    STRIPPED_HASH_K = 'stripped_hash'

    def __init__(self, path: Path) -> None:
        self.path = path
        self._access_time: ty.Optional[float] = 0
        self._accessed_d: ty.Optional[ty.Dict[str, ty.Any]] = None

    def cache(self, source: 'SourceFile') -> None:
        """
        Updates cached data from passed source.
        :param source: SourceFile
        :return: None
        """
        d = {
            self.STRIPPED_HASH_K: source.stripped_hash
        }
        with self.path.open('w') as f:
            json.dump(d, f)

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def m_time(self) -> float:
        """
        Gets modification time of source file.
        :return: float time in seconds since epoch.
        """
        return os.path.getmtime(self.path.absolute())

    @property
    def _d(self) -> ty.Dict[str, ty.Any]:
        if self._accessed_d is None or self._access_time < self.m_time:
            self._access_time = time.time()
            with self.path.open() as f:
                self._accessed_d = json.load(f)
        # noinspection PyTypeChecker
        return self._accessed_d

    @property
    def stripped_hash(self) -> int:
        """
        Gets hash of the cached source file's raw content.
        :rtype: int
        """
        return self._d[self.STRIPPED_HASH_K]


#######################################################################
# Source analysis


class SourceContent:
    path: Path
    lines: ty.List['Line']
    _raw_hash: ty.Optional[int]

    def __init__(self, content: ty.Union[str, ty.TextIO]) -> None:
        if isinstance(content, str):
            self.lines = self._lines_from_str(content)
        else:
            self.lines = self._lines_from_f(content)
        self._raw_hash: ty.Optional[int] = None
        self._stripped_comments: bool = False
        self._component: ty.Optional['Block'] = None
        self._constructs: ty.Dict[str, 'Construct'] = None
        self._chunk: ty.Optional['Chunk'] = None

    def strip_comments(self) -> None:
        """
        Removes comments from all lines in content.
        :return: None
        """
        if self._stripped_comments:
            raise ValueError('Already stripped comments')
        in_block: bool = False
        for line in self.lines:
            s: str = line.raw
            i: int = 0
            chunks: ty.List[str] = []
            while True:
                if in_block:
                    end_index = s.find('*/', i)
                    if end_index == -1:
                        break
                    i = end_index + len('*/')
                    in_block = False
                else:
                    start_index = s.find('/*', i)
                    chunk_end = start_index if start_index != -1 else None
                    # Add found useful code to chunks
                    chunks.append(s[i:chunk_end])
                    if start_index == -1:
                        break
                    i = start_index + len('/*')
                    in_block = True
            unblocked = ' '.join(chunks)
            line_comment_start = unblocked.find('//')
            if line_comment_start == -1:
                uncommented = unblocked
            else:
                uncommented = unblocked[:line_comment_start]
            if line.raw.endswith('\n'):
                uncommented += '\n'
            line.uncommented = uncommented
        self._stripped_comments = True

    def start_pos(self, form: 'SourceForm') -> 'SourcePos':
        return SourcePos(self, 0, 0, form)

    def end_pos(self, form: 'SourceForm') -> 'SourcePos':
        return SourcePos(self, -1, len(self.lines[-1].s(form)), form)

    @property
    def has_uncommented(self) -> bool:
        return self._stripped_comments

    @property
    def stripped_hash(self) -> int:
        """
        Gets hash of raw content, before documentation has been
        stripped from it.
        :rtype: int
        """
        if self._raw_hash is None:
            if not self._stripped_comments:
                self.strip_comments()
            self._raw_hash = iter_hash(
                line.stripped.strip()  # remove newline, etc.
                for line in self.lines if line.stripped != '\n')
        assert isinstance(self._raw_hash, int)
        return self._raw_hash

    @property
    def component(self) -> 'Block':
        if self._component is None:
            self._component = Block(self)
        assert isinstance(self._component, Block)
        return self._component

    @property
    def used_constructs(self) -> ty.Dict[str, 'Construct']:
        return self.component.used_constructs

    @staticmethod
    def _lines_from_str(content: str) -> ty.List['Line']:
        return [Line(i, line_s) for i, line_s in
                enumerate(content.splitlines(True))]

    @staticmethod
    def _lines_from_f(f: ty.TextIO) -> ty.List['Line']:
        return [Line(i, line_s) for i, line_s in enumerate(f.readlines())]


class Line:
    """
    Data storage class for storing information about a line of source.
    """
    i: int
    raw: str
    stripped: str
    uncommented: str

    def __init__(self, i: int, s: str) -> None:
        self.index = i
        self.raw = s
        self._uncommented: ty.Optional[str] = None

    @property
    def uncommented(self) -> str:
        """
        Since the 'uncommented' value of a Line is set externally,
        this property exists to check that it is not accessed before
        it has been calculated, to avoid silent failure.

        :return: str of uncommented content of line.
        """
        if self._uncommented is None:
            raise AttributeError(
                'Uncommented value of {repr(self)} has not been set.')
        return self._uncommented

    @uncommented.setter
    def uncommented(self, s: str) -> None:
        """
        Used by SourceContent to set Line instance's uncommented str.
        :param s: uncommented content str
        :return: None
        """
        self._uncommented = s

    @property
    def stripped(self) -> str:
        s = ' '.join(self.uncommented.split())
        if self.uncommented.endswith('\n'):
            s += '\n'
        return s
    
    def s(self, form: 'SourceForm') -> str:
        """
        Gets line string in the specified form.

        :param form: SourceForm; RAW, UNCOMMENTED, or STRIPPED
        :return: str of line content.
        :rtype: str
        :raises ValueError if uncommented form has not been set and
                    UNCOMMENTED or STRIPPED form is passed as an arg.
        """
        if form == SourceForm.RAW:
            return self.raw
        if form == SourceForm.UNCOMMENTED:
            return self.uncommented
        if form == SourceForm.STRIPPED:
            return self.stripped

    def __repr__(self) -> str:
        preview_len = 40
        # Produces Line[i: index, s: preview + ... if preview runs over]
        return f'Line[i: {self.index}, ' \
               f'\'{self.raw[:preview_len]}' \
               f'{"..." if len(self.raw) > preview_len else ""}\']'


class SourceForm(enum.Enum):
    RAW = 1
    UNCOMMENTED = 2
    STRIPPED = 3


class SourcePos:
    """
    Class storing position within source.
    """

    def __init__(
            self,
            file_content: 'SourceContent',
            line_i: int,
            col_i: int,
            form: 'SourceForm'
    ) -> None:
        self.file_content = file_content
        self.form = form
        if not self.file_content.has_uncommented and form in (
                SourceForm.UNCOMMENTED, SourceForm.STRIPPED):
            self.file_content.strip_comments()
        self.line_i = self._normalize_line_i(line_i)
        col_i = self._normalize_col_i(col_i)
        if col_i == len(self.file_content.lines[line_i].s(self.form)) and \
                self.line_i < len(self.file_content.lines) - 1:
            self.line_i += 1
            col_i = 0
        self.col_i = col_i

    def __add__(self, n: int) -> 'SourcePos':
        original_n = n
        line = self.file_content.lines[self.line_i]
        remaining_chars = len(line.s(self.form)) - self.col_i
        if n < remaining_chars:
            return SourcePos(
                self.file_content,
                self.line_i,
                self.col_i + n,
                self.form
            )
        else:
            n -= remaining_chars
        for line in self.file_content.lines[self.line_i + 1:]:
            line_chars = len(line.s(self.form))
            if n < line_chars:
                return SourcePos(self.file_content, line.index, n, self.form)
            n -= line_chars
        else:
            raise ValueError(
                f'Cannot add {original_n} to {self}. '
                f'{original_n} is too large.')

    def __sub__(self, n: int) -> 'SourcePos':
        original_n = n
        remaining_chars = self.col_i
        if n <= remaining_chars:
            return SourcePos(
                self.file_content,
                self.line_i,
                self.col_i - n,
                self.form
            )
        else:
            n -= remaining_chars
        for line in reversed(self.file_content.lines[:self.line_i]):
            line_chars = len(line.s(self.form))
            if n <= line_chars:
                return SourcePos(
                    self.file_content,
                    line.index,
                    line_chars - n,
                    self.form)
            n -= line_chars
        else:
            raise ValueError(
                f'Cannot subtract {original_n} from {self}. '
                f'{original_n} is too large.')

    @property
    def next_line_pos(self) -> 'SourcePos':
        return SourcePos(self.file_content, self.line_i + 1, 0, self.form)

    def _normalize_line_i(self, i: int) -> int:
        original_i = i
        lines = self.file_content.lines
        if i < 0:
            i += len(lines)
        if not 0 <= i < len(lines):
            raise IndexError(
                f'Line/row index invalid: {original_i}. '
                f'{len(lines)} lines exist in {self.file_content}')
        return i

    def _normalize_col_i(self, i: int) -> int:
        original_i = i
        line = self.file_content.lines[self.line_i]
        line_len = len(line.s(self.form))
        if i < 0:
            i += line_len
        if not 0 <= i <= line_len:
            raise IndexError(
                f'Column index invalid: {original_i}. '
                f'Line {self.line_i} is {line_len} chars long.')
        return i

    def __repr__(self) -> str:
        return f'SourcePos[line: {self.line_i}, col: {self.col_i}]'


class Chunk:
    """
    Intermediate class used to store data about code and provide
    convenience accessors to help determine what kind of Component(s)
    are stored within the Chunk's code.
    """

    def __init__(
            self,
            file_content: 'SourceContent',
            start: ty.Optional['SourcePosI'] = None,
            end: ty.Optional['SourcePosI'] = None,
            form: 'SourceForm' = SourceForm.STRIPPED
    ) -> None:
        self.file_content = file_content
        self.form = form
        if not self.file_content.has_uncommented and form in (
                SourceForm.UNCOMMENTED, SourceForm.STRIPPED):
            self.file_content.strip_comments()
        self._start = start or file_content.start_pos(form)
        self._end = end or file_content.end_pos(form)
        if self.start.line_i > self.end.line_i:
            raise ValueError(
                f'Start line index: {self.start.line_i} follows '
                f'end line index: {self.end.line_i}.')
        if self.start.line_i == self.end.line_i and \
                self.start.col_i > self.end.col_i:
            raise ValueError(
                f'Start column: {self.start.line_i} follows '
                f'end column: {self.end.col_i} when Chunk begins and ends '
                f'on the same line.')
        self.first_line = self.lines[0]
        self.last_line = self.lines[-1]
        self._index_range: ty.Optional[range] = None

    def __len__(self) -> int:
        return self.index_range.stop

    def __getitem__(self, i: ty.Union[int, 'SourcePos', slice]):
        if isinstance(i, SourcePos):
            return self._char_at_pos(i)
        if isinstance(i, slice):
            return self._slice(i)
        return self._char_at_index(i)

    def __iter__(self):
        if self.first_line is self.last_line:
            line_s = self.first_line.s(self.form)
            for c in line_s[self.start.col_i:self.end.col_i]:
                yield c
            return
        for line in self.lines:
            line_s = line.s(self.form)
            if line is self.first_line:
                s = line_s[self.start.col_i:]
            elif line is self.last_line:
                s = line_s[:self.end.col_i]
            else:
                s = line_s
            for c in s:
                yield c

    def pos(self, line_i: int, col_i: ty.Union[str, int] = 0) -> 'SourcePos':
        if isinstance(col_i, str):
            if col_i == 'end':
                col_i = len(self.file_content.lines[line_i].s(self.form))
            else:
                raise ValueError(f'Unknown column index keyword: {col_i}')
        return SourcePos(self.file_content, line_i, col_i, self.form)

    def line(self, pos: 'SourcePos') -> 'Line':
        return self.file_content.lines[pos.line_i]

    def tokenize(self, regex: str = r"[\w0-9]+") -> ty.Set[str]:
        tokens: ty.Set[str] = set()
        for line in self.lines:
            for token in re.findall(regex, line.s(self.form)):
                tokens.add(token)
        return tokens

    def find_pair(self, start_pos: 'SourcePos') -> 'SourcePos':
        """
        Finds paired closing bracket for the bracket which exists at
        the passed start position.

        :param start_pos: SourcePos
        :return: SourcePos
        """
        if not self[start_pos] in BRACKETS.keys():
            raise ValueError(
                f'Expected bracket in {BRACKETS.keys()} at '
                f'start_pos: {start_pos}. Got: {self[start_pos]}')
        sub_chunk = self[start_pos:]
        depth = 0
        begin_char = self[start_pos]
        end_char = BRACKETS[begin_char]
        for i, c in enumerate(sub_chunk):
            if c == begin_char:
                depth += 1
            elif c == end_char:
                depth -= 1
                if depth == 0:
                    return start_pos + i
        else:
            raise ParsingException(
                f'No end to bracket at {start_pos} found in {self}.')

    @property
    def index_range(self) -> range:
        if self._index_range is None:
            # populate sorted dict?
            assert isinstance(self.start, SourcePos)
            assert isinstance(self.end, SourcePos)
            size_sum = sum(len(line.s(self.form)) for line in self.lines)
            size_sum -= self.start.col_i
            size_sum -= len(self.lines[self.end.line_i].s(self.form)) - \
                self.end.col_i
            self._index_range = range(size_sum)
        assert isinstance(self._index_range, range)
        return self._index_range

    @property
    def lines(self) -> 'Lines':
        return self.Lines(self)

    @property
    def content_hash(self) -> int:
        return iter_hash((s[:-1] if s.endswith('\n') else s)
                         for s in self.line_strings)

    @property
    def line_strings(self):
        line_s = ''
        for c in self:
            line_s += c
            if c == '\n':
                yield line_s
                line_s = ''

    @property
    def start(self) -> 'SourcePos':
        return self._start

    @property
    def end(self) -> 'SourcePos':
        return self._end

    def _slice(self, chunk_slice: slice):
        if chunk_slice.step:
            raise ValueError('Chunk cannot be sliced using step argument.')
        start = chunk_slice.start or self.start
        stop = chunk_slice.stop or self.end
        return Chunk(self.file_content, start, stop)

    def _char_at_pos(self, pos: 'SourcePos') -> str:
        if not self.start.line_i <= pos.line_i <= self.end.line_i:
            raise IndexError(
                f'Line index {pos.line_i} outside chunk lines: '
                f'{self.start.line_i} to {self.end.line_i}')
        if pos.line_i == self.start.line_i and pos.col_i < self.start.col_i:
            raise IndexError(
                f'Column index {pos.col_i} precedes chunk start index: '
                f'{self.start.col_i}')
        if pos.line_i == self.end.line_i and pos.col_i >= self.end.col_i:
            raise IndexError(
                f'Column index {pos.col_i} does not precede chunk end '
                f'index: {self.end.col_i}')
        return self.file_content.lines[pos.line_i].s(self.form)[pos.col_i]

    def _char_at_index(self, i: int) -> str:
        if i < 0:
            i += len(self)
        if i not in self.index_range:
            raise IndexError(
                f'Index: {i} is outside valid range. '
                f'Chunk has len: {len(self)}')
        # Use sorted dict to accelerate line lookup?
        assert isinstance(self.start, SourcePos)
        search_i = 0
        for line in self.lines:
            if search_i + len(line.s(self.form)) > i:
                containing_line = line
                relative_col = i - search_i
                break
            search_i += len(line.s(self.form))
        else:
            raise RuntimeError('This should not be reached.')
        if containing_line is self.lines[0]:
            line_col = relative_col + self.start.col_i
        else:
            line_col = relative_col
        return containing_line.s(self.form)[line_col]

    def __str__(self):
        s = ''
        if self.first_line is self.last_line:
            line_s = self.first_line.s(self.form)
            return line_s[self.start.col_i:self.end.col_i]
        for line in self.lines:
            line_s = line.s(self.form)
            if line is self.first_line:
                s += line_s[self.start.col_i:]
            elif line is self.last_line:
                s += line_s[:self.end.col_i]
            else:
                s += line_s
        return s

    def __repr__(self) -> str:
        return f'Chunk[s: {str(self)}]'

    class Lines:
        def __init__(self, chunk: 'Chunk') -> None:
            self.chunk = chunk

        def __len__(self) -> int:
            return self.chunk.end.line_i - self.chunk.start.line_i + 1

        def __getitem__(self, i: int) -> 'Line':
            if i < 0:
                i += len(self)
            if not 0 <= i < len(self):
                raise IndexError(f'Invalid index: {i}. '
                                 f'{len(self)} lines in Chunk.')
            return self.chunk.file_content.lines[i + self.chunk.start.line_i]

        # noinspection PyTypeChecker
        def __iter__(self) -> ty.Iterable['Line']:
            assert isinstance(self.chunk.start, SourcePos)
            assert isinstance(self.chunk.end, SourcePos)
            end_i = self.chunk.end.line_i
            if end_i is None:
                end_i = len(self.chunk.file_content.lines)
            else:
                end_i += 1
            for i in range(self.chunk.start.line_i, end_i):
                yield self.chunk.file_content.lines[i]


#######################################################################
# Source Components

# Define type alias
SourcePosI = ty.Tuple[ty.Optional[int], ty.Optional[int]]


class Component:
    """
    Base class for code units

    Component instances represent a specific occurrence of a type,
    declaration, definition, etc in code.

    Parent to: Preprocessor, Statement, FuncDec, FuncDef, ClassDec,
        ClassDef, and Block.
    """
    def __init__(
            self,
            file_content: ty.Union['SourceContent', 'Chunk'],
            start: SourcePosI = None,
            end: ty.Optional[SourcePosI] = None
    ) -> None:
        """
        Creates a new component from the passed area of source.

        :param file_content: SourceContent for file that
                    contains Component.
        :param start: SourcePos. Indices may be negative.
        :param end: SourcePos. Indices may be negative.
        """
        if isinstance(file_content, Chunk):
            self.chunk = file_content
        else:
            self.chunk = Chunk(file_content, start, end)
        self._tokens: ty.Optional[ty.Set[str]] = None

    @classmethod
    def create(cls, chunk: 'Chunk', in_func: bool = False) -> 'Component':
        """
        Creates a Component from a passed position in source.
        :return: Component
        """
        # This method should be broken up.
        s = ''
        pos = chunk.start
        component: ty.Optional['Component'] = None
        while pos != chunk.end:
            c = chunk[pos]
            # Check for statement
            if c == ';':
                s += c
                component_chunk = chunk[:pos + 1]
                if in_func:
                    component = MiscStatement(component_chunk)
                else:
                    if 'class' in s:
                        component = CppClassDeclaration(component_chunk)
                    elif 'using' in s:
                        # noinspection PyTypeChecker
                        component = UsingStatement.create(
                            component_chunk, in_func)
                    elif '()' in s:
                        component = FunctionDeclaration(component_chunk)
                break
            # Check for preprocessor directive
            elif pos.col_i == 0 and chunk.line(pos).stripped.startswith('#'):
                component = PreprocessorComponent.create(chunk[pos:])
                break
            elif c in string.whitespace:
                pass
            elif c == '<':
                pos = chunk.find_pair(pos)
                s += '<>'  # Leave out template internals.
            elif c == '(':
                pos = chunk.find_pair(pos)
                s += '()'  # Leave out argument internals.
            elif c == '[':
                pos = chunk.find_pair(pos)
                s += '[]'  # Leave out capture internals.
            elif c == '{':
                pos = chunk.find_pair(pos)
                if 'class' in s:
                    # Ensure class definition is followed by
                    # a semi-colon.
                    for trailing_c in chunk[pos:]:
                        if trailing_c == ';':
                            break
                        if trailing_c not in string.whitespace:
                            raise ParsingException(
                                'Class definition seems to be missing'
                                f'semi-colon in {chunk[:pos]}. Unexpected '
                                'character found after class: '
                                f'{repr(trailing_c)}'
                            )
                        pos += 1
                    else:
                        raise ParsingException(
                            'No semi-colon found after class in '
                            f'{chunk[:pos]}')
                    component = CppClassDefinition(chunk[:pos + 1])
                    break
                if s.endswith('()'):  # Function
                    if in_func and '[]' not in s:
                        raise ParsingException(
                            'Seemed to find function definition within'
                            'another function definition in '
                            f'{chunk[:pos + 1]}')
                    component = FunctionDefinition(chunk[:pos + 1])
                    break
                # Other occurrences of curly brackets are ignored.
            else:
                s += c
            pos += 1
        if not component:
            raise ComponentCreationError(f'No component found in {chunk}')
        return component

    @property
    def tokens(self) -> ty.Set[str]:
        if self._tokens is None:
            self._tokens = self.chunk.tokenize()
        assert isinstance(self._tokens, set)
        return self._tokens

    @property
    def used_constructs(self) -> ty.Dict[str, 'Construct']:
        """
        Retrieves dict of constructs used by the Component.

        :return: dict of Constructs.
        :rtype: Dict[str, Construct]
        """
        return {name: Construct(name) for name in self.tokens}

    @property
    def declared_constructs(self) -> ty.Dict[str, 'Construct']:
        """
        Retrieves dict of constructs which are declared by
        this component.
        :return: dict of Constructs
        :rtype: Dict[str, Construct]
        """
        return {}

    @property
    def defined_constructs(self) -> ty.Dict[str, 'Construct']:
        """
        Retrieves dict of constructs which are defined by
        this component.
        :return: dict of Constructs
        :rtype: Dict[str, Construct]
        """
        return {}

    @property
    def sub_components(self) -> ty.List['Component']:
        """
        Gets collection of other components contained within
        the Component.
        :return: collection of Components
        :rtype: Collection[Component]
        """
        return []


class Block(Component):
    """

    """

    def __init__(
            self,
            file_content: 'SourceContent',
            start: 'SourcePosI' = None,
            end: ty.Optional['SourcePosI'] = None
    ) -> None:
        super().__init__(file_content, start, end)
        self._sub_components: ty.Optional[ty.List['Component']] = None

    @property
    def sub_components(self) -> ty.List['Component']:
        if self._sub_components is None:
            self._sub_components = []
            pos = self.chunk.start
            if self.chunk[pos] == '{':
                pos += 1
            try:
                component = Component.create(self.chunk[pos:])
            except ComponentCreationError:
                pass  # Stop generating components
            else:
                self._sub_components.append(component)
        assert isinstance(self._sub_components, list)
        return self._sub_components


class PreprocessorComponent(Component):
    @classmethod
    def create(cls, chunk: 'Chunk', in_func: bool = False) -> 'Component':
        """
        Create pre-processor macro component.

        :param chunk: Chunk
        :param in_func: Whether component exists within a
                    function definition. Has no effect. Included for
                    compatibility with parent class' method.
        :return: PreprocessorComponent
        """
        # Check that passed chunk appears to contain a pre
        # processor directive.
        if not chunk.first_line.stripped.startswith('#'):
            raise ValueError(
                'Invalid chunk passed. '
                'Expected chunk to start with \'#\'')

        # First find end of preprocessor
        for line in chunk.lines:
            if not line.stripped[:-1].endswith('\\'):
                # noinspection PyTypeChecker
                end = chunk.pos(line.index, 'end')
                break
        else:
            raise ParsingException(
                f'No end to macro starting at {chunk.start} found.')
        pre_processor_chunk = Chunk(chunk.file_content, chunk.start, end)
        return PreprocessorComponent(pre_processor_chunk)


class MiscStatement(Component):
    """
    Component containing a miscellaneous statement within a function.
    """


class FunctionDeclaration(Component):
    """
    Component containing the declaration of a function.

    Initializing a variable can also be categorized as function
    declarations, as without knowing details of types,
    "a b();" could either be a declaration of a function that returns
    "a" from a function called "b", or an instantiation of variable "b"
    of type "a". In either case, a construct named "b" has been
    declared, and so the effect should be the same.
    """


class MemberFunctionDeclaration(Component):
    """
    Component containing the declaration of a function.

    Initializing a variable can also be categorized as function
    declarations, as without knowing details of types,
    "a b();" could either be a declaration of a function that returns
    "a" from a function called "b", or an instantiation of variable "b"
    of type "a". In either case, a construct named "b" has been
    declared, and so the effect should be the same.
    """


class CppClassDeclaration(Component):
    """
    Component containing the declaration of a C++ class.
    """


class FunctionDefinition(Component):
    """
    Component containing the definition of a function.
    """


class MemberFunctionDefinition(Component):
    """
    Component containing the definition of a function.
    """


class CppClassDefinition(Component):
    """
    Component containing the definition of a C++ class.
    """


class UsingStatement(Component):
    """
    Component storing a using definition or declaration.
    """
    @classmethod
    def create(cls, chunk: 'Chunk', in_func: bool = False) -> 'Component':
        return UsingStatement(chunk)


#######################################################################
# Source Constructs


class Construct:
    """
    """
    _constructs = {}

    def __new__(cls, name: str) -> 'Construct':
        try:
            construct = cls._constructs[name]
        except KeyError:
            construct = cls._constructs[name] = object.__new__(cls)
        return construct

    def __init__(self, name: str) -> None:
        if hasattr(self, '_initialized'):
            return
        self._name = name
        self._initialized = True
        self._dep_names: ty.Set[str] = set()
        self._declaration_dep_names: ty.Set[str] = set()

    @classmethod
    def clear(cls) -> None:
        cls._constructs.clear()

    @property
    def name(self) -> str:
        """
        Gets name of Construct. Will be used as a unique key for
        this construct.

        :return: unique name for construct.
        :rtype: Set[str]
        """
        raise NotImplementedError

    @property
    def status(self) -> 'Status':
        return

    @property
    def declaration_status(self) -> 'Status':
        return

    @property
    def dependencies(self) -> ty.Dict[str, 'Construct']:
        """
        Returns dict of all constructs that this construct depends on;
        if any of the dependencies have changed, this Construct is
        considered to have changed as well.

        When doubt exists of whether a construct is a true dependency,
        it should be included, to err on the side of correct
        build output.

        :return: set containing the names of all constructs this
                    Construct depends on.
        :rtype Set[str]
        """
        raise NotImplementedError

    @property
    def declaration_dependencies(self) -> ty.Dict[str, 'Construct']:
        """
        Returns dict of all constructs on whose declaration this
        construct depends on. Declaration dependencies will cause this
        construct to rebuild only if their declaration has changed.
        Changes to their definitions will not cause this construct
        to rebuild.

        When doubt exists of whether a construct is a true dependency,
        it should be included, to err on the side of correct
        build output.

        :return: set containing the names of all constructs this
                    Construct depends on.
        :rtype Set[str]
        """
        raise NotImplementedError


def iter_hash(gen: ty.Iterable[str], accept_none: bool = False) -> int:
    """
    Hashes content of iterable.

    Intended to be used to parse line content.

    :param gen: Iterable[Hashable]
    :param accept_none: If true, throws ValueError if None is received.
    :return: int hash whose absolute value is < system max-size.
    :rtype: int
    :raises ValueError if None is received and accept_none is False.
    """
    prime = 31
    result: int = 1
    for s in gen:
        if not accept_none and s is None:
            raise ValueError(
                'None received. Enable accept_none if this is expected.')
        s_hash = int(hashlib.md5(s.encode()).hexdigest(), 16)
        result = (result * prime + s_hash) % sys.maxsize
    return result


#######################################################################


def verbose(*args, **kwargs):
    if verbose_opt:
        print(*args, **kwargs)


def clear() -> None:
    SourceFile.clear()
    Construct.clear()


def main():
    global verbose_opt
    parser = argparse.ArgumentParser(
        description='Run Zen to focus compilation')
    parser.add_argument('task')
    parser.add_argument('build_dir')
    parser.add_argument('-v', '--verbose', action='store_true')
    user_args = parser.parse_args()
    build_dir = BuildDir(user_args.build_dir)
    if user_args.task == 'meditate':
        build_dir.meditate()
    elif user_args.task == 'remember':
        build_dir.remember()
    verbose_opt = user_args.verbose


verbose_opt = False


if __name__ == '__main__':
    main()
