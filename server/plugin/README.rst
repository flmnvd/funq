Plugin Build
============

This subproject builds the funq server as a plugin with qmake and the C++98
language level.

Build::

  cd server/plugin
  qmake
  make

Or with CMake::

  cd server/plugin
  cmake -S . -B build
  cmake --build build

The resulting plugin is named ``funqserverplugin``.

Loading the plugin instantiates ``FunqServerPlugin``, which starts the funq
TCP server inside the target Qt application.

Compatibility:

* Qt4 uses ``Q_EXPORT_PLUGIN2``.
* Qt5 and Qt6 use ``Q_PLUGIN_METADATA``.
* The qmake project uses C++98. The CMake project uses C++98 for Qt4/Qt5 and
  C++17 for Qt6 because Qt6 itself requires a newer language level.
