"""
    '--------____________________________--------'
    |    |              -ZEN-               |    |
    |____|  Reducing recompilation times.   |____|
         '----------------------------------'


   Copyright 2019 TryExceptElse

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

"""

import argparse
import enum
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import string
import subprocess as sub
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
    """
    Change status of a SourceFile, CompileObject, or Target.
    """
    UNCHECKED = 1
    NO_CHANGE = 2
    MINOR_CHANGE = 3
    CHANGED = 4


class TargetType(enum.Enum):
    EXECUTABLE = 1
    STATIC_LIB = 2
    SHARED_LIB = 3
    UNKNOWN = 4


IPath = ty.Union[str, Path, os.PathLike]


LIB_TYPES = {TargetType.STATIC_LIB, TargetType.SHARED_LIB}

HEADER_EXT = '.h', '.hpp', '.hh', '.hxx'

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

    def __init__(self, path: IPath) -> None:
        """
        Initialize BuildDir instance for a cmake build directory.
        :param path: Path-like pointing to build directory.
        """
        self.path = Path(path)
        self.targets = self._find_targets()
        self.targets_by_path = {
            target.file_path.absolute(): target
            for target in self.targets.values()
        }
        self.sources = self._find_sources()
        self._hash_cache: ty.Optional[ty.Dict[str, int]] = None

    def meditate(self) -> None:
        """
        Minimizes number of objects and targets that need to
        be rebuilt.
        :return: None
        """
        [target.meditate() for target in self.targets.values()]

    def remember(self) -> None:
        """
        Stores information about the current form of the source code,
        so that it may later be determined later what has been changed
        substantially enough to require recompilation.
        :return: None
        """
        for dep in self.sources:
            dep.remember(self.hash_cache)
        for target in self.targets.values():
            target.remember()
        with self.cache_path.open('w') as f:
            json.dump(self.hash_cache, f)

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
        """
        Finds SourceFiles that are used by any target in this build.
        :return: Set[SourceFile]
        """
        dependencies = set()
        for target in self.targets.values():
            for compile_object in target.objects:
                for dependency in compile_object.sources:
                    dependencies.add(dependency)
        return dependencies

    @property
    def hash_cache(self) -> ty.Dict[str, int]:
        """
        Gets SourceCache storing previously compiled values.
        :return: Cache dict.
        """
        if self._hash_cache is None:
            try:
                with self.cache_path.open() as f:
                    self._hash_cache = json.load(f)
            except FileNotFoundError:
                self._hash_cache = {}
        return self._hash_cache

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
        """
        Determines whether Target rebuild can be avoided based on
        analysis of changes in the source code.

        If it is determined that changes have been made to the target
        that do not change the observable behavior of programs
        conforming to basic expectations, then target re-compilation
        will be avoided.

        :return: None
        """
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

    def remember(self) -> None:
        """
        Stores information about the current form of the target,
        so that it may later be determined later what has been changed
        substantially enough to require recompilation.
        :return: None
        """
        for obj in self.objects:
            obj.remember()

    def avoid_build(self) -> None:
        """
        Un-Marks this target for re-linking.
        This method should only be called if target is known.
        :return: None
        """
        sub.run(['touch', '-c', str(self.file_path.absolute())], check=True)

    @staticmethod
    def type_from_path(path: ty.Union[str, Path]) -> TargetType:
        """
        Determine the TargetType from the name of the file
        produced by the target.
        :param path: 
        :return: 
        """
        ext = os.path.splitext(path)[1]
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
        with depend_internal_path.open() as f:
            d: ty.Dict[Path, ty.List[Path]] = {}
            deps: ty.List[Path] = []
            for line in f.readlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.endswith('.o'):
                    deps = d[Path(self.build_dir.path, stripped)] = []
                elif line.startswith(' '):
                    deps.append(Path(self.build_dir.path, stripped).resolve())
        return [CompileObject(o, deps, self.build_dir) for
                o, deps in d.items()]

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
        return path, target_type

    def _find_dependencies(self) -> ty.Set[Path]:
        """
        Produces set of dependency files that are relied upon by
        this target.

        :return: set of Path objects each pointing to a file while this
                    target depends on.
        :rtype: Set[Path]
        """
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
        return self.file_path.stat().st_mtime

    @property
    def other_status(self) -> Status:
        """
        Gets status of other files that the target relies upon, such as
        make files. Since these files are not parsed, their status will
        only ever be NO_CHANGE or CHANGED.

        :return: Status.NO_CHANGE or Status.CHANGED
        :rtype Status
        """
        if any(other.stat().st_mtime > self.m_time for
               other in self.other_dependencies):
            return Status.CHANGED
        return Status.NO_CHANGE

    @property
    def lib_dependencies(self) -> ty.Set['Target']:
        """
        Finds library Targets that this Target relies upon.
        :return: Library Targets.
        :rtype Set[Target]
        """
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
            if os.path.splitext(str(dep))[1] == '.o':
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
        self._used_content_hash: ty.Optional[int] = None

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

        try:
            if self._has_code_changes() and self._has_used_content_change():
                self.status = Status.CHANGED
            else:
                self.status = Status.MINOR_CHANGE
                self.avoid_build()
        except ParsingException:
            self.status = Status.CHANGED

    def remember(self) -> None:
        """
        Remembers used parts of sources, so that differences can be
        found the next time zen is run.
        :return: None
        """
        # Store constructs
        try:
            constructs = self.create_constructs()
            for construct in constructs:
                cache_k = self.construct_hex(construct.name)
                self.build_dir.hash_cache[cache_k] = construct.content_hash
        except ParsingException:
            # It is always ok to not store a file hash.
            # This simply causes the object to be treated as if it had
            # never been seen before, as if it were the first build.
            pass

    def _has_code_changes(self) -> bool:
        """
        Checks whether any source file dependencies have had changes,
        not including whitespace or comments.
        :return: True if code changes are found in any source file.
        :rtype: bool
        """
        for source in self.sources:
            if source.substantive_changes(self.build_dir.hash_cache):
                return True
        return False

    def _has_used_content_change(self):
        """
        Checks whether used content has changed.
        :return: True if used content has changed.
        :rtype: bool
        """
        graph: ConstructGraph = self.create_constructs()
        change_cache: ty.Dict['Construct', bool] = {}

        def get_cached_hash(construct: 'Construct') -> int:
            k = self.construct_hex(construct.name)
            return self.build_dir.hash_cache[k]

        def is_changed(construct: 'Construct') -> bool:
            if construct not in change_cache:
                for dep in construct.dependencies:
                    if is_changed(dep):
                        changed = True
                        break
                else:
                    try:
                        cached_hash = get_cached_hash(construct)
                    except KeyError:
                        changed = True
                    else:
                        changed = cached_hash != construct.content_hash
                change_cache[construct] = changed
            return change_cache[construct]

        # Find changes
        # Look through each component of each definition file to see if
        # any component uses a Construct which has changed.
        for source in self.sources:
            if source.is_header:
                continue
            if source.substantive_changes(self.build_dir.hash_cache):
                return True
            for component in source.content.component.recursive_components:
                for used_construct in component.used_constructs(
                        graph.constructs).values():
                    if is_changed(used_construct):
                        return True
        return False

    def avoid_build(self) -> None:
        """
        Un-Marks this object for re-compilation.
        :return: None
        """
        sub.run(['touch', '-c', str(self.path.absolute())], check=True)

    @property
    def m_time(self):
        """
        Gets modification time of compiled object.
        :return: float time in seconds since epoch.
        """
        return self.path.stat().st_mtime

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

    def create_constructs(self) -> 'ConstructGraph':
        """
        Gets constructs produced by sources used by CompileObject.
        :return: ConstructGraph.
        :rtype ConstructGraph.
        """
        graph = ConstructGraph()
        for source in self.sources:
            for component in source.content.component.recursive_components:
                for name, content in component.construct_content.items():
                    graph.get(name, create=True).add_content(content)

        return graph

    def construct_hex(self, name: str) -> str:
        """
        Gets the hash hex for a Construct of the passed name.
        :param name: str name of Construct.
        :return: hex version of the hash code.
        :rtype: str
        """
        k = f'[{str(self.path)}][CONSTRUCT][{name}]'
        return hashlib.md5(str(k).encode()).hexdigest()

    def __repr__(self) -> str:
        return f'Object[{os.path.basename(str(self.path))}]'


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
        """
        Clears all source file instances that have been created.
        :return: None
        """
        cls._source_files.clear()

    def substantive_changes(self, cache: ty.Dict[str, int]) -> bool:
        """
        Check for changes against cache.

        :param cache: SourceCache
        :return: bool which is True if changes have occurred.
        """
        try:
            return self.stripped_hash != cache[self.hex]
        except KeyError:
            return True

    def remember(self, cache: ty.Dict[str, int]) -> None:
        """
        Stores information about the current form of the source file,
        so that changes may be detected.

        :param cache: cache dictionary.
        :return: None
        """
        cache[self.hex] = self.stripped_hash

    @property
    def is_header(self) -> bool:
        """
        Returns whether or not SourceFile is a header.
        :return: bool true if SourceFile is a header file.
        """
        return self.path.suffix in HEADER_EXT

    @property
    def m_time(self) -> float:
        """
        Gets modification time of source file.
        :return: float time in seconds since epoch.
        """
        return self.path.stat().st_mtime

    @property
    def content(self) -> 'SourceContent':
        """
        Gets SourceContent object for accessing information about the
        code contained within the SourceFile.
        :return: SourceContent instance representing
                    SourceFile's content.
        :rtype: SourceContent
        """
        if self._content is None or self.m_time > self._access_time:
            self._access_time = time.time()
            with self.path.open() as f:
                self._content = SourceContent(f)
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
        return f'SourceFile[{os.path.basename(str(self.path))}]'


