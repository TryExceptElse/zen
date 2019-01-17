# Zen
Focusing compilation.

[![Build Status](https://travis-ci.org/TryExceptElse/zen.svg?branch=master)](https://travis-ci.org/TryExceptElse/zen)
[![codecov](https://codecov.io/gh/TryExceptElse/zen/branch/master/graph/badge.svg)](https://codecov.io/gh/TryExceptElse/zen)


## Levels:

Zen has different levels that can be set project-wide, for specific 
source files, or individual code blocks.

 * Disable: Disables Zen for this source file or block; any change to
    the source will trigger a rebuild of dependant objects.
 * Shallow: Prevents changes in comments and whitespace from 
    triggering rebuilds of dependant objects.
 * Deep: (WIP) Only changes to types (namespaces, classes, functions, 
    and macros) actually used by compiled objects will trigger 
    a rebuild. For example: modifying the class declaration of Foo will
    only trigger a rebuild of dependant objects if they actually use Foo.
    
## Project Assumptions:
In order to effectively optimize compilation, Zen makes a number of
assumptions about the structure of a project.

 * Definitions in header files will <i>not</i> be linked to. Zen
        assumes that if a definition is in a header file, then it
        will be included by any source files that require it.
 * Zen assumes that all definitions in .cc / .cpp
        source files are useful, and should cause recompilation
        should they change, while all declarations and definitions in
        header files exist purely to be used within the compilation
        units that `#include` them. Therefore, if a declaration or 
        definition within a header file is not used within the the
        current compilation unit (directly or indirectly) then any
        changes made to it should not cause a rebuild of that unit.
 * Headers and source from outside the project do not change.

## Unsupported code features:
Some features of valid C++ code are not supported by Zen, and are not
intended to ever be supported.

These include:
 * `#include` statements anywhere but in the global scope.
 * Cross-file code blocks, IE: a code block that begins in one file, 
        and ends in another, via abuse of `#include` 
        preprocessor macros.
 * Macros that act as anything but a pseudo-function. 
        For example: macros such as SWAP(a, b) are acceptable,
        however a macro that expands to the declaration of a function
        is not supported, and a macro that contains only the beginning
        or only the end of a code block are certainly not
        supported. If you must have such things in your code, the
        surrounding code block containing the macro should be
        marked with `// ZEN(disable)`

## Todo:
 * Test + ensure correct operation of shallow mode
 * Implement deep mode
    * Run block use analysis on header files only.
    * Consider operator overload functions to be used whenever their
        class is, since they are called without their name being used.