How to find widget's paths
==========================

Currently there is two ways fo ind widget's paths, and it is explained
in this section.

With **funq**
-------------

The easiest way is to start **funq** executable (from *funq-server*
package) in *pick mode*.

For example, to find widgets from qtcreator application:

.. code-block:: bash

  funq --pick qtcreator

Then you need to pick on a widget while pressing *Ctrl* and *Shift*.
This will print on stdout the complete widget path and the available
properties.

Here is an example of output when clicking on the "File" menu in qtcreator::

  WIDGET: `Core:_:Internal:_:MainWindow-0::QtCreator.MenuBar` (pos: 42, 12)
  	objectName: QtCreator.MenuBar
  	modal: false
  	windowModality: 0
  	enabled: true
  	x: 0
  	y: 0
  	width: 1091
  	height: 25
  	minimumWidth: 0
  	minimumHeight: 0
  	maximumWidth: 16777215
  	maximumHeight: 16777215
  	font: Sans,10,-1,0,50,0,0,0,0,0
  	mouseTracking: true
  	isActiveWindow: true
  	focusPolicy: 0
  	focus: false
  	contextMenuPolicy: 1
  	updatesEnabled: true
  	visible: true
  	minimized: false
  	maximized: false
  	fullScreen: false
  	acceptDrops: false
  	windowOpacity: 1
  	windowModified: false
  	layoutDirection: 0
  	autoFillBackground: false
  	inputMethodHints: 0
  	defaultUp: false
  	nativeMenuBar: false

In object paths, ``::`` is the separator between QObject path components. If a
real Qt object name itself contains ``::``, Funq escapes it as ``:_:`` inside
the path.

For example::

  Core:_:Internal:_:MainWindow-0::QtCreator.MenuBar

means:

* top-level object name: ``Core::Internal::MainWindow-0``
* child object name: ``QtCreator.MenuBar``

So ``:_:`` inside one path component means a literal ``::`` in the original
QObject name, not another path level.

Xml dump of all widgets
-----------------------

It is also possible to dump widgets of the running application. This may
only be used in a test::

  from funq.testcase import FunqTestCase

  class MyTestCase(FunqTestCase):
      __app_config_name__ = 'applitest'

      def test_my_first_test(self):
          # this will write a "dump.json" file
          self.funq.dump_widgets_list('dump.json')

Lookup by property
------------------

You can also retrieve a QObject directly by one of its properties instead of
using a full QObject path.

For example, to find a button by its displayed text::

  ok_button = self.funq.widget(property_name='text', property_value='OK')
  ok_button.click()

For a generic QObject, use :meth:`funq.client.FunqClient.object`::

  label = self.funq.object(property_name='objectName',
                           property_value='statusLabel')
  self.assertEqual(label.properties()['text'], 'Ready')

Property-based lookup must match exactly one object:

* no match: ``ObjectNotFound``
* more than one match: ``AmbiguousObjectMatch``

In both cases, Funq raises an exception and the test fails.