#######################################################################
# Source analysis


class SourceContent:
    """
    Class representing the content of a header or definition file.
    """
    path: Path
    name: ty.Optional[str]
    lines: ty.List['Line']
    _raw_hash: ty.Optional[int]

    def __init__(self, content: ty.Union[str, ty.TextIO]) -> None:
        if isinstance(content, str):
            self.lines = self._lines_from_str(content)
            self.name = None
        else:
            self.lines = self._lines_from_f(content)
            self.name = Path(content.name).name
        self._raw_hash: ty.Optional[int] = None
        self._stripped_comments: bool = False
        self._component: ty.Optional['Block'] = None
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
            if line.raw.endswith('\n') and not uncommented.endswith('\n'):
                uncommented += '\n'
            line.uncommented = uncommented
        self._stripped_comments = True

    def start_pos(self, form: 'SourceForm') -> 'SourcePos':
        """
        Gets SourcePos pointing to the beginning of the SourceContent.
        :param form: SourceForm for the produced SourcePos.
        :return: SourcePos
        """
        return SourcePos(self, 0, 0, form)

    def end_pos(self, form: 'SourceForm') -> 'SourcePos':
        """
        Gets SourcePos pointing to the end of the SourceContent.
        :param form: SourceForm for the produced SourcePos.
        :return: SourcePos
        """
        return SourcePos(self, -1, len(self.lines[-1].s(form)), form)

    @property
    def has_uncommented(self) -> bool:
        """
        Whether SourceContent's lines' uncommented forms have been
        produced and stored.
        :return: bool which is True if lines' uncommented forms have
                    been produced and stored.
        """
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
        """
        Gets Component containing entirety of the source's content.
        :return: Block Component
        :rtype: Block
        """
        if self._component is None:
            self._component = Block(self)
        assert isinstance(self._component, Block)
        return self._component

    @staticmethod
    def _lines_from_str(content: str) -> ty.List['Line']:
        return [Line(i, line_s) for i, line_s in
                enumerate(content.splitlines(True))]

    @staticmethod
    def _lines_from_f(f: ty.TextIO) -> ty.List['Line']:
        return [Line(i, line_s) for i, line_s in enumerate(f.readlines())]

    def __repr__(self) -> str:
        return f'SourceContent[{self.name}]'


class Line:
    """
    Data storage class for storing information about a line of source.
    """

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
                f'Uncommented value of {repr(self)} has not been set.')
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
        """
        Gets form of line with all unneeded whitespace removed.
        Whitespace that separates tokens in the line are left
        in place.

        :return: str of line's content without comments or
                    extra whitespace.
        """
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
        # Produces Line[i: index, s: preview + '...' if preview runs over]
        return f'Line[i: {self.index}, ' \
               f'\'{self.raw[:preview_len]}' \
               f'{"..." if len(self.raw) > preview_len else ""}\']'


