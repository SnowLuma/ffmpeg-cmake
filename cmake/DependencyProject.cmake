# The dependency projects have their own project() and compiler detection.
if(CMAKE_C_COMPILER_ID STREQUAL "MSVC")
  set(CMAKE_CL_SHOWINCLUDES_PREFIX "Note: including file: ")
  set(CMAKE_MSVC_DEBUG_INFORMATION_FORMAT "$<$<CONFIG:Debug,RelWithDebInfo>:Embedded>")
endif()
if(PROJECT_NAME STREQUAL "harfbuzz")
  # The upstream existing-target path exports a relocatable target reference;
  # its FindFreetype path embeds the original absolute .a/.lib filename.
  find_package(Freetype REQUIRED)
  add_library(freetype ALIAS Freetype::Freetype)
  # HarfBuzz's existing-target branch omits this public integration header.
  install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/hb-ft.h" DESTINATION include/harfbuzz)
endif()
