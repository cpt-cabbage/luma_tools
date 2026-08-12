# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'logs.ui'
##
## Created by: Qt User Interface Compiler version 6.10.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QCheckBox, QGroupBox, QHBoxLayout,
    QLineEdit, QPushButton, QSizePolicy, QSpacerItem,
    QTextEdit, QVBoxLayout, QWidget)

class Ui_LogsTab(object):
    def setupUi(self, LogsTab):
        if not LogsTab.objectName():
            LogsTab.setObjectName(u"LogsTab")
        LogsTab.resize(1400, 850)
        self.logsMainLayout = QVBoxLayout(LogsTab)
        self.logsMainLayout.setSpacing(24)
        self.logsMainLayout.setObjectName(u"logsMainLayout")
        self.logsMainLayout.setContentsMargins(24, 24, 24, 24)
        self.logOutputGroupBox = QGroupBox(LogsTab)
        self.logOutputGroupBox.setObjectName(u"logOutputGroupBox")
        self.logOutputLayout = QVBoxLayout(self.logOutputGroupBox)
        self.logOutputLayout.setObjectName(u"logOutputLayout")
        self.logToolbarLayout = QHBoxLayout()
        self.logToolbarLayout.setObjectName(u"logToolbarLayout")
        self.LogFilterEdit = QLineEdit(self.logOutputGroupBox)
        self.LogFilterEdit.setObjectName(u"LogFilterEdit")
        self.LogFilterEdit.setClearButtonEnabled(True)
        self.LogFilterEdit.setMaximumSize(QSize(320, 16777215))

        self.logToolbarLayout.addWidget(self.LogFilterEdit)

        self.VerboseLogsCheckbox = QCheckBox(self.logOutputGroupBox)
        self.VerboseLogsCheckbox.setObjectName(u"VerboseLogsCheckbox")

        self.logToolbarLayout.addWidget(self.VerboseLogsCheckbox)

        self.logHorizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.logToolbarLayout.addItem(self.logHorizontalSpacer)

        self.PauseLogButton = QPushButton(self.logOutputGroupBox)
        self.PauseLogButton.setObjectName(u"PauseLogButton")
        self.PauseLogButton.setMinimumSize(QSize(100, 32))
        self.PauseLogButton.setCheckable(True)

        self.logToolbarLayout.addWidget(self.PauseLogButton)

        self.ClearLogButton = QPushButton(self.logOutputGroupBox)
        self.ClearLogButton.setObjectName(u"ClearLogButton")
        self.ClearLogButton.setMinimumSize(QSize(100, 32))

        self.logToolbarLayout.addWidget(self.ClearLogButton)


        self.logOutputLayout.addLayout(self.logToolbarLayout)

        self.LogOutput = QTextEdit(self.logOutputGroupBox)
        self.LogOutput.setObjectName(u"LogOutput")
        self.LogOutput.setReadOnly(True)
        self.LogOutput.setLineWrapMode(QTextEdit.NoWrap)
        font = QFont()
        font.setFamilies([u"Consolas"])
        font.setPointSize(9)
        self.LogOutput.setFont(font)

        self.logOutputLayout.addWidget(self.LogOutput)


        self.logsMainLayout.addWidget(self.logOutputGroupBox)


        self.retranslateUi(LogsTab)

        QMetaObject.connectSlotsByName(LogsTab)
    # setupUi

    def retranslateUi(self, LogsTab):
        self.logOutputGroupBox.setTitle(QCoreApplication.translate("LogsTab", u"Terminal Log Output", None))
        self.LogFilterEdit.setPlaceholderText(QCoreApplication.translate("LogsTab", u"Filter\u2026 (case-insensitive)", None))
#if QT_CONFIG(tooltip)
        self.LogFilterEdit.setToolTip(QCoreApplication.translate("LogsTab", u"Show only log lines containing this text (case-insensitive)", None))
#endif // QT_CONFIG(tooltip)
        self.VerboseLogsCheckbox.setText(QCoreApplication.translate("LogsTab", u"Show debug logs", None))
#if QT_CONFIG(tooltip)
        self.VerboseLogsCheckbox.setToolTip(QCoreApplication.translate("LogsTab", u"Show debug-level messages (Detection, Poll Debug, Batch, etc.) in this view. All messages are always written to the log file.", None))
#endif // QT_CONFIG(tooltip)
        self.PauseLogButton.setProperty(u"role", QCoreApplication.translate("LogsTab", u"secondary", None))
        self.PauseLogButton.setText(QCoreApplication.translate("LogsTab", u"Pause", None))
#if QT_CONFIG(tooltip)
        self.PauseLogButton.setToolTip(QCoreApplication.translate("LogsTab", u"Pause/resume log output", None))
#endif // QT_CONFIG(tooltip)
        self.ClearLogButton.setProperty(u"role", QCoreApplication.translate("LogsTab", u"secondary", None))
        self.ClearLogButton.setText(QCoreApplication.translate("LogsTab", u"Clear Log", None))
#if QT_CONFIG(tooltip)
        self.ClearLogButton.setToolTip(QCoreApplication.translate("LogsTab", u"Clear all log messages", None))
#endif // QT_CONFIG(tooltip)
        self.LogOutput.setPlaceholderText(QCoreApplication.translate("LogsTab", u"Terminal output will appear here...", None))
        pass
    # retranslateUi

