# CMAKE generated file: DO NOT EDIT!
# Generated by "Unix Makefiles" Generator, CMake Version 3.10

# Delete rule output on recipe failure.
.DELETE_ON_ERROR:


#=============================================================================
# Special targets provided by cmake.

# Disable implicit rules so canonical targets will work.
.SUFFIXES:


# Remove some rules from gmake that .SUFFIXES does not remove.
SUFFIXES =

.SUFFIXES: .hpux_make_needs_suffix_list


# Suppress display of executed commands.
$(VERBOSE).SILENT:


# A target that is always out of date.
cmake_force:

.PHONY : cmake_force

#=============================================================================
# Set environment variables for the build.

# The shell in which to execute make rules.
SHELL = /bin/sh

# The CMake executable.
CMAKE_COMMAND = /usr/local/bin/cmake

# The command to remove a file.
RM = /usr/local/bin/cmake -E remove -f

# Escaping for special characters.
EQUALS = =

# The top-level source directory on which CMake was run.
CMAKE_SOURCE_DIR = /home/user/src/sample_project_1

# The top-level build directory on which CMake was run.
CMAKE_BINARY_DIR = /home/user/src/sample_project_1/build

# Include any dependencies generated for this target.
include hello/CMakeFiles/hello.dir/depend.make

# Include the progress variables for this target.
include hello/CMakeFiles/hello.dir/progress.make

# Include the compile flags for this target's objects.
include hello/CMakeFiles/hello.dir/flags.make

hello/CMakeFiles/hello.dir/hello.cc.o: hello/CMakeFiles/hello.dir/flags.make
hello/CMakeFiles/hello.dir/hello.cc.o: ../hello/hello.cc
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green --progress-dir=/home/user/src/sample_project_1/build/CMakeFiles --progress-num=$(CMAKE_PROGRESS_1) "Building CXX object hello/CMakeFiles/hello.dir/hello.cc.o"
	cd /home/user/src/sample_project_1/build/hello && /usr/bin/c++  $(CXX_DEFINES) $(CXX_INCLUDES) $(CXX_FLAGS) -o CMakeFiles/hello.dir/hello.cc.o -c /home/user/src/sample_project_1/hello/hello.cc

hello/CMakeFiles/hello.dir/hello.cc.i: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Preprocessing CXX source to CMakeFiles/hello.dir/hello.cc.i"
	cd /home/user/src/sample_project_1/build/hello && /usr/bin/c++ $(CXX_DEFINES) $(CXX_INCLUDES) $(CXX_FLAGS) -E /home/user/src/sample_project_1/hello/hello.cc > CMakeFiles/hello.dir/hello.cc.i

hello/CMakeFiles/hello.dir/hello.cc.s: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Compiling CXX source to assembly CMakeFiles/hello.dir/hello.cc.s"
	cd /home/user/src/sample_project_1/build/hello && /usr/bin/c++ $(CXX_DEFINES) $(CXX_INCLUDES) $(CXX_FLAGS) -S /home/user/src/sample_project_1/hello/hello.cc -o CMakeFiles/hello.dir/hello.cc.s

hello/CMakeFiles/hello.dir/hello.cc.o.requires:

.PHONY : hello/CMakeFiles/hello.dir/hello.cc.o.requires

hello/CMakeFiles/hello.dir/hello.cc.o.provides: hello/CMakeFiles/hello.dir/hello.cc.o.requires
	$(MAKE) -f hello/CMakeFiles/hello.dir/build.make hello/CMakeFiles/hello.dir/hello.cc.o.provides.build
.PHONY : hello/CMakeFiles/hello.dir/hello.cc.o.provides

hello/CMakeFiles/hello.dir/hello.cc.o.provides.build: hello/CMakeFiles/hello.dir/hello.cc.o


# Object files for target hello
hello_OBJECTS = \
"CMakeFiles/hello.dir/hello.cc.o"

# External object files for target hello
hello_EXTERNAL_OBJECTS =

hello/libhello.a: hello/CMakeFiles/hello.dir/hello.cc.o
hello/libhello.a: hello/CMakeFiles/hello.dir/build.make
hello/libhello.a: hello/CMakeFiles/hello.dir/link.txt
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green --bold --progress-dir=/home/user/src/sample_project_1/build/CMakeFiles --progress-num=$(CMAKE_PROGRESS_2) "Linking CXX static library libhello.a"
	cd /home/user/src/sample_project_1/build/hello && $(CMAKE_COMMAND) -P CMakeFiles/hello.dir/cmake_clean_target.cmake
	cd /home/user/src/sample_project_1/build/hello && $(CMAKE_COMMAND) -E cmake_link_script CMakeFiles/hello.dir/link.txt --verbose=$(VERBOSE)

# Rule to build all files generated by this target.
hello/CMakeFiles/hello.dir/build: hello/libhello.a

.PHONY : hello/CMakeFiles/hello.dir/build

hello/CMakeFiles/hello.dir/requires: hello/CMakeFiles/hello.dir/hello.cc.o.requires

.PHONY : hello/CMakeFiles/hello.dir/requires

hello/CMakeFiles/hello.dir/clean:
	cd /home/user/src/sample_project_1/build/hello && $(CMAKE_COMMAND) -P CMakeFiles/hello.dir/cmake_clean.cmake
.PHONY : hello/CMakeFiles/hello.dir/clean

hello/CMakeFiles/hello.dir/depend:
	cd /home/user/src/sample_project_1/build && $(CMAKE_COMMAND) -E cmake_depends "Unix Makefiles" /home/user/src/sample_project_1 /home/user/src/sample_project_1/hello /home/user/src/sample_project_1/build /home/user/src/sample_project_1/build/hello /home/user/src/sample_project_1/build/hello/CMakeFiles/hello.dir/DependInfo.cmake --color=$(COLOR)
.PHONY : hello/CMakeFiles/hello.dir/depend

