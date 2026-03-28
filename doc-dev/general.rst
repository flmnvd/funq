Funq Overview
=============

Client/server operation
-----------------------

Funq works in **client/server** mode over TCP:

* the server is embedded in the application under test
* the client manipulates the application by sending requests

.. _trames-echanges:

Exchange frames
---------------

The exchanged frames contain plain text in JSON format.

The frame header contains the message size as text, followed by a newline
character **\\n**, followed by the message itself.

For example, this is a valid message::

  26\n{"action": "widgets_list"}

Implementation choices - server side
------------------------------------

The server side is written in C++ with the Qt framework, because the target
applications under test are also based on Qt. It is possible either to inject
code into an already running application with **funq**, or to compile the
application with **libFunq** to embed the server directly into it.

.. note::

  At the moment, code injection on Windows works but is still incomplete. For
  example, testing an application built in DEBUG mode requires **libFunq** to
  be built and installed in DEBUG mode as well. The **funq** executable
  (server-side tool) could choose automatically if both DEBUG and RELEASE
  versions were installed. (TODO)

  Also, the `server/setup.py` script currently supports building only with
  `mingw-32`. (TODO)

Implementation choices - client side
------------------------------------

The client is implemented in Python, and tests should therefore be written in
Python as well.

To run the tests, the **nosetests** library is used. It is a client-side
dependency.

Unit tests
----------

Unit tests are **very important to ensure that fixes or new features do not**
**introduce regressions and that the system continues to behave correctly**.

They must therefore be **run again after every change**, **and extended when
needed**.

SCLE Jenkins should normally provide builds for this. The manual procedure is
described below.

For the server side:

.. code-block:: bash

  cd server/tests
  qmake && make && make check

.. note::

  It is also possible to run the tests with code coverage on Linux:

  .. code-block:: bash

    cd server
    ./run_tests_lcov.sh && firefox test-lcov-html/index.html

For the client side:

.. code-block:: bash

  cd client
  nosetests

.. note::

  To run with coverage:

  .. code-block:: bash

    cd client
    nosetests --with-coverage --cover-package funq

The client side requires the Python **nose** framework [1] to run tests, and
**coverage.py** [2] for coverage.

* [1] https://nose.readthedocs.org/en/latest/
* [2] http://nedbatchelder.com/code/coverage/

Documentation
-------------

Documentation is also very important because it allows **people to use the
tools independently**.

This is especially necessary for the client documentation, **which serves as
guidance for people writing test code based on this framework**.

All project documentation is written in reStructuredText [1] with Sphinx [2].
To generate this type of documentation, go to the documentation directory
(containing at least a `Makefile`, `make.bat`, and `index.rst`) and run the
following command, for example on GNU/Linux to generate HTML:

.. code-block:: bash

  make html
  firefox _build/html/index.html

.. note::

  It is very important to **update** the documentation as soon as it becomes
  outdated or when new features are added.

* [1] http://docutils.sourceforge.net/rst.html
* [2] http://sphinx-doc.org/