class SourceForm(enum.Enum):
    """
    Enum that indicates a form of source content.

    Used by SourcePos, Chunk, and elsewhere to indicate what form of
    the source code they represent.
    """
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
        """
        Create new SourcePos

        :param file_content: SourceContent instance.
        :param line_i: Line index int.
        :param col_i: Column index int.
        :param form: Form of source code which is referenced.
                    Positions will differ depending on the SourceForm
                    which they use.
        """
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
        """
        Produces a new SourcePos object that has a char index n higher
        than the SourcePos on which this method was called.

        :param n: int
        :return: newly created SourcePos.
        :raise: ValueError if n is too large (either positive or
                    negative) to be added to the SourcePos.
        """
        if n < 0:
            return self - abs(n)
        original_n = n
        line = self.file_content.lines[self.line_i]
        remaining_chars = len(line.s(self.form)) - self.col_i
        if n <= remaining_chars:
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
            if n <= line_chars:
                return SourcePos(self.file_content, line.index, n, self.form)
            n -= line_chars
        else:
            raise ValueError(
                f'Cannot add {original_n} to {self}. '
                f'{original_n} is too large.')

    def __sub__(self, n: int) -> 'SourcePos':
        """
        Produces a new SourcePos object that has a char index n lower
        than the SourcePos on which this method was called.
        
        :param n: int
        :return: newly created SourcePos.
        :raise: ValueError if n is too large (either positive or
                    negative) to be subtracted from the SourcePos.
        """
        if n < 0:
            return self + abs(n)
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

    def __hash__(self) -> int:
        """
        Custom hash for SourcePos that allows equivalent SourcePos
        instances to have equal hashes.
        :return: int
        """
        return hash((self.file_content, self.line_i, self.col_i, self.form))

    def __eq__(self, other) -> bool:
        """
        Compares SourcePos to another.

        Source positions are considered equal if they point to the same
        position of the same file content, and have the same form as
        each other (raw, uncommented, or stripped).

        :param other: SourcePos to compare with.
        :return: True if both SourcePos are equivalent.
        """
        try:
            return all((
                self.file_content == other.file_content,
                self.line_i == other.line_i,
                self.col_i == other.col_i,
                self.form == other.form
            ))
        except AttributeError:
            return False

    @property
    def next_line_pos(self) -> 'SourcePos':
        """
        Returns a SourcePos pointing to the first character in the next
        line following the SourcePos.
        :return: SourcePos pointing to beginning of the next line.
        """
        return SourcePos(self.file_content, self.line_i + 1, 0, self.form)

    def _normalize_line_i(self, i: int) -> int:
        """
        Produces a 'conventional' non-negative index from the
        passed int.

        If passed integer is negative, an index relative to the first
        line of the file is produced.

        :param i: int index between -len(file_content.lines) and
                    len(file_content.lines) - 1.
        :return: int index between 0 and len(file_content.lines) - 1.
        :raises IndexError if passed integer is outside valid range.
        """
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
        """
        Produces a 'conventional' non-negative index from the
        passed column index.

        If passed integer is negative, a positive index relative to
        column 0 is produced.

        :param i: int index between (-line len) and (line len - 1).
        :return: int index between 0 and line len - 1.
        :raises IndexError if passed integer is outside valid range.
        """
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
            start: ty.Optional['SourcePos'] = None,
            end: ty.Optional['SourcePos'] = None,
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
        """
        Gets length of Chunk in chars.
        :return: Number of chars in Chunk.
        """
        return self.index_range.stop

    def __getitem__(
            self, i: ty.Union[int, 'SourcePos', slice]
    ) -> ty.Union[str, 'Chunk']:
        """
        Gets character at passed position, or returns a subset Chunk
        from a slice.

        :param i: index, SourcePos, or slice.
        :return: char str if index or SourcePos is passed, or Chunk
                    if slice is passed.
        :rtype: Union[str, Chunk]
        """
        if isinstance(i, SourcePos):
            return self._char_at_pos(i)
        if isinstance(i, slice):
            return self._slice(i)
        return self._char_at_index(i)

    def __iter__(self) -> ty.Iterable[str]:
        """
        Iterate over all characters in Chunk.
        :return: str iterable yielding each character in Chunk.
        """
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
        """
        Gets SourcePos representing a position within source.

        :param line_i: int line index in source.
                    Not relative to start of Chunk.
        :param col_i: int col index or position keyword ('end')
                    Always relative to line start, not start of Chunk.
        :return: SourcePos for the same source file and form as Chunk,
                    and with the passed line and column indices.
        :rtype: SourcePos
        """
        if isinstance(col_i, str):
            if col_i == 'end':
                col_i = len(self.file_content.lines[line_i].s(self.form))
            else:
                raise ValueError(f'Unknown column index keyword: {col_i}')
        return SourcePos(self.file_content, line_i, col_i, self.form)

    def line(self, pos: 'SourcePos') -> 'Line':
        """
        Returns the line within the Chunk that contains the passed
        source pos.

        The column index of the passed SourcePos is ignored.

        :param pos: SourcePos which points to a position within the
                    line to be returned.
        :return: Line which contains the passed SourcePos.
        """
        return self.file_content.lines[pos.line_i]

    def tokenize(self, regex: str = r"[\w0-9]+") -> ty.List[str]:
        """
        Produces a list of the tokens contained within the Chunk.
        :param regex: If passed, the regex that will be used to
                    find chunks.
        :return: list of token str.
        :rtype List[str]
        """
        tokens: ty.List[str] = []
        if self.start.line_i == self.end.line_i:
            return re.findall(regex, str(self))
        for line in self.lines:
            s = line.s(self.form)
            if line == self.lines[0]:
                s = s[self.start.col_i:]
            elif line == self.lines[-1]:
                s = s[:self.end.col_i]
            tokens += re.findall(regex, s)
        return tokens

    def find_pair(
            self,
            start_pos: 'SourcePos',
            allow_semicolon: bool = True
    ) -> 'SourcePos':
        """
        Finds paired closing bracket for the bracket which exists at
        the passed start position.

        :param start_pos: SourcePos
        :param allow_semicolon: if False, a ParsingException is thrown
                    upon encountering a semi-colon before the
                    close-bracket.
        :return: SourcePos
        :raise ParsingException if Unexpected Syntax is encountered.
        """
        if not self[start_pos] in BRACKETS.keys():
            raise ValueError(
                f'Expected bracket in {BRACKETS.keys()} at '
                f'start_pos: {start_pos}. Got: {self[start_pos]}')
        sub_chunk = self[start_pos:]
        depth = 0
        begin_char = self[start_pos]
        end_char = BRACKETS[begin_char]
        pos = sub_chunk.start
        while True:
            try:
                c = sub_chunk[pos]
            except IndexError:
                raise ParsingException(
                    f'No end to bracket at {start_pos} found in {self}.')
            if c == begin_char:
                depth += 1
            elif c == end_char:
                depth -= 1
                if depth == 0:
                    return pos
            if c == ';' and not allow_semicolon:
                raise ParsingException(
                    f'No end to bracket at {start_pos} found in {self}, '
                    f'before semicolon was encountered at {pos}')
            elif c in '\'"':
                pos = sub_chunk.find_quote_end(pos)
            pos += 1

    def find_quote_end(self, pos: 'SourcePos') -> 'SourcePos':
        """
        Finds the end quote char of the string that begins at the
        passed position.

        Escaped quotes are skipped, and end quote must match the type
        of quote char which is at the passed position in the chunk.

        :param pos: SourcePos indicating a quote char that
                    begins a string.
        :return: SourcePos indicating the end of the string.
        :rtype SourcePos
        """
        escaped = False
        end_char = self[pos]
        if end_char not in '\'"':
            raise ValueError(
                'Expected start of quote to begin with \' or \" character.')
        for i, c in enumerate(self[pos + 1:]):
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == '\n':
                raise ValueError('End of line encountered while looking for '
                                 f'string end for quote char at {pos}')
            elif c == end_char:
                return pos + i + 1

    def strip(self) -> 'Chunk':
        """
        Returns a new chunk that has had leading and trailing
        whitespace removed.

        :return: Chunk without leading and trailing whitespace.
        :rtype Chunk
        """
        for i, c in enumerate(self):
            if c not in string.whitespace:
                start = i
                break
        else:
            raise ValueError(f'No non-whitespace content in {self}')
        end = len(self) - 1
        while self[end] in string.whitespace:
            end -= 1
        return self[start:end + 1]

    @property
    def index_range(self) -> range:
        """
        Range of valid int indices in chunk.
        :return: range
        """
        if self._index_range is None:
            # populate sorted dict?
            assert isinstance(self.start, SourcePos)
            assert isinstance(self.end, SourcePos)
            size_sum = sum(len(line.s(self.form)) for line in self.lines)
            size_sum -= self.start.col_i
            size_sum -= \
                len(self.file_content.lines[self.end.line_i].s(self.form)) - \
                self.end.col_i
            self._index_range = range(size_sum)
        assert isinstance(self._index_range, range)
        return self._index_range

    @property
    def lines(self) -> 'Lines':
        """
        Returns lines object which serves as a utility for accessing
        lines within Chunk.
        :return: Lines object
        :rtype Lines
        """
        return self.Lines(self)

    @property
    def content_hash(self) -> int:
        """
        Hashes content of Chunk.
        :return: hash int
        :rtype int
        """
        return iter_hash((s[:-1] if s.endswith('\n') else s)
                         for s in self.line_strings)

    @property
    def line_strings(self):
        """
        Yields a string for each line in the chunk, containing
        that line's content in the SourceForm used by the chunk.
        :return: str Iterator
        """
        line_s = ''
        for c in self:
            line_s += c
            if c == '\n':
                yield line_s
                line_s = ''

    @property
    def start(self) -> 'SourcePos':
        """
        Returns a SourcePos pointing to the first character in
        the Chunk.
        :return: SourcePos
        """
        return self._start

    @property
    def end(self) -> 'SourcePos':
        """
        Returns a SourcePos pointing to the last character in
        the Chunk.
        :return: SourcePos
        """
        return self._end

    @property
    def bounds_description(self) -> str:
        """
        Returns human-readable description of chunk bounds.
        :return: description str
        """
        if self.start.line_i == self.end.line_i:
            return f'Line {self.start.line_i}, ' \
                f'Chars {self.start.col_i} to {self.end.col_i}.'
        else:
            return f'Line {self.start.line_i} to line {self.end.line_i}'

    def _slice(self, chunk_slice: slice):
        if chunk_slice.step:
            raise ValueError('Chunk cannot be sliced using step argument.')
        start = chunk_slice.start or self.start
        if chunk_slice.stop is not None:
            stop = chunk_slice.stop
        else:
            stop = self.end
        if isinstance(start, int):
            if start < 0:
                start += len(self)
            start = self.start + start
        if isinstance(stop, int):
            if stop < 0:
                stop += len(self)
            stop = self.start + stop
        return Chunk(self.file_content, start, stop)

    def _char_at_pos(self, pos: 'SourcePos') -> str:
        """
        Gets character at the position identified by the
        passed SourcePos.
        :param pos: Position in SourceContent.
        :return: char str
        :rtype: str
        :raises IndexError if SourcePos outside Chunk.
        """
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
        """
        Helper method to retrieve character at passed index
        from Chunk.

        :param i: int index of character to be retrieved.
        :return: char str.
        :rtype: str
        :raises IndexError if index is outside Chunk.
        """
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
            usable_len = len(line.s(self.form))
            if line == self.first_line:
                usable_len -= self.start.col_i
            if search_i + usable_len > i:
                containing_line = line
                relative_col = i - search_i
                break
            search_i += usable_len
        else:
            raise RuntimeError('This should not be reached.')
        if containing_line is self.lines[0]:
            line_col = relative_col + self.start.col_i
        else:
            line_col = relative_col
        return containing_line.s(self.form)[line_col]

    def __str__(self):
        """
        Gets str content of chunk.
        :return: str
        """
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
            """
            Returns number of lines in chunk.
            :return: number of lines.
            :rtype int
            """
            return self.chunk.end.line_i - self.chunk.start.line_i + 1

        def __getitem__(self, i: int) -> 'Line':
            """
            Gets item with passed index from Chunk Lines.
            :param i: int index of chunk lines, where 0 is the first
                        line in the Chunk.
            :return: Line at passed index
            :rtype: Line
            """
            if i < 0:
                i += len(self)
            if not 0 <= i < len(self):
                raise IndexError(f'Invalid index: {i}. '
                                 f'{len(self)} lines in Chunk.')
            return self.chunk.file_content.lines[i + self.chunk.start.line_i]

        def __iter__(self) -> ty.Iterable['Line']:
            """
            Returns generator for iterating over all lines in Chunk.
            :return: Line generator
            """
            assert isinstance(self.chunk.start, SourcePos)
            assert isinstance(self.chunk.end, SourcePos)
            end_i = self.chunk.end.line_i
            if end_i is None:
                end_i = len(self.chunk.file_content.lines)
            else:
                end_i += 1
            for i in range(self.chunk.start.line_i, end_i):
                yield self.chunk.file_content.lines[i]


