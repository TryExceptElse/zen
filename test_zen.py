from unittest import TestCase

import collections
import os
from pathlib import Path
import shutil
import subprocess as sub
import tempfile

import zen


ROOT = Path(os.path.dirname(__file__))
TEST_RESOURCES_PATH = Path(ROOT, 'test_resources')

SAMPLE_PROJECT_PATH = Path(TEST_RESOURCES_PATH, 'sample_project_1')
SAMPLE_BUILD_DIR = os.path.join(SAMPLE_PROJECT_PATH, 'build')
FAKE_PROJECT_PATH = Path(
    '/', 'home', 'user0', 'PycharmProjects', 'zen', 'test_resources',
    'sample_project_1')
HELLO_H_PATH = Path(os.path.join(FAKE_PROJECT_PATH, 'hello', 'hello.h'))
HELLO_CC_PATH = Path(os.path.join(FAKE_PROJECT_PATH, 'hello', 'hello.cc'))
SAMPLE_H_PATH = Path(os.path.join(FAKE_PROJECT_PATH, 'sample.h'))
SAMPLE_CC_PATH = Path(os.path.join(FAKE_PROJECT_PATH, 'sample.cc'))
MAIN_CC_PATH = Path(os.path.join(FAKE_PROJECT_PATH, 'main.cc'))

TEST_SOURCE_DIR_PATH = Path(TEST_RESOURCES_PATH, 'test_source_dir_1')
FULL_BUILD_OUT_PATH = Path(TEST_RESOURCES_PATH, 'full_build_out')
NO_REBUILD_OUT_PATH = Path(TEST_RESOURCES_PATH, 'no_rebuild_out')
ALTERNATE_SAMPLE_H_PATH = Path(TEST_RESOURCES_PATH, 'alternate_sample.h')
ALTERNATE_HELLO_H_PATH = Path(TEST_RESOURCES_PATH, 'alternate_hello.h')

HELLO_REBUILD_OUT_PATH = Path(TEST_RESOURCES_PATH, 'hello_rebuild_out')
CHANGED_HELLO_CC_PATH = Path(TEST_RESOURCES_PATH, 'changed_hello.cc')
BROKEN_HELLO_CC_PATH = Path(TEST_RESOURCES_PATH, 'broken_hello.cc')

EXPECTED_OUT_1_PATH = Path(TEST_RESOURCES_PATH, 'expected_out1')
EXPECTED_OUT_2_PATH = Path(TEST_RESOURCES_PATH, 'expected_out2')

CODE_SAMPLES_PATH = Path(TEST_RESOURCES_PATH, 'code_samples')

with NO_REBUILD_OUT_PATH.open('rb') as f:
    NO_REBUILD_OUT = f.read()
with FULL_BUILD_OUT_PATH.open('rb') as f:
    FULL_BUILD_OUT = f.read()
with HELLO_REBUILD_OUT_PATH.open('rb') as f:
    HELLO_REBUILD_OUT = f.read()
with EXPECTED_OUT_1_PATH.open('rb') as f:
    EXPECTED_OUT_1 = f.read()
with EXPECTED_OUT_2_PATH.open('rb') as f:
    EXPECTED_OUT_2 = f.read()


