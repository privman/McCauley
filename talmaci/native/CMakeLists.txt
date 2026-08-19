# Builds libtalmaci_native (shared) + talmaci-cli.
# Dependencies (whisper.cpp, CTranslate2, SentencePiece) are fetched at
# configure time via FetchContent and linked statically into the one dylib.
#
#   cmake -S native -B native/build -DCMAKE_BUILD_TYPE=Release
#   cmake --build native/build -j
#
# On Apple Silicon, Metal (for whisper) and Accelerate (for CTranslate2) are
# enabled automatically.

cmake_minimum_required(VERSION 3.24)
project(talmaci_native LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

include(FetchContent)

# ---- whisper.cpp ----
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
if(APPLE)
  set(GGML_METAL ON CACHE BOOL "" FORCE)
  set(GGML_METAL_EMBED_LIBRARY ON CACHE BOOL "" FORCE)
  set(GGML_ACCELERATE ON CACHE BOOL "" FORCE)
endif()
FetchContent_Declare(whisper
  GIT_REPOSITORY https://github.com/ggml-org/whisper.cpp
  GIT_TAG        v1.9.2
  GIT_SHALLOW    TRUE)

# ---- CTranslate2 ----
set(WITH_MKL OFF CACHE BOOL "" FORCE)
set(WITH_DNNL OFF CACHE BOOL "" FORCE)
set(WITH_RUY ON CACHE BOOL "" FORCE)
set(OPENMP_RUNTIME "NONE" CACHE STRING "" FORCE)
set(BUILD_CLI OFF CACHE BOOL "" FORCE)
set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
if(APPLE)
  set(WITH_ACCELERATE ON CACHE BOOL "" FORCE)
endif()
FetchContent_Declare(ctranslate2
  GIT_REPOSITORY https://github.com/OpenNMT/CTranslate2
  GIT_TAG        v4.8.1
  GIT_SHALLOW    TRUE)

# ---- SentencePiece ----
set(SPM_ENABLE_SHARED OFF CACHE BOOL "" FORCE)
set(SPM_ENABLE_TCMALLOC OFF CACHE BOOL "" FORCE)
FetchContent_Declare(sentencepiece
  GIT_REPOSITORY https://github.com/google/sentencepiece
  GIT_TAG        v0.2.0
  GIT_SHALLOW    TRUE)

FetchContent_MakeAvailable(whisper ctranslate2 sentencepiece)

# CTranslate2's CMakeLists unset()s CMAKE_POSITION_INDEPENDENT_CODE, so the
# global default doesn't reach its targets; force it so the static lib can be
# linked into our shared library.
foreach(t ctranslate2 ruy cpu_features spdlog)
  if(TARGET ${t})
    set_target_properties(${t} PROPERTIES POSITION_INDEPENDENT_CODE ON)
  endif()
endforeach()

add_library(talmaci_native SHARED src/talmaci_native.cpp)
target_include_directories(talmaci_native
  PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include
  PRIVATE ${sentencepiece_SOURCE_DIR}/src)
target_link_libraries(talmaci_native PRIVATE whisper ctranslate2 sentencepiece-static)

# CTranslate2's install interface isn't needed; include dirs come from the
# build tree targets. SentencePiece's static target lacks a public include dir,
# hence the explicit include path above.

add_executable(talmaci-cli cli/main.cpp)
target_link_libraries(talmaci-cli PRIVATE talmaci_native)

install(TARGETS talmaci_native talmaci-cli)