def join_hashes(hash_iterable: ty.Iterable[int]) -> int:
    """
    Join hashes of the passed iterable.
    :param hash_iterable: Iterable[int]
    :return: int
    """
    prime = 31
    result: int = 1
    for sub_hash in hash_iterable:
        result = (result * prime + sub_hash) % (2 ** 127 - 1)
    return result


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
    def hash_generator():
        for s in gen:
            if not accept_none and s is None:
                raise ValueError(
                    'None received. Enable accept_none if this is expected.')
            yield int(hashlib.md5(s.encode()).hexdigest(), 16)
    result = join_hashes(hash_generator())
    assert isinstance(result, int)
    return result


#######################################################################
# Source Components

class ScopeType(enum.Enum):
    GLOBAL = 1
    CLASS = 2
    FUNC = 3


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
            start: 'SourcePos' = None,
            end: ty.Optional['SourcePos'] = None
    ) -> None:
        """
        Creates a new component from the passed area of source.

        :param file_content: SourceContent for file that
                    contains Component.
        :param start: SourcePos. Indices may be negative.
        :param end: SourcePos. Indices may be negative.
        """
        if isinstance(file_content, Chunk):
            self.chunk = file_content.strip()
        else:
            self.chunk = Chunk(file_content, start, end).strip()
        self._tokens: ty.Optional[ty.Set[str]] = None
        self._tags: ty.Optional[ty.Set[str]] = None

    @classmethod
    def create(
            cls, 
            chunk: 'Chunk', 
            scope: 'ScopeType' = ScopeType.GLOBAL
    ) -> 'Component':
        """
        Creates a Component from a passed position in source.
        :return: Component
        """
        # This method should be broken up.
        s = ''
        pos = chunk.start
        component: ty.Optional['Component'] = None
        while True:
            try:
                c = chunk[pos]
            except IndexError:
                raise ComponentCreationError('End of block reached.')
            # Check for label
            # Consider component to be a label when a single ':'
            # appears in s, that is not a class extension or beginning
            # of an initialization.
            if all(('class' not in s,
                    '()' not in s,
                    c != ':',
                    s.endswith(':'),
                    not s.endswith('::'))):
                component = Label(chunk[:pos])
                break
            # Check for statement
            if c == ';':
                s += c
                component_chunk = chunk[:pos + 1]
                if scope == ScopeType.FUNC:
                    component = MiscStatement(component_chunk)
                else:
                    if 'class' in s:
                        component = CppClassForwardDeclaration(component_chunk)
                    elif 'using' in s:
                        component = UsingStatement.create(
                            component_chunk, scope)
                    elif '()' in s:
                        if scope == ScopeType.GLOBAL:
                            component = FunctionDeclaration(component_chunk)
                        elif scope == ScopeType.CLASS:
                            component = \
                                MemberFunctionDeclaration(component_chunk)
                    else:
                        component = MiscStatement(component_chunk)
                break
            # Check for preprocessor directive
            elif pos.col_i == 0 and chunk.line(pos).stripped.startswith('#'):
                component = PreprocessorComponent.create(chunk[pos:])
                break
            elif c in string.whitespace:
                pass
            elif c == '<' and scope != ScopeType.FUNC:
                # If outside function, '<'
                try:
                    pos = chunk.find_pair(pos, allow_semicolon=False)
                    s += '<>'  # Leave out template internals.
                except ParsingException:
                    pass
            elif c == '(':
                pos = chunk.find_pair(pos)
                s += '()'  # Leave out argument internals.
            elif c == '[':
                pos = chunk.find_pair(pos)
                s += '[]'  # Leave out capture internals.
            elif c == '{':
                # Check if brackets are a control block
                prefix_tokens = set(scope_tokens(chunk[:pos]))
                pos = chunk.find_pair(pos)
                if 'namespace' in s:
                    component = NamespaceComponent(chunk[:pos + 1])
                    break
                if 'class' in s:
                    # Ensure class definition is followed by
                    # a semi-colon.
                    for trailing_c in chunk[pos + 1:]:
                        pos += 1
                        if trailing_c == ';':
                            break
                        if trailing_c not in string.whitespace:
                            raise ParsingException(
                                'Class definition seems to be missing'
                                f'semi-colon in {chunk[:pos]}. Unexpected '
                                'character found after class: '
                                f'{repr(trailing_c)}'
                            )
                    else:
                        raise ParsingException(
                            'No semi-colon found after class in '
                            f'{chunk[:pos]}')
                    component = CppClassDefinition(chunk[:pos + 1])
                    break
                if '()' in s:  # Function
                    if any(kw in prefix_tokens for
                           kw in ControlBlock.KEYWORDS):
                        component = ControlBlock(chunk[:pos + 1])
                    elif scope == ScopeType.FUNC and '[]' not in s:
                        raise ParsingException(
                            'Seemed to find function definition within'
                            'another function definition in '
                            f'{chunk[:pos + 1]}')
                    elif scope == ScopeType.GLOBAL:
                        component = FunctionDefinition(chunk[:pos + 1])
                    elif scope == ScopeType.CLASS:
                        component = MemberFunctionDefinition(chunk[:pos + 1])
                    break
                # Other occurrences of curly brackets are ignored.
            else:
                s += c
            try:
                pos += 1
            except ValueError:
                break
        if not component:
            raise ComponentCreationError(f'No component found in {chunk}')
        return component

    @property
    def tokens(self) -> ty.List[str]:
        """
        Gets tokens within the block.
        :return: List[str] of tokens in the component.
        """
        if self._tokens is None:
            self._tokens = self._find_tokens()
        return self._tokens

    @property
    def tags(self) -> ty.Set[str]:
        """
        Finds tags that have been assigned to this component.
        :return: Set of tag strings.
        :rtype: Set[str]
        """
        if self._tags is None:
            if len(self.chunk.lines) == 1:
                return parse_tags(
                    self.chunk.first_line.s(SourceForm.RAW))

            # Find inner components which will disqualify lines from
            # being checked for tags that apply to this component.
            if hasattr(self, 'inner_block'):
                inner_components = itertools.chain(
                    self.sub_components,
                    getattr(self, 'inner_block').sub_components
                )
            else:
                inner_components = self.sub_components

            # Produce set of lines will be checked for tags.
            lines = {line for line in self.chunk.lines}
            for sub_component in inner_components:
                for line in sub_component.chunk.lines:
                    if line in lines:
                        lines.remove(line)

            # Parse lines for tags.
            tags: ty.Set[str] = set()
            for line in lines:
                tags |= parse_tags(line.s(SourceForm.RAW))
            self._tags = tags
        return self._tags

    def used_constructs(
            self,
            constructs: ty.Dict[str, 'Construct']
    ) -> ty.Dict[str, 'Construct']:
        """
        Retrieves dict of constructs used by the Component.

        :return: dict of Constructs.
        :rtype: Dict[str, Construct]
        """
        return {token: constructs[token] for token in self.tokens
                if token in constructs and
                getattr(self, 'name', None) != token}

    @property
    def construct_content(self) -> ty.Dict[str, ty.List['Component']]:
        """
        Gets content provided by the Component for Construct(s).
        :return: dict of content chunks stored by construct name.
        :rtype: Dict[str, List[Chunk]]
        """
        return {}

    @property
    def exposed_content(self) -> ty.List['Chunk']:
        """
        Gets content provided by component which affects compilation
        even if constructs declared or created by the component are
        not used.

        :return: List of chunks used by program regardless of whether
                    constructs modified by this component are used.
        :rtype: List[Chunk]
        """
        return [self.chunk]

    @property
    def sub_components(self) -> ty.List['Component']:
        """
        Gets collection of other components contained within
        the Component.
        :return: collection of Components
        :rtype: Collection[Component]
        """
        return []

    @property
    def recursive_components(self) -> ty.Iterable['Component']:
        """
        Yields all components contained within this
        component, recursively.
        :return: Iterable[Component]
        """
        for component in self.sub_components:
            yield component
            yield from component.recursive_components

    def _find_tokens(self) -> ty.List[str]:
        """
        Method used to find tokens for return by 'tokens' property.
        May be overridden in subclasses without having to re-implement
        the full 'tokens' property.
        :return: List[str]
        """
        return self.chunk.tokenize()


