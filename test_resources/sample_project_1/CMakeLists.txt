cmake_minimum_required(VERSION 3.10)

project(sample_project)

set(CMAKE_CXX_FLAGS "-std=c++11 ${CMAKE_CXX_FLAGS}")

add_subdirectory(hello)

add_executable(sample_target
    sample.cc
    main.cc)

target_link_libraries(sample_target hello)
