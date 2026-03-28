Funq Server Architecture
========================

The server sources are located in the `cpp` folder.

File tree
---------

* **server/funq.pro**: main qmake build file
* **server/player_tester/**: example application used for manual framework testing
* **server/tests/**: unit test directory
* **server/protocole/**: protocol layer directory
* **server/libFunq/**: `libFunq` library directory
* **server/funq/**: `funq` executable directory (injects `libFunq` into an application)

Adding features (commands available from a client)
--------------------------------------------------

The most important file is **server/libFunq/player.h**, which contains the
definition of the **Player** class.

The public slots defined in this class are automatically callable by a
**client that sends a command with the same name as the slot**.

A client **command** is a JSON object (its raw format is defined here:
:ref:`trames-echanges`) that contains at least one key named **"action"**
whose **value is the command name**.

For example, here is the implementation of the **quit** command (which exits
the `QApplication`) on the C++ side.

player.h:

.. code-block:: cpp

  public slots:
    ...
    QtJson::JsonObject quit(const QtJson::JsonObject & command);

player.cpp:

.. code-block:: cpp

  QtJson::JsonObject Player::quit(const QtJson::JsonObject &) {
      if (qApp) {
          qApp->exit();
      }
      QtJson::JsonObject result;
      return result;
  }

To trigger this command from the client side, the following JSON object must be
sent over the network (here without the frame header defined in
:ref:`trames-echanges`):

.. code-block:: python

  {"action": "quit"}

And the server response will be an empty JSON object.

.. note::

  The important point to remember is that on the server side, adding a slot
  with the proper signature automatically adds a command.

.. note::

  The files **server/libFunq/player.h** and **server/libFunq/player.cpp** are a
  good starting point for learning how to add and implement commands.

Contents of the *server/libFunq/player.h* file
----------------------------------------------

Below is the content of `player.h`. For a full understanding, refer to the
complete sources in **server/libFunq**.

.. literalinclude:: ../server/libFunq/player.h
  :language: cpp