class Block(Component):
    """
    Class representing block of code, such as comprises a part of a
    class declaration or function definition.
    """

    def __init__(
            self,
            file_content: ty.Union['SourceContent', 'Chunk'],
            start: 'SourcePos' = None,
            end: ty.Optional['SourcePos'] = None,
            scope_type: 'ScopeType' = ScopeType.GLOBAL
    ) -> None:
        super().__init__(file_content, start, end)
        self._sub_components: ty.Optional[ty.List['Component']] = None
        self._tags: ty.Optional[ty.Set[str]] = None
        self.scope_type = scope_type

    @property
    def sub_components(self) -> ty.List['Component']:
        """
        Gets collection of other components contained within
        the Component.
        """
        if self._sub_components is None:
            self._sub_components = []
            pos = self.chunk.start
            end = None
            if self.chunk[pos] == '{':
                pos += 1
                if self.chunk[-1] == '}':
                    end = self.chunk.end - 1
            while True:
                try:
                    component = Component.create(
                        self.chunk[pos:end], scope=self.scope_type)
                except ComponentCreationError:
                    break  # Stop generating components
                else:
                    self._sub_components.append(component)
                    pos = component.chunk.end
        return self._sub_components

    def __repr__(self) -> str:
        return f'Block[{self.chunk.bounds_description}]'


