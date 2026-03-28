cmake_minimum_required(VERSION 3.5...3.19)
if(${CMAKE_VERSION} VERSION_LESS 3.12)
  cmake_policy(VERSION ${CMAKE_MAJOR_VERSION}.${CMAKE_MINOR_VERSION})
endif()

project(funqserverplugin LANGUAGES CXX)

set(FUNQ_PLUGIN_HEADERS
    funqserverplugin.h
    ../libFunq/delayedresponse.h
    ../libFunq/dragndropresponse.h
    ../libFunq/funq.h
    ../libFunq/json.h
    ../libFunq/jsonclient.h
    ../libFunq/objectpath.h
    ../libFunq/pick.h
    ../libFunq/player.h
    ../libFunq/protocole.h
    ../libFunq/shortcutresponse.h)

set(FUNQ_PLUGIN_SOURCES
    funqserverplugin.cpp
    ../libFunq/delayedresponse.cpp
    ../libFunq/dragndropresponse.cpp
    ../libFunq/funq.cpp
    ../libFunq/json.cpp
    ../libFunq/jsonclient.cpp
    ../libFunq/objectpath.cpp
    ../libFunq/pick.cpp
    ../libFunq/player.cpp
    ../libFunq/protocole.cpp
    ../libFunq/shortcutresponse.cpp)

set(FUNQ_PLUGIN_MOC_HEADERS
    funqserverplugin.h
    ../libFunq/delayedresponse.h
    ../libFunq/funq.h
    ../libFunq/jsonclient.h
    ../libFunq/player.h
    ../libFunq/protocole.h
    ../libFunq/shortcutresponse.h)

include_directories(${CMAKE_CURRENT_SOURCE_DIR}/../libFunq)

if(NOT QT_MAJOR_VERSION)
  find_package(Qt NAMES Qt6 Qt5 QUIET COMPONENTS Core)
  if(Qt_FOUND)
    set(QT_MAJOR_VERSION ${Qt_VERSION_MAJOR})
  else()
    find_package(Qt4 REQUIRED QtCore QtGui QtNetwork QtTest)
    set(QT_MAJOR_VERSION 4)
  endif()
endif()

if(QT_MAJOR_VERSION EQUAL 4)
  include(${QT_USE_FILE})

  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(-std=c++98)
  endif()

  qt4_wrap_cpp(FUNQ_PLUGIN_MOC_SOURCES ${FUNQ_PLUGIN_MOC_HEADERS})

  add_library(funqserverplugin MODULE
              ${FUNQ_PLUGIN_HEADERS}
              ${FUNQ_PLUGIN_SOURCES}
              ${FUNQ_PLUGIN_MOC_SOURCES})
  target_compile_definitions(funqserverplugin PRIVATE QT_NO_RVALUE_REFS)
  target_link_libraries(funqserverplugin
                        ${QT_QTCORE_LIBRARY}
                        ${QT_QTGUI_LIBRARY}
                        ${QT_QTNETWORK_LIBRARY}
                        ${QT_QTTEST_LIBRARY})
else()
  set(CMAKE_AUTOMOC ON)
  set(CMAKE_AUTOUIC OFF)
  set(CMAKE_AUTORCC OFF)

  if(QT_MAJOR_VERSION EQUAL 6)
    set(CMAKE_CXX_STANDARD 17)
  elseif(QT_MAJOR_VERSION EQUAL 5)
    set(CMAKE_CXX_STANDARD 11)
  else()
    set(CMAKE_CXX_STANDARD 98)
  endif()
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
  set(CMAKE_CXX_EXTENSIONS OFF)

  set(QT "Qt${QT_MAJOR_VERSION}")
  find_package(${QT} REQUIRED COMPONENTS Core Gui Network Widgets Test)

  add_library(funqserverplugin MODULE
              ${FUNQ_PLUGIN_HEADERS}
              ${FUNQ_PLUGIN_SOURCES})
  target_link_libraries(funqserverplugin
                        PRIVATE
                        ${QT}::Core
                        ${QT}::Gui
                        ${QT}::Network
                        ${QT}::Widgets
                        ${QT}::Test)
endif()

if(WIN32)
  target_compile_definitions(funqserverplugin PRIVATE UNICODE _UNICODE)
endif()

target_compile_definitions(funqserverplugin PRIVATE QT_NO_DEPRECATED_WARNINGS)
set_target_properties(funqserverplugin PROPERTIES
                      OUTPUT_NAME funqserverplugin)
