cmake_minimum_required(VERSION 3.10)

project(YAGG_Launcher C)  # C-only project

# Configure executable
add_executable(YAGG WIN32 launcher.c launcher.rc)

# Static linking to minimize dependencies
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -static -mwindows")
target_link_libraries(YAGG kernel32 user32 shell32)

# Output directory
set_target_properties(YAGG PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/../dist"
)

# Compiler optimization flags
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -Os -s")