class NamespaceComponent(Component):
    """
    Component containing the code that comprises a cpp namespace.
    """
    def __init__(
            self,
            file_content: ty.Union['SourceContent', 'Chunk'],
            start: 'SourcePos' = None,
            end: ty.Optional['SourcePos'] = None,
    ) -> None:
        super().__init__(file_content, start, end)
        self.block = self._find_block()
        self.prefix: 'Chunk' = self.chunk[:self.block.chunk.start]

    def _find_block(self) -> 'Block':
        block_start = find_in_scope('{', self.chunk)
        return Block(self.chunk[block_start:])

    @property
    def sub_components(self):
        return self.block.sub_components

    @property
    def exposed_content(self) -> ty.List['Chunk']:
        return [self.prefix.strip()]

    def _find_tokens(self) -> ty.List[str]:
        return self.prefix.tokenize()


class PreprocessorComponent(Component):
    @classmethod
    def create(
            cls,
            chunk: 'Chunk',
            scope: 'ScopeType' = ScopeType.GLOBAL
    ) -> 'Component':
        """
        Create pre-processor macro component.

        :param chunk: Chunk
        :param scope: Variety of scope that component exists within.
                    Has no effect. Included for
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
                end = chunk.pos(line.index, 'end')
                break
        else:
            raise ParsingException(
                f'No end to macro starting at {chunk.start} found.')
        pre_processor_chunk = Chunk(chunk.file_content, chunk.start, end)
        return PreprocessorComponent(pre_processor_chunk)

    def __repr__(self):
        if len(self.chunk) < 20:
            preview = str(self.chunk)
        else:
            preview = str(self.chunk[:self.chunk.start + 20]) + '...'
        return f'PreprocessorComponent[{preview}]'


class MiscStatement(Component):
    """
    Component containing a miscellaneous statement within a function.
    """

    def __repr__(self):
        if len(self.chunk) < 40:
            preview = str(self.chunk)
        else:
            preview = str(self.chunk[:self.chunk.start + 40]) + '...'
        return f'MiscStatement[{preview}]'


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

    @property
    def name(self) -> str:
        first_parenthesis = find_in_scope('(', self.chunk)
        return scope_tokens(self.chunk[:first_parenthesis])[-1]

    @property
    def construct_content(self) -> ty.Dict[str, ty.List['Component']]:
        return {self.name: [self]}

    @property
    def exposed_content(self) -> ty.List['Chunk']:
        """
        Since function definitions cannot change the operation of a
        program without being used, function declarations have
        no exposed content.
        :return: Empty list.
        """
        return []

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}[{self.name}]'


class MemberFunctionDeclaration(FunctionDeclaration):
    """
    Component containing the declaration of a function.

    Initializing a variable can also be categorized as function
    declarations, as without knowing details of types,
    "a b();" could either be a declaration of a function that returns
    "a" from a function called "b", or an instantiation of variable "b"
    of type "a". In either case, a construct named "b" has been
    declared, and so the effect should be the same.
    """

    exposed_content = Component.exposed_content


class CppClassForwardDeclaration(Component):
    """
    Component containing the declaration of a C++ class.
    """
    def __init__(
            self,
            file_content: ty.Union['SourceContent', 'Chunk'],
            start: 'SourcePos' = None,
            end: ty.Optional['SourcePos'] = None
    ) -> None:
        super().__init__(file_content, start, end)
        self.name = self.chunk.tokenize()[-1]


class FunctionDefinition(Component):
    """
    Component containing the definition of a function.
    """
    def __init__(
            self,
            file_content: ty.Union['SourceContent', 'Chunk'],
            start: 'SourcePos' = None,
            end: ty.Optional['SourcePos'] = None
    ) -> None:
        super().__init__(file_content, start, end)
        self.inner_block = self._find_block()
        self.prefix: 'Chunk' = self.chunk[:self.inner_block.chunk.start]
        first_parenthesis = find_in_scope('(', self.chunk)
        self.name = scope_tokens(self.chunk[:first_parenthesis])[-1]

    def _find_block(self) -> 'Block':
        block_start = find_in_scope('{', self.chunk)
        return Block(self.chunk[block_start:], scope_type=ScopeType.FUNC)

    def used_constructs(
            self,
            constructs: ty.Dict[str, 'Construct']
    ) -> ty.Dict[str, 'Construct']:
        used: ty.Dict[str, 'Construct'] = super().used_constructs(constructs)
        for component in self.inner_block.sub_components:
            used.update(component.used_constructs(constructs))
        return used

    @property
    def construct_content(self) -> ty.Dict[str, ty.List['Component']]:
        # noinspection PyTypeChecker
        content: ty.List['Component'] = [MiscStatement(self.prefix)] + \
            self.inner_block.sub_components
        return {self.name: content}

    @property
    def exposed_content(self) -> ty.List['Chunk']:
        """
        Gets content provided by component which affects compilation
        even if constructs declared or created by the component are
        not used.

        In the case of non-member FunctionDeclarations this is always
        an empty list.

        :return Empty List
        :rtype: List['Chunk']
        """
        return []

    def _find_tokens(self) -> ty.List[str]:
        return self.prefix.tokenize()

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}[{self.name}]'


class MemberFunctionDefinition(FunctionDefinition):
    """
    Component containing the definition of a function.
    """

    @property
    def exposed_content(self) -> ty.List['Chunk']:
        return [self.prefix.strip()]


class CppClassDefinition(Component):
    """
    Component containing the definition of a C++ class.
    """
    def __init__(
            self,
            file_content: ty.Union['SourceContent', 'Chunk'],
            start: 'SourcePos' = None,
            end: ty.Optional['SourcePos'] = None
    ) -> None:
        super().__init__(file_content, start, end)
        self.inner_block = self._find_block()
        self.prefix: 'Chunk' = self.chunk[:self.inner_block.chunk.start]
        self.name = self._find_name()

    def _find_block(self) -> 'Block':
        block_start = find_in_scope('{', self.chunk)
        end = self.chunk.end - 1
        return Block(self.chunk[block_start:end], scope_type=ScopeType.CLASS)

    def _find_name(self) -> str:
        prefix_tokens = scope_tokens(self.prefix)
        return prefix_tokens[prefix_tokens.index('class') + 1]

    def used_constructs(
            self,
            constructs: ty.Dict[str, 'Construct']
    ) -> ty.Dict[str, 'Construct']:
        used: ty.Dict[str, 'Construct'] = super().used_constructs(constructs)
        for component in self.member_components:
            used.update(component.used_constructs(constructs))
        return used

    @property
    def construct_content(self) -> ty.Dict[str, ty.List['Component']]:
        own_content = self.inner_block.sub_components
        construct_content = {self.name: own_content.copy()}
        for component in self.inner_block.sub_components:
            update_content(construct_content, component.construct_content)
        return construct_content

    @property
    def exposed_content(self) -> ty.List['Chunk']:
        return [self.prefix.strip()]
    
    @property
    def member_components(self) -> ty.List['Component']:
        return self.inner_block.sub_components

    def _find_tokens(self) -> ty.List[str]:
        return self.prefix.tokenize()

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}[{self.name}]'


class Label(Component):
    """
    Class representing c++ label components.
    Ex: "private:"
    """

    @property
    def name(self) -> str:
        return self.tokens[0]

    def __repr__(self) -> str:
        return f'Label[{self.name}]'


class ControlBlock(Component):
    """
    Component representing a control block such as an
    if, for, while, or do loop.
    """

    KEYWORDS = ('if', 'for', 'while', 'do')

    def __init__(
            self,
            file_content: ty.Union['SourceContent', 'Chunk'],
            start: 'SourcePos' = None,
            end: ty.Optional['SourcePos'] = None
    ) -> None:
        super().__init__(file_content, start, end)
        self.inner_block = self._find_block()
        self.prefix: 'Chunk' = self.chunk[:self.inner_block.chunk.start]

    def _find_block(self) -> 'Block':
        block_start = find_in_scope('{', self.chunk)
        return Block(self.chunk[block_start:], scope_type=ScopeType.CLASS)

    @property
    def sub_components(self) -> ty.List['Component']:
        return self.inner_block.sub_components

    @property
    def exposed_content(self) -> ty.List['Chunk']:
        return [self.prefix.strip()]

    def _find_tokens(self) -> ty.List[str]:
        return self.prefix.tokenize()


class UsingStatement(Component):
    """
    Component storing a using definition or declaration.
    """
    @classmethod
    def create(
            cls, 
            chunk: 'Chunk', 
            scope: 'ScopeType' = ScopeType.GLOBAL
    ) -> 'Component':
        return UsingStatement(chunk)


def find_in_scope(sub_str: str, chunk: 'Chunk') -> 'SourcePos':
    """
    Finds passed sub_str within the scope that begins at the start of
    the passed chunk. Ignores quoted strings within chunk.

    Chunk is assumed to contain no content from a higher level scope
    than that at the beginning of the chunk, and is assumed not to
    begin within a quote.

    :param sub_str: str to find within Chunk.
    :param chunk: Chunk of source to search.
    :return: SourcePos indicating start of passed sub_str in chunk.
    :rtype: SourcePos
    """
    s = ''
    pos = chunk.start
    while True:
        if s.endswith(sub_str):
            return pos - len(sub_str)
        try:
            c = chunk[pos]
        except IndexError:
            raise KeyError(f'{sub_str} not found in {chunk}')
        if (c in BRACKETS or c in '\'"') and (s + c).endswith(sub_str):
            return pos - (len(sub_str) - 1)
        if c in BRACKETS:
            pos = chunk.find_pair(pos)
            s = BRACKETS[c]
        elif c in '\'"':
            pos = chunk.find_quote_end(pos)
            s = c
        else:
            s += c
        pos += 1


def scope_tokens(chunk: 'Chunk', regex: str = r"[\w0-9]+") -> ty.List[str]:
    """
    Gets tokens in the highest level scope of the passed chunk.
    Passed chunk should begin within the scope that tokens
    are to be retrieved from, and not contain any content from a
    higher level scope. IE: Chunk should end before the function /
    class / etc ends.

    :param chunk: Chunk to check for tokens.
    :param regex: Optional regex to use for finding tokens.
    :return: List[str]
    """
    s = ''
    pos = chunk.start
    while pos != chunk.end:
        c = chunk[pos]
        if c in BRACKETS:
            pos = chunk.find_pair(pos)
        elif c in '\'"':
            pos = chunk.find_quote_end(pos)
        else:
            s += c
        try:
            pos += 1
        except ValueError:
            break
    return re.findall(regex, s)


def update_content(
        a: ty.Dict[str, ty.List['Component']],
        b: ty.Dict[str, ty.List['Component']]
) -> None:
    """
    Adds component content of dict b to dict a.

    :param a: Dictionary of components to be added to.
    :param b: Dictionary of components to add.
    :return: None
    """
    for k, v in b.items():
        try:
            content = a[k]
        except KeyError:
            content = a[k] = []
        content += v


def parse_tags(s: str) -> ty.Set[str]:
    """
    Parse passed string for tags (ie: 'ZEN(shallow)' ) within 
    passed string. 
    
    Intended to be passed raw line strings. 
    
    Does not look within block comments, as it is expected that all
    tags are in comments following a statement, or within a block.
    
    :param s: Line str to search for tags.
    :return: Set[str]
    """
    if '//' not in s or 'ZEN(' not in s:
        return set()
    comment = s[s.find('//') + 2:]
    matches = re.findall(r'ZEN\([^()]*\)', comment)
    tags: ty.Set[str] = set()
    for match in matches:
        tags_s = match[4:-1]
        tags |= {tag.strip() for tag in tags_s.split(',') if tag.strip()}
    return tags


#######################################################################
# Construct Graph


class ConstructGraph:
    """
    Contains a graph of constructs, for tracking constructs by name,
    and keeping track of the dependencies between them.
    """
    def __init__(self) -> None:
        """
        Initialize a new construct graph.
        """
        self.constructs: ty.Dict[str, Construct] = {}

    def __getitem__(self, name: str) -> 'Construct':
        """
        Gets construct with the passed name.
        :param name: str name of Construct.
        :return: Construct
        :raises: KeyError if no construct with passed name exists.
        """
        return self.constructs[name]

    def __len__(self) -> int:
        """
        Gets number of constructs in graph.
        :return: int
        """
        return len(self.constructs)

    def __iter__(self) -> ty.Iterable['Construct']:
        """
        Iterates over all Constructs in the graph.
        :return: Iterable[Construct]
        """
        yield from self.constructs.values()

    def get(self, name: str, create=False) -> 'Construct':
        """
        Gets a construct with the passed name if one exists,
        otherwise creates one.

        :param name: construct name str.
        :param create: if True, will create a construct if one does
                    not exist. Default is False.
        :return: Construct
        :raises KeyError if Construct with passed name does not exist and
                    create argument is False.
        """
        try:
            rv = self[name]
        except KeyError:
            if not create:
                raise
            rv = self.constructs[name] = Construct(name, graph=self)
        return rv

    def add(self, construct: 'Construct') -> None:
        """
        Add passed construct to graph.
        :param construct: Construct
        :return: None
        """
        if construct.graph:
            raise ValueError(f'{construct} already is in a graph.')
        construct.graph = self
        self.constructs[construct.name] = construct

    @property
    def names(self):
        return self.constructs.keys()

    def __repr__(self) -> str:
        return f'ConstructGraph[len={len(self.constructs)}]'


class Construct:
    """
    Constructs represent the code relating to a specific symbol.

    Classes, functions, and global variables are all examples
    of Constructs.
    """
    def __init__(self, name: str, graph: 'ConstructGraph' = None) -> None:
        self.name = name
        self.content: ty.List['Component'] = []
        self._content_hash: ty.Optional[int] = None
        self.graph: ty.Optional['ConstructGraph'] = graph

    def add_content(self, content: ty.List['Component']) -> None:
        """
        Adds content chunks to construct.

        :param content: List[Component]
        :rtype: None
        """
        self.content += content

    @property
    def content_hash(self) -> int:
        """
        Gets hash associated with the content of the construct.

        If any functional change is made to the Construct, the hash
        is expected to change.

        This value will be compared to previous runs in order to
        determine whether a change has been made.

        :return: int
        """
        if self._content_hash is None:
            self._content_hash = join_hashes(
                component.chunk.content_hash for component in self.content
            )
        return self._content_hash

    @property
    def dependencies(self) -> ty.Set['Construct']:
        """
        Gets Construct dependencies of this Construct.

        This property returns the direct dependencies of this
        Construct. No recursion occurs.

        :return: Set[Construct]
        """
        if not self.graph:
            raise ValueError(f'{self} does not belong to a graph.')

        deps: ty.Set['Construct'] = set()
        self._dep_search(self, deps, recurse=False)
        deps.discard(self)
        return deps

    @property
    def recursive_dependencies(self) -> ty.Set['Construct']:
        """
        Gets Construct dependencies of this construct recursively.
        :return: Set[Construct]
        """
        if not self.graph:
            raise ValueError(f'{self} does not belong to a graph.')

        deps = set()
        self._dep_search(self, deps, recurse=True)  # Adds to deps.
        deps.remove(self)
        return deps

    def _dep_search(
            self,
            construct: 'Construct',
            visited: ty.Set['Construct'],
            recurse: bool
    ):
        """
        Helper function that finds dependency Constructs.

        :param construct: Root construct.
        :param visited: Set of constructs to which dependencies will be added.
        :param recurse:
        :return:
        """
        if construct in visited:
            return
        for component in construct.content:
            for dep in component.used_constructs(
                    self.graph.constructs).values():
                if dep not in visited:
                    visited.add(dep)
                    if recurse:
                        self._dep_search(dep, visited, True)

    def __repr__(self) -> str:
        return f'Construct[{self.name}]'


#######################################################################


def verbose(*args, **kwargs) -> None:
    """
    Prints message if verbose_opt global has been set.
    :param args: args passed to print function.
    :param kwargs: kwargs passed to print function.
    :return: None
    """
    if verbose_opt:
        print(*args, **kwargs)


def clear() -> None:
    """
    Clears all statically cached objects.
    :return: None
    """
    SourceFile.clear()


def main():
    global verbose_opt
    parser = argparse.ArgumentParser(description='Focus compilation')
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