class TestBuildDir(TestCase):
    def tearDown(self):
        zen.clear()

    def test_build_dir_finds_targets(self):
        build_dir = zen.BuildDir(SAMPLE_BUILD_DIR)
        self.assertEqual(2, len(build_dir.targets))
        self.assertIn('sample_target', build_dir.targets)
        self.assertIn('hello', build_dir.targets)

    def test_all_dependencies_are_found(self):
        build_dir = zen.BuildDir(SAMPLE_BUILD_DIR)
        self.assertIn(zen.SourceFile(HELLO_H_PATH), build_dir.sources)
        self.assertIn(zen.SourceFile(HELLO_CC_PATH), build_dir.sources)
        self.assertIn(zen.SourceFile(SAMPLE_H_PATH), build_dir.sources)
        self.assertIn(zen.SourceFile(SAMPLE_CC_PATH), build_dir.sources)
        self.assertIn(zen.SourceFile(MAIN_CC_PATH), build_dir.sources)

    def test_meditation_prevents_doc_edit_from_causing_rebuild(self):
        original_dir = os.curdir
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                project_dir, build_dir = self.set_up_project_dir(temp_dir)

                def make():
                    """
                    Run Zen, followed by make, and then
                    remember the sources used for the build.
                    :return: bytes resulting from the make call.
                    """
                    build_dir1 = zen.BuildDir(build_dir.absolute())
                    build_dir1.meditate()
                    out = sub.check_output(['make'])
                    build_dir2 = zen.BuildDir(build_dir.absolute())
                    build_dir2.remember()
                    return out

                # First make - full project should build.
                first_out = make()
                self.assertEqual(FULL_BUILD_OUT, first_out)
                # Second make with no source changes:
                # nothing should be rebuilt.
                second_out = make()
                self.assertEqual(NO_REBUILD_OUT, second_out)
                # Change docs and whitespace in header.
                shutil.copy(
                    ALTERNATE_SAMPLE_H_PATH.absolute(),
                    Path(project_dir, 'sample.h').absolute()
                )
                # Since no substantive changes have been made,
                # no objects should need to be rebuilt.
                last_out = make()
                self.assertEqual(NO_REBUILD_OUT, last_out)
        finally:
            os.chdir(original_dir)

    @staticmethod
    def set_up_project_dir(temp_dir):
        project_dir = Path(temp_dir, 'project')
        # Copy sources to project dir
        shutil.copytree(
            TEST_SOURCE_DIR_PATH.absolute(),
            project_dir.absolute()
        )
        build_dir = Path(project_dir, 'build')
        build_dir.mkdir()

        # CMake
        os.chdir(build_dir.absolute())
        sub.call(['cmake', '..'])
        return project_dir, build_dir

    @staticmethod
    def make(build_path: Path):
        """
        Run Zen, followed by make, and then
        remember the sources used for the build.
        :return: bytes resulting from the make call.
        """
        zen_path = Path(ROOT, 'zen.py')
        sub.check_call([
            'python3.6',
            str(zen_path),
            'meditate',
            str(build_path),
            '--verbose'
        ])
        out = sub.check_output(['make'])
        sub.check_call([
            'python3.6',
            str(zen_path),
            'remember',
            str(build_path),
            '--verbose'
        ])
        return out

    def test_meditation_prevents_doc_edit_from_causing_rebuild_cmd_line(self):
        original_dir = os.curdir
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                project_dir, build_dir = self.set_up_project_dir(temp_dir)

                # First make - full project should build.
                first_out = self.make(build_dir)
                self.assertEqual(FULL_BUILD_OUT, first_out)

                # Second make with no source changes:
                # nothing should be rebuilt.
                second_out = self.make(build_dir)
                self.assertEqual(NO_REBUILD_OUT, second_out)

                # Change docs and whitespace in header.
                shutil.copy(
                    ALTERNATE_SAMPLE_H_PATH.absolute(),
                    Path(project_dir, 'sample.h').absolute()
                )

                # Since no substantive changes have been made,
                # no objects should need to be rebuilt.
                last_out = self.make(build_dir)
                self.assertEqual(NO_REBUILD_OUT, last_out)
        finally:
            os.chdir(original_dir)

    def test_meditation_prevents_new_line_char_from_causing_rebuild(self):
        original_dir = os.curdir
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                project_dir, build_dir = self.set_up_project_dir(temp_dir)

                # First make - full project should build.
                first_out = self.make(build_dir)
                self.assertEqual(FULL_BUILD_OUT, first_out)
                # Second make with no source changes:
                # nothing should be rebuilt.
                second_out = self.make(build_dir)
                self.assertEqual(NO_REBUILD_OUT, second_out)
                # Change docs and whitespace in header.
                shutil.copy(
                    ALTERNATE_HELLO_H_PATH.absolute(),
                    Path(project_dir, 'hello', 'hello.h').absolute()
                )
                # Since no substantive changes have been made,
                # no objects should need to be rebuilt.
                last_out = self.make(build_dir)
                self.assertEqual(NO_REBUILD_OUT, last_out)
        finally:
            os.chdir(original_dir)

    def test_substantive_change_triggers_rebuilds(self):
        original_dir = os.curdir
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                project_dir, build_dir = self.set_up_project_dir(temp_dir)

                # First make - full project should build.
                first_out = self.make(build_dir)
                self.assertEqual(FULL_BUILD_OUT, first_out)

                # Change function definition in hello.cc.
                shutil.copy(
                    str(CHANGED_HELLO_CC_PATH),
                    str(Path(project_dir, 'hello', 'hello.cc'))
                )

                # Since no substantive changes have been made,
                # no objects should need to be rebuilt.
                last_out = self.make(build_dir)
                self.assertEqual(HELLO_REBUILD_OUT, last_out)
        finally:
            os.chdir(original_dir)

    def test_build_failure_does_not_cause_break_follow_up_builds(self):
        original_dir = os.curdir
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                project_dir, build_dir = self.set_up_project_dir(temp_dir)

                # First make - full project should build.
                first_build_out = self.make(build_dir)
                self.assertEqual(FULL_BUILD_OUT, first_build_out)

                # Check output of program
                call_path = str(Path(build_dir, 'sample_target'))
                first_program_out = sub.check_output([call_path])
                self.assertEqual(EXPECTED_OUT_1, first_program_out)

                # Change function definition in hello.cc.
                shutil.copy(
                    str(BROKEN_HELLO_CC_PATH),
                    str(Path(project_dir, 'hello', 'hello.cc'))
                )

                # Build with broken source
                self.assertRaises(sub.CalledProcessError, self.make, build_dir)

                # Fix source and rebuild
                shutil.copy(
                    str(CHANGED_HELLO_CC_PATH),
                    str(Path(project_dir, 'hello', 'hello.cc'))
                )
                fixed_build_out = self.make(build_dir)
                self.assertEqual(HELLO_REBUILD_OUT, fixed_build_out)

                # Re run program and check output.
                fixed_program_out = sub.check_output([call_path])
                self.assertEqual(EXPECTED_OUT_2, fixed_program_out)

        finally:
            os.chdir(original_dir)


