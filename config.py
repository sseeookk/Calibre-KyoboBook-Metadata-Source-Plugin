#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2014, YongSeok Choi <sseeookk@gmail.com> based on the Goodreads work by Grant Drake <grant.drake@gmail.com>'
__docformat__ = 'restructuredtext en'

import copy
from functools import partial

#20141108 16:27:50
#from PyQt4 import QtGui
#from PyQt4.Qt import (QLabel,QTableWidgetItem, QVBoxLayout, Qt, QGroupBox, QTableWidget,
#                      QCheckBox, QAbstractItemView, QHBoxLayout, QIcon, QInputDialog)
try:
    from PyQt4 import QtGui
except ImportError:
    from PyQt5 import QtGui
try:
    from PyQt4.Qt import (QLabel,QTableWidgetItem, QVBoxLayout, Qt, QGroupBox, QTableWidget,
                          QCheckBox, QAbstractItemView, QHBoxLayout, QIcon,QInputDialog)
except ImportError:
    from PyQt5.Qt import (QLabel,QTableWidgetItem, QVBoxLayout, Qt, QGroupBox, QTableWidget,
                          QCheckBox, QAbstractItemView, QHBoxLayout, QIcon,QInputDialog)

try:
    from PyQt4.QtGui import (QSpinBox)
except ImportError:
    from PyQt5.Qt import (QSpinBox)
                          
from calibre.gui2 import get_current_db, question_dialog, error_dialog

#20141108
#from calibre.gui2.complete import MultiCompleteLineEdit

from calibre.gui2.metadata.config import ConfigWidget as DefaultConfigWidget
from calibre.utils.config import JSONConfig

from calibre_plugins.kyobobook.common_utils import ReadOnlyTableWidgetItem

STORE_NAME = 'Kyobobook'
KEY_MAX_DOWNLOADS = 'maxDownloads'
KEY_GET_CATEGORY = 'getCategory'
KEY_GET_ALL_AUTHORS = 'getAllAuthors'
KEY_APPEND_TOC = 'appendTOC'

DEFAULT_STORE_VALUES = {
    KEY_MAX_DOWNLOADS: 5,
    KEY_GET_CATEGORY: True,
    KEY_GET_ALL_AUTHORS: False,
    KEY_APPEND_TOC: True
}

# This is where all preferences for this plugin will be stored
plugin_prefs = JSONConfig('plugins/Kyobobook')

# Set defaults
plugin_prefs.defaults[STORE_NAME] = DEFAULT_STORE_VALUES


class ConfigWidget(DefaultConfigWidget):

    def __init__(self, plugin):
        DefaultConfigWidget.__init__(self, plugin)
        c = plugin_prefs[STORE_NAME]
        all_tags = get_current_db().all_tags()

        other_group_box = QGroupBox('Other options', self)
        self.l.addWidget(other_group_box, self.l.rowCount(), 0, 1, 2)
        other_group_box_layout = QVBoxLayout()
        other_group_box.setLayout(other_group_box_layout)

        max_label = QLabel('Maximum title/author search matches to evaluate (1 = fastest):', self)
        max_label.setToolTip('Kyobobook do not always have links to large covers for every ISBN\n'
                             'of the same book. Increasing this value will take effect when doing\n'
                             'title/author searches to consider more ISBN editions.\n\n'
                             'This will increase the potential likelihood of getting a larger cover\n'
                             'though does not guarantee it.')
        other_group_box_layout.addWidget(max_label) #, 0, 0, 1, 1)
        self.max_downloads_spin = QSpinBox(self)
        self.max_downloads_spin.setMinimum(1)
        self.max_downloads_spin.setMaximum(20)
        self.max_downloads_spin.setProperty('value', c.get(KEY_MAX_DOWNLOADS, DEFAULT_STORE_VALUES[KEY_MAX_DOWNLOADS]))
        other_group_box_layout.addWidget(self.max_downloads_spin)#, 0, 1, 1, 1)
        #other_group_box_layout.setColumnStretch(2, 1)


        # by sseeookk, category 20140315
        self.get_category_checkbox = QCheckBox('Add Kyobobook Categories to Calibre tags', self)
        self.get_category_checkbox.setToolTip('Add Kyobobook Categories to Calibre tags(ex, [Domestic Books > History > Korea Culture / History Journey]).')
        self.get_category_checkbox.setChecked(c[KEY_GET_CATEGORY])
        other_group_box_layout.addWidget(self.get_category_checkbox)
        
        
        self.all_authors_checkbox = QCheckBox('Get all contributing authors (e.g. illustrators, series editors etc)', self)
        self.all_authors_checkbox.setToolTip('Kyobobook for some books will list all of the contributing authors and\n'
                                              'the type of contribution like (Editor), (Illustrator) etc.\n\n'
                                              'When this option is checked, all contributing authors are retrieved.\n\n'
                                              'When unchecked (default) only the primary author(s) are returned which\n'
                                              'are those that either have no contribution type specified, or have the\n'
                                              'value of (Kyobobook Author).\n\n'
                                              'If there is no primary author then only those with the same contribution\n'
                                              'type as the first author are returned.\n'
                                              'e.g. "A, B (Illustrator)" will return author A\n'
                                              'e.g. "A (Kyobobook Author)" will return author A\n'
                                              'e.g. "A (Editor), B (Editor), C (Illustrator)" will return authors A & B\n'
                                              'e.g. "A (Editor), B (Series Editor)" will return author A\n')
        self.all_authors_checkbox.setChecked(c[KEY_GET_ALL_AUTHORS])
        other_group_box_layout.addWidget(self.all_authors_checkbox)
        
        # Add by sseeookk, 20140315
        self.toc_checkbox = QCheckBox('Append TOC from Features tab if available to comments', self)
        self.toc_checkbox.setToolTip('Kyobobook for textbooks on their website have a Features tab which\n'
                                      'contains a table of contents for the book. Checking this option will\n'
                                      'append the TOC to the bottom of the Synopsis in the comments field')
        self.toc_checkbox.setChecked(c.get(KEY_APPEND_TOC, DEFAULT_STORE_VALUES[KEY_APPEND_TOC]))
        # other_group_box_layout.addWidget(self.toc_checkbox, 2, 0, 1, 3)
        other_group_box_layout.addWidget(self.toc_checkbox)


    def commit(self):
        DefaultConfigWidget.commit(self)
        new_prefs = {}
        # new_prefs[KEY_MAX_DOWNLOADS] = int(unicode(self.max_downloads_spin.value()))
        new_prefs[KEY_MAX_DOWNLOADS] = int(self.max_downloads_spin.value())
        new_prefs[KEY_GET_CATEGORY] = self.get_category_checkbox.checkState() == Qt.Checked
        new_prefs[KEY_GET_ALL_AUTHORS] = self.all_authors_checkbox.checkState() == Qt.Checked
        new_prefs[KEY_APPEND_TOC] = self.toc_checkbox.checkState() == Qt.Checked
        plugin_prefs[STORE_NAME] = new_prefs