class TestTarget(TestCase):
    def tearDown(self):
        zen.clear()

    def test_target_has_correct_objects(self):
        target = zen.BuildDir(SAMPLE_BUILD_DIR).targets['sample_target']
        self.assertEqual(2, len(target.objects))

    def test_target_finds_library_dependencies(self):
        build_dir = zen.BuildDir(SAMPLE_BUILD_DIR)
        target = build_dir.targets['sample_target']
        self.assertIn(build_dir.targets['hello'], target.lib_dependencies)

    def test_target_finds_other_dependencies(self):
        build_dir = zen.BuildDir(SAMPLE_BUILD_DIR)
        target = build_dir.targets['sample_target']
        build_file_path = Path(
            build_dir.path, 'CMakeFiles', 'sample_target.dir', 'build.make')
        link_file_path = Path(
            build_dir.path, 'CMakeFiles', 'sample_target.dir', 'link.txt')
        self.assertIn(build_file_path, target.other_dependencies)
        self.assertIn(link_file_path, target.other_dependencies)


class TestSourceFile(TestCase):
    def tearDown(self):
        zen.clear()

    def test_multiple_source_file_instantiations_produce_same_instance(self):
        a = zen.SourceFile(HELLO_H_PATH)
        b = zen.SourceFile(HELLO_H_PATH)
        self.assertIs(a, b)

    def test_duplicate_source_files_have_same_hash(self):
        a = zen.SourceFile(HELLO_H_PATH)
        b = zen.SourceFile(HELLO_H_PATH)
        self.assertEqual(hash(a), hash(b))

    def test_different_source_files_are_unique_instances(self):
        definition_file = zen.SourceFile(HELLO_CC_PATH)
        header_file = zen.SourceFile(HELLO_H_PATH)
        self.assertIsNot(header_file, definition_file)


class TestSourceContent(TestCase):
    def tearDown(self):
        zen.clear()

    def test_source_content_generates_lines(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        self.assertEqual(3, len(content.lines))

    def test_uncomment_line_removes_block_comment_in_single_line(self):
        content = zen.SourceContent('    this is a /* commented */ line')
        content.strip_comments()
        self.assertEqual('    this is a   line', content.lines[0].uncommented)

    def test_uncomment_line_removes_block_comment_in_multiple_lines(self):
        content = zen.SourceContent('    this is a /* \ncommented\n */ line')
        content.strip_comments()
        self.assertEqual('    this is a \n', content.lines[0].uncommented)
        self.assertEqual('\n', content.lines[1].uncommented)
        self.assertEqual(' line', content.lines[2].uncommented)

    def test_uncomment_line_removes_line_comment_in_single_line(self):
        content = zen.SourceContent('    this is a line  // with line comment')
        content.strip_comments()
        self.assertEqual('    this is a line  ', content.lines[0].uncommented)

    def test_removing_line_comment_does_not_remove_newline_char(self):
        content = zen.SourceContent('    line  // with newline char\n')
        content.strip_comments()
        self.assertEqual('    line  \n', content.lines[0].uncommented)

    def test_removing_block_comment_does_not_remove_newline_char(self):
        content = zen.SourceContent('    this is a /*\ncommented\n*/ line')
        content.strip_comments()
        self.assertEqual('    this is a \n', content.lines[0].uncommented)
        self.assertEqual('\n', content.lines[1].uncommented)
        self.assertEqual(' line', content.lines[2].uncommented)

    def test_stripped_line_with_content_is_correct(self):
        content = zen.SourceContent('    this is a /* commented */ line\n')
        content.strip_comments()
        self.assertEqual('this is a line\n', content.lines[0].stripped)

    def test_stripped_line_with_whitespace_is_correct(self):
        content = zen.SourceContent('    \t\n')
        content.strip_comments()
        self.assertEqual('\n', content.lines[0].stripped)

    def test_stripped_empty_line_is_correct(self):
        content = zen.SourceContent('\n')
        content.strip_comments()
        self.assertEqual('\n', content.lines[0].stripped)

    def test_stripped_hash_does_not_change_with_whitespace_line_number(self):
        content1 = zen.SourceContent('    \n    \nFoo')
        content1.strip_comments()
        content2 = zen.SourceContent('    \n    \n\n  \n\nFoo')
        content2.strip_comments()
        self.assertEqual(content1.stripped_hash, content2.stripped_hash)

    def test_stripped_hash_changes_with_different_useful_content(self):
        content1 = zen.SourceContent('    \n    \nFoo')
        content1.strip_comments()
        content2 = zen.SourceContent('    \n    \nBar')
        content2.strip_comments()
        self.assertNotEqual(content1.stripped_hash, content2.stripped_hash)

    def test_preprocessor_directive_is_identified(self):
        content1 = zen.SourceContent('// Preprocessor\n#include <string>\n\n')
        self.assertIsInstance(
            content1.component.sub_components[0],
            zen.PreprocessorComponent
        )

    def test_correct_components_are_found(self):
        with Path(TEST_RESOURCES_PATH, 'template_func.cc').open() as src_f:
            # noinspection PyTypeChecker
            content = zen.SourceContent(src_f)
            components = content.component.sub_components
            self.assertIsInstance(
                components[0],
                zen.PreprocessorComponent
            )
            self.assertIsInstance(
                components[1],
                zen.UsingStatement
            )
            self.assertIsInstance(
                components[2],
                zen.FunctionDefinition
            )
            self.assertEqual(1, len(components[2].construct_content))
            self.assertIn('custom_max', components[2].construct_content)
            self.assertIsInstance(
                components[3],
                zen.FunctionDefinition
            )
            self.assertEqual(1, len(components[3].construct_content))
            self.assertIn('main', components[3].construct_content)

    def test_correct_nested_components_are_found(self):
        with ALTERNATE_SAMPLE_H_PATH.open() as src_f:
            # noinspection PyTypeChecker
            content = zen.SourceContent(src_f)
            components = content.component.sub_components
            self.assertEqual(2, len(components))
            self.assertIsInstance(components[0], zen.PreprocessorComponent)
            self.assertIsInstance(components[1], zen.NamespaceComponent)
            ns_components = components[1].sub_components
            self.assertEqual(1, len(ns_components))
            self.assertIsInstance(ns_components[0], zen.CppClassDefinition)
            self.assertIn('Foo', ns_components[0].construct_content)
            # noinspection PyUnresolvedReferences
            class_components = ns_components[0].inner_block.sub_components
            self.assertEqual(5, len(class_components))
            self.assertIsInstance(
                class_components[1],
                zen.MemberFunctionDefinition
            )
            self.assertIn('Foo', class_components[1].construct_content)
            self.assertIsInstance(
                class_components[2],
                zen.MemberFunctionDeclaration
            )
            self.assertIn('Print', class_components[2].construct_content)
            self.assertIsInstance(
                class_components[4],
                zen.MiscStatement
            )


class TestSourceCache(TestCase):
    FakeSourceFile = collections.namedtuple(
        'FakeSourceFile', (
            'stripped_hash'
        )
    )

    def test_cache_and_recovery(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create source
            fake_source = self.FakeSourceFile(5)

            # Create cache
            cache_path = Path(temp_dir, 'cache')
            cache = zen.SourceCache(cache_path)
            # noinspection PyTypeChecker
            cache.cache(fake_source)

            # Create second cache to check that values can be restored.
            cache2 = zen.SourceCache(cache_path)
            self.assertEqual(5, cache2.stripped_hash)


class TestSourcePos(TestCase):
    def test_position_can_be_added_to(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        chunk = zen.Chunk(content)
        a = chunk.start
        b = a + 10
        c = a + 25
        self.assertEqual('T', chunk[a])
        self.assertEqual('h', chunk[b])
        self.assertEqual('.', chunk[c])

    def test_addition_does_not_modify_operands(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        chunk = zen.Chunk(content)
        a = chunk.start
        initial_line_i = a.line_i
        initial_col_i = a.col_i
        a + 10
        self.assertEqual(initial_line_i, a.line_i)
        self.assertEqual(initial_col_i, a.col_i)

    def test_position_can_be_added_to_to_get_end_pos(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        chunk = zen.Chunk(content)
        a = chunk.start
        b = a + 26
        self.assertEqual(b, chunk.end)

    def test_position_can_be_added_to_to_get_end_pos_on_same_line(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        chunk = zen.Chunk(content)
        a = chunk.start + 22
        b = a + 4
        self.assertEqual(b, chunk.end)

    def test_position_can_be_subtracted_from(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        chunk = zen.Chunk(content)
        a = chunk.end - 1
        b = chunk.end - 16
        c = chunk.end - 26
        self.assertEqual('T', chunk[c])
        self.assertEqual('h', chunk[b])
        self.assertEqual('.', chunk[a])

    def test_next_line_can_be_accessed(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        chunk = zen.Chunk(content)
        a = zen.SourcePos(content, 0, 4, zen.SourceForm.STRIPPED)
        b = a.next_line_pos
        c = b.next_line_pos
        self.assertEqual('h', chunk[b])
        self.assertEqual('l', chunk[c])

    def test_positions_with_same_indices_are_equal(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        a = zen.SourcePos(content, 0, 4, zen.SourceForm.STRIPPED)
        b = zen.SourcePos(content, 0, 4, zen.SourceForm.STRIPPED)
        self.assertEqual(a, b)

    def test_positions_with_same_indices_have_same_hash(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        a = zen.SourcePos(content, 0, 4, zen.SourceForm.STRIPPED)
        b = zen.SourcePos(content, 0, 4, zen.SourceForm.STRIPPED)
        self.assertEqual(hash(a), hash(b))

    def test_positions_with_different_indices_are_not_equal(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        a = zen.SourcePos(content, 0, 4, zen.SourceForm.STRIPPED)
        b = zen.SourcePos(content, 1, 4, zen.SourceForm.STRIPPED)
        self.assertNotEqual(a, b)


class TestChunk(TestCase):
    def test_chunk_created_from_content_has_correct_length(self):
        content = zen.SourceContent('\n\n\n\n\n\nclass Foo')
        self.assertEqual(15, len(zen.Chunk(content)))

    def test_chunk_created_from_content_same_string(self):
        s = '\n\n\n\n\n\nclass Foo'
        content = zen.SourceContent(s)
        self.assertEqual(s, str(zen.Chunk(content)))

    def test_chunk_index_accessor_works_correctly(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        chunk = zen.Chunk(content)
        self.assertEqual('T', chunk[0])
        self.assertEqual('h', chunk[10])
        self.assertEqual('.', chunk[-1])

    def test_chunk_index_accessor_works_when_chunk_starts_mid_line(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        start_pos = zen.SourcePos(content, 0, 5, zen.SourceForm.STRIPPED)
        chunk = zen.Chunk(content, start=start_pos)
        assert chunk[5] == 'h'
        assert chunk[15] == 'l'

    def test_source_pos_can_be_passed_to_getitem(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        chunk = zen.Chunk(content)
        self.assertEqual('T', chunk[chunk.pos(0, 0)])
        self.assertEqual('h', chunk[chunk.pos(1, 0)])
        self.assertEqual('.', chunk[chunk.pos(-1, -1)])

    def test_source_pos_can_be_sliced_with_positions(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        chunk = zen.Chunk(content)
        a = chunk[:chunk.pos(1, 3)]
        b = a[chunk.pos(1):]
        self.assertEqual('This file\nhas three\nlines.', str(chunk))
        self.assertEqual('This file\nhas', str(a))
        self.assertEqual('has', str(b))

    def test_chunk_can_be_turned_into_string(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        chunk = zen.Chunk(content)
        self.assertEqual('This file\nhas three\nlines.', str(chunk))

    def test_chunk_can_be_turned_into_string2(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        start = zen.SourcePos(content, 1, 0, zen.SourceForm.STRIPPED)
        end = zen.SourcePos(content, 1, 3, zen.SourceForm.STRIPPED)
        chunk = zen.Chunk(content, start, end)
        self.assertEqual('has', str(chunk))

    def test_chunk_chars_can_be_iterated_over(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        chunk = zen.Chunk(content)
        chars = [c for c in chunk]
        self.assertEqual(len('This file\nhas three\nlines.'), len(chars))
        self.assertEqual('T', chars[0])
        self.assertEqual('h', chars[10])
        self.assertEqual('.', chars[-1])

    def test_chunk_chars_can_be_iterated_over2(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        start = zen.SourcePos(content, 1, 0, zen.SourceForm.STRIPPED)
        end = zen.SourcePos(content, 1, 3, zen.SourceForm.STRIPPED)
        chunk = zen.Chunk(content, start, end)
        self.assertEqual('has', ''.join(char for char in chunk))

    def test_chunk_can_be_initialized_with_end_of_line_position(self):
        content = zen.SourceContent('This file\nhas three\nlines.')
        start_pos = zen.SourcePos(
            content, 0, len('This file\n'), zen.SourceForm.STRIPPED)
        chunk = zen.Chunk(content, start_pos)
        self.assertEqual('has three\nlines.', str(chunk))

    def test_chunk_may_be_default_tokenized(self):
        content = zen.SourceContent('This file\nhas three\nlines.\nfoo123')
        chunk = zen.Chunk(content)
        self.assertEqual(
            ['This', 'file', 'has', 'three', 'lines', 'foo123'],  # No period.
            chunk.tokenize()
        )

    def test_simple_bracket_pair_can_be_found(self):
        content = zen.SourceContent('Some bracket {\nfoo;\n}\n')
        chunk = zen.Chunk(content)
        first_bracket_pos = chunk.pos(0, -2)
        end_pos = chunk.find_pair(first_bracket_pos)
        self.assertEqual(2, end_pos.line_i)
        self.assertEqual(0, end_pos.col_i)

    def test_nested_bracket_pair_can_be_found(self):
        content = zen.SourceContent('{Some bracket {\n{foo};\n}\n}')
        chunk = zen.Chunk(content)
        first_bracket_pos = chunk.pos(0, -2)
        end_pos = chunk.find_pair(first_bracket_pos)
        self.assertEqual(2, end_pos.line_i)
        self.assertEqual(0, end_pos.col_i)

    def test_bracket_pair_can_be_found_when_quoted_brackets_are_used(self):
        content = zen.SourceContent('{foo {\n{foo("bracket: }")};\n}\n}')
        chunk = zen.Chunk(content)
        first_bracket_pos = chunk.pos(0, -2)
        end_pos = chunk.find_pair(first_bracket_pos)
        self.assertEqual(2, end_pos.line_i)
        self.assertEqual(0, end_pos.col_i)

    def test_bracket_pair_can_be_found_when_bracket_char_is_used(self):
        content = zen.SourceContent("{foo {\n{foo('}')};\n}\n}")
        chunk = zen.Chunk(content)
        first_bracket_pos = chunk.pos(0, -2)
        end_pos = chunk.find_pair(first_bracket_pos)
        self.assertEqual(2, end_pos.line_i)
        self.assertEqual(0, end_pos.col_i)

    def test_quote_end_can_be_found(self):
        content = zen.SourceContent('foo("some [string]\\" argument")')
        chunk = zen.Chunk(content)
        first_quote_pos = chunk.pos(0, 4)
        end_pos = chunk.find_quote_end(first_quote_pos)
        self.assertEqual(0, end_pos.line_i)
        self.assertEqual(29, end_pos.col_i)

    def test_line_can_be_retrieved_from_pos(self):
        content = zen.SourceContent('{Some bracket {\n{foo};\n}\n}')
        chunk = zen.Chunk(content)
        pos = chunk.pos(1, 2)
        self.assertEqual(1, chunk.line(pos).index)

    def test_chunk_can_strip_whitespace_lines(self):
        content = zen.SourceContent('\n\n\nfoo("some arg")\n\n')
        chunk = zen.Chunk(content)
        stripped = chunk.strip()
        self.assertEqual(3, stripped.start.line_i)
        self.assertEqual(0, stripped.start.col_i)
        self.assertEqual(3, stripped.end.line_i)
        self.assertEqual(15, stripped.end.col_i)

    def test_chunk_does_not_strip_non_whitespace_chars(self):
        content = zen.SourceContent('\n\n\nfoo("some arg")')
        chunk = zen.Chunk(content)
        stripped = chunk.strip()
        self.assertEqual(3, stripped.start.line_i)
        self.assertEqual(0, stripped.start.col_i)
        self.assertEqual(3, stripped.end.line_i)
        self.assertEqual(15, stripped.end.col_i)
        self.assertEqual('foo("some arg")', str(stripped))

    def test_chunk_can_be_stripped_when_trailing_spaces_are_present(self):
        content = zen.SourceContent('\n\n\nfoo("some arg") \n\n')
        chunk = zen.Chunk(content)
        stripped = chunk.strip()
        self.assertEqual(3, stripped.start.line_i)
        self.assertEqual(0, stripped.start.col_i)
        self.assertEqual(3, stripped.end.line_i)
        self.assertEqual(15, stripped.end.col_i)

    def test_chunk_hash_is_same_for_chunks_with_same_stripped_content(self):
        content_a = zen.SourceContent('This file\nhas three\nlines.')
        chunk_a = zen.Chunk(content_a)
        hash_a = chunk_a.content_hash
        content_b = zen.SourceContent('This file\n  has   three\nlines.')
        chunk_b = zen.Chunk(content_b)
        hash_b = chunk_b.content_hash
        self.assertEqual(hash_a, hash_b)

    def test_chunk_hash_is_same_for_chunks_with_same_stripped_content2(self):
        content_a = zen.SourceContent('This file\nhas three\nlines.')
        chunk_a = zen.Chunk(content_a)
        hash_a = chunk_a[chunk_a.pos(1, 0):].content_hash
        content_b = zen.SourceContent('file\n  has   three\nlines.')
        chunk_b = zen.Chunk(content_b)
        hash_b = chunk_b[chunk_b.pos(1, 0):].content_hash
        self.assertEqual(hash_a, hash_b)

    def test_chunk_hash_differs_if_content_does(self):
        content_a = zen.SourceContent('This file\nhas three\nlines.')
        chunk_a = zen.Chunk(content_a)
        hash_a = chunk_a.content_hash
        content_b = zen.SourceContent('file\n  has   three\nlines.')
        chunk_b = zen.Chunk(content_b)
        hash_b = chunk_b.content_hash
        self.assertNotEqual(hash_a, hash_b)


class TestCppClassDefinition(TestCase):
    def get_class_def(self) -> zen.CppClassDefinition:
        with Path(CODE_SAMPLES_PATH, 'sample_class').open() as src_f:
            # noinspection PyTypeChecker
            content = zen.SourceContent(src_f)
            definition = content.component.sub_components[0]
            self.assertIsInstance(definition, zen.CppClassDefinition)
            return definition

    def test_class_produces_correctly_named_constructs(self):
        definition = self.get_class_def()
        self.assertEqual(2, len(definition.construct_content))
        self.assertIn('Foo', definition.construct_content)
        self.assertIn('Print', definition.construct_content)

    def test_class_members_are_not_in_sub_components(self):
        definition = self.get_class_def()
        self.assertEqual([], definition.sub_components)

    def test_correct_number_of_member_components_are_found(self):
        definition = self.get_class_def()
        self.assertEqual(5, len(definition.member_components))

    def test_class_labels_are_found(self):
        definition = self.get_class_def()
        components = definition.member_components
        self.assertIsInstance(components[0], zen.Label)
        self.assertIsInstance(components[3], zen.Label)

    def test_class_constructor_has_correct_type(self):
        definition = self.get_class_def()
        components = definition.member_components
        self.assertIsInstance(components[1], zen.MemberFunctionDefinition)

    def test_member_function_declaration_has_correct_type(self):
        definition = self.get_class_def()
        components = definition.member_components
        self.assertIsInstance(components[2], zen.MemberFunctionDeclaration)

    def test_member_variable_declaration_has_correct_type(self):
        definition = self.get_class_def()
        components = definition.member_components
        self.assertIsInstance(components[4], zen.MiscStatement)

    def test_tokens_are_correct(self):
        definition = self.get_class_def()
        self.assertEqual(['class', 'Foo'], definition.tokens)

    def test_exposed_content_only_includes_prefix(self):
        definition = self.get_class_def()
        self.assertEqual(1, len(definition.exposed_content))
        self.assertEqual('class Foo', str(definition.exposed_content[0]))


class TestFunctionDeclaration(TestCase):
    pass


class TestMemberFunctionDeclaration(TestCase):
    def test_construct_is_correctly_named(self):
        content = zen.SourceContent('void Print() const;')
        declaration = zen.MemberFunctionDeclaration(content.component.chunk)
        self.assertEqual(1, len(declaration.construct_content))
        self.assertIn('Print', declaration.construct_content)

    def test_whole_declaration_is_in_external_content(self):
        s = 'void Print() const;'
        content = zen.SourceContent(s)
        declaration = zen.MemberFunctionDeclaration(content.component.chunk)
        self.assertEqual(s, str(declaration.exposed_content[0]))


class TestMemberFunctionDefinition(TestCase):
    def test_construct_is_correctly_named(self):
        with Path(CODE_SAMPLES_PATH, 'sample_member_func').open() as src_f:
            content_s = src_f.read()
        content = zen.SourceContent(content_s)
        definition = zen.MemberFunctionDefinition(content.component.chunk)
        self.assertEqual(1, len(definition.construct_content))
        self.assertIn('Print', definition.construct_content)

    def test_code_preceding_function_block_is_external(self):
        with Path(CODE_SAMPLES_PATH, 'sample_member_func').open() as src_f:
            content_s = src_f.read()
        content = zen.SourceContent(content_s)
        definition = zen.MemberFunctionDefinition(content.component.chunk)
        self.assertEqual(1, len(definition.construct_content))
        self.assertIn('Print', definition.construct_content)


class TestControlComponent(TestCase):
    def test_control_block_can_be_recognized(self):
        content = zen.SourceContent('for (i = 0; i < 5; ++i) { a += 5; }')
        components = content.component.sub_components
        self.assertEqual(1, len(components))
        self.assertIsInstance(components[0], zen.ControlBlock)

    def test_control_block_has_correct_sub_components(self):
        content = zen.SourceContent('for (i = 0; i < 5; ++i) { a += 5; }')
        control_component = zen.ControlBlock(content.component.chunk)
        sub_components = control_component.sub_components
        self.assertEqual(1, len(sub_components))
        self.assertIsInstance(sub_components[0], zen.MiscStatement)

    def test_exposed_content_only_includes_prefix(self):
        content = zen.SourceContent('for (i = 0; i < 5; ++i){ a += 5; }')
        control_component = zen.ControlBlock(content.component.chunk)
        self.assertEqual(1, len(control_component.exposed_content))
        self.assertEqual(
            'for (i = 0; i < 5; ++i)',
            str(control_component.exposed_content[0])
        )

    def test_correct_tokens_are_present(self):
        content = zen.SourceContent('for (i = 0; i < 5; ++i){ a += 5; }')
        component = zen.ControlBlock(content.component.chunk)
        self.assertEqual(['for', 'i', '0', 'i', '5', 'i'], component.tokens)


class TestNamespace(TestCase):
    def test_exposed_content_only_includes_prefix(self):
        content = zen.SourceContent(
            'namespace ns{ \n'
            'void foo() { std::cout << "hi"; }\n'
            '}  // namespace ns\n'
        )
        namespace = zen.NamespaceComponent(content.component.chunk)
        self.assertEqual(1, len(namespace.exposed_content))
        self.assertEqual('namespace ns', str(namespace.exposed_content[0]))


class TestMiscComponent(TestCase):
    def test_correct_tokens_are_present(self):
        content = zen.SourceContent('std::vector<int> numbers_;')
        chunk = content.component.chunk
        statement = zen.MiscStatement(chunk)
        self.assertEqual(
            ['std', 'vector', 'int', 'numbers_'],
            statement.tokens
        )


class TestFindInScope(TestCase):
    def test_find_in_scope_finds_bracket_start(self):
        content = zen.SourceContent(
            '\n\n\n\ntemplate <typename T>\n'
            'T custom_max(T x, T y)\n{\n'
            'return (x > y)? x: y;\n'
            '}'
        )
        chunk = content.component.chunk
        result = zen.find_in_scope('{', chunk)
        self.assertEqual(6, result.line_i)
        self.assertEqual(0, result.col_i)


class TestFindScopeTokens(TestCase):
    def test_scope_tokens_are_correct(self):
        content = zen.SourceContent(
            '\n\n\n\ntemplate <typename T>\n'
            'T custom_max(T x, T y)\n'
        )
        chunk = content.component.chunk
        tokens = zen.scope_tokens(chunk)
        self.assertEqual(['template', 'T', 'custom_max'], tokens)


class TestIterHash(TestCase):
    def test_hash_is_repeatable(self):
        result: int = zen.iter_hash((s for s in ['a', 'b', 'c']))
        self.assertEqual(8304879420899386742, result)
