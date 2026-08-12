# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'pass_builder.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QAbstractSpinBox, QApplication, QComboBox,
    QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QSizePolicy, QSpacerItem,
    QSpinBox, QVBoxLayout, QWidget)

class Ui_PassBuilderTab(object):
    def setupUi(self, PassBuilderTab):
        if not PassBuilderTab.objectName():
            PassBuilderTab.setObjectName(u"PassBuilderTab")
        PassBuilderTab.resize(1400, 850)
        self.passBuilderLayout = QVBoxLayout(PassBuilderTab)
        self.passBuilderLayout.setSpacing(24)
        self.passBuilderLayout.setObjectName(u"passBuilderLayout")
        self.passBuilderLayout.setContentsMargins(24, 24, 24, 24)
        self.pathGroupBox = QGroupBox(PassBuilderTab)
        self.pathGroupBox.setObjectName(u"pathGroupBox")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.pathGroupBox.sizePolicy().hasHeightForWidth())
        self.pathGroupBox.setSizePolicy(sizePolicy)
        self.pathLayout = QVBoxLayout(self.pathGroupBox)
        self.pathLayout.setObjectName(u"pathLayout")
        self.RenderPath = QLabel(self.pathGroupBox)
        self.RenderPath.setObjectName(u"RenderPath")
        self.RenderPath.setWordWrap(True)
        self.RenderPath.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.pathLayout.addWidget(self.RenderPath)

        self.versionLayout = QHBoxLayout()
        self.versionLayout.setObjectName(u"versionLayout")
        self.label_3 = QLabel(self.pathGroupBox)
        self.label_3.setObjectName(u"label_3")

        self.versionLayout.addWidget(self.label_3)

        self.CurrentVer = QSpinBox(self.pathGroupBox)
        self.CurrentVer.setObjectName(u"CurrentVer")
        self.CurrentVer.setMinimumSize(QSize(80, 28))
        self.CurrentVer.setAlignment(Qt.AlignCenter)
        self.CurrentVer.setButtonSymbols(QAbstractSpinBox.PlusMinus)
        self.CurrentVer.setMinimum(0)
        self.CurrentVer.setMaximum(999)

        self.versionLayout.addWidget(self.CurrentVer)

        self.ScanRenders = QPushButton(self.pathGroupBox)
        self.ScanRenders.setObjectName(u"ScanRenders")
        self.ScanRenders.setMinimumSize(QSize(100, 32))

        self.versionLayout.addWidget(self.ScanRenders)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.versionLayout.addItem(self.horizontalSpacer)


        self.pathLayout.addLayout(self.versionLayout)


        self.passBuilderLayout.addWidget(self.pathGroupBox)

        self.mainContentLayout = QHBoxLayout()
        self.mainContentLayout.setSpacing(20)
        self.mainContentLayout.setObjectName(u"mainContentLayout")
        self.rendersGroupBox = QGroupBox(PassBuilderTab)
        self.rendersGroupBox.setObjectName(u"rendersGroupBox")
        self.rendersBoxLayout = QVBoxLayout(self.rendersGroupBox)
        self.rendersBoxLayout.setObjectName(u"rendersBoxLayout")
        self.RendersList = QListWidget(self.rendersGroupBox)
        self.RendersList.setObjectName(u"RendersList")
        self.RendersList.setAlternatingRowColors(True)
        self.RendersList.setSelectionMode(QAbstractItemView.SingleSelection)

        self.rendersBoxLayout.addWidget(self.RendersList)


        self.mainContentLayout.addWidget(self.rendersGroupBox)

        self.passesGroupBox = QGroupBox(PassBuilderTab)
        self.passesGroupBox.setObjectName(u"passesGroupBox")
        self.passesBoxLayout = QVBoxLayout(self.passesGroupBox)
        self.passesBoxLayout.setObjectName(u"passesBoxLayout")
        self.passesHint = QLabel(self.passesGroupBox)
        self.passesHint.setObjectName(u"passesHint")
        self.passesHint.setWordWrap(True)
        self.passesHint.setAlignment(Qt.AlignCenter)

        self.passesBoxLayout.addWidget(self.passesHint)

        self.Passes = QListWidget(self.passesGroupBox)
        self.Passes.setObjectName(u"Passes")
        self.Passes.setAlternatingRowColors(True)
        self.Passes.setSelectionMode(QAbstractItemView.MultiSelection)

        self.passesBoxLayout.addWidget(self.Passes)


        self.mainContentLayout.addWidget(self.passesGroupBox)

        self.buildOptionsGroupBox = QGroupBox(PassBuilderTab)
        self.buildOptionsGroupBox.setObjectName(u"buildOptionsGroupBox")
        self.buildOptionsGroupBox.setMinimumSize(QSize(220, 0))
        self.buildOptionsGroupBox.setMaximumSize(QSize(250, 16777215))
        self.buildOptionsLayout = QVBoxLayout(self.buildOptionsGroupBox)
        self.buildOptionsLayout.setSpacing(12)
        self.buildOptionsLayout.setObjectName(u"buildOptionsLayout")
        self.BuildTypeButton = QPushButton(self.buildOptionsGroupBox)
        self.BuildTypeButton.setObjectName(u"BuildTypeButton")
        self.BuildTypeButton.setMinimumSize(QSize(0, 0))

        self.buildOptionsLayout.addWidget(self.BuildTypeButton)

        self.buildOptionsSpacer1 = QSpacerItem(20, 16, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self.buildOptionsLayout.addItem(self.buildOptionsSpacer1)

        self.publishToLabel = QLabel(self.buildOptionsGroupBox)
        self.publishToLabel.setObjectName(u"publishToLabel")

        self.buildOptionsLayout.addWidget(self.publishToLabel)

        self.PublishProductCombo = QComboBox(self.buildOptionsGroupBox)
        self.PublishProductCombo.setObjectName(u"PublishProductCombo")
        self.PublishProductCombo.setEditable(True)

        self.buildOptionsLayout.addWidget(self.PublishProductCombo)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.buildOptionsLayout.addItem(self.verticalSpacer)

        self.BuildPasses = QPushButton(self.buildOptionsGroupBox)
        self.BuildPasses.setObjectName(u"BuildPasses")
        self.BuildPasses.setEnabled(False)
        self.BuildPasses.setMinimumSize(QSize(0, 50))

        self.buildOptionsLayout.addWidget(self.BuildPasses)


        self.mainContentLayout.addWidget(self.buildOptionsGroupBox)


        self.passBuilderLayout.addLayout(self.mainContentLayout)

        self.PassBuilderStatusLabel = QLabel(PassBuilderTab)
        self.PassBuilderStatusLabel.setObjectName(u"PassBuilderStatusLabel")
        self.PassBuilderStatusLabel.setWordWrap(True)
        self.PassBuilderStatusLabel.setStyleSheet(u"color: #888888; font-size: 9pt;")
        self.PassBuilderStatusLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.passBuilderLayout.addWidget(self.PassBuilderStatusLabel)


        self.retranslateUi(PassBuilderTab)

        QMetaObject.connectSlotsByName(PassBuilderTab)
    # setupUi

    def retranslateUi(self, PassBuilderTab):
        self.pathGroupBox.setTitle(QCoreApplication.translate("PassBuilderTab", u"Render Path", None))
        self.RenderPath.setText(QCoreApplication.translate("PassBuilderTab", u"No path selected", None))
        self.label_3.setText(QCoreApplication.translate("PassBuilderTab", u"Version:", None))
        self.ScanRenders.setProperty(u"role", QCoreApplication.translate("PassBuilderTab", u"secondary", None))
#if QT_CONFIG(tooltip)
        self.ScanRenders.setToolTip(QCoreApplication.translate("PassBuilderTab", u"Rescan version and find render files", None))
#endif // QT_CONFIG(tooltip)
        self.ScanRenders.setText(QCoreApplication.translate("PassBuilderTab", u"Rescan", None))
        self.rendersGroupBox.setTitle(QCoreApplication.translate("PassBuilderTab", u"Renders", None))
#if QT_CONFIG(tooltip)
        self.RendersList.setToolTip(QCoreApplication.translate("PassBuilderTab", u"Renders found in the current version - select the sequence you want to update", None))
#endif // QT_CONFIG(tooltip)
        self.passesGroupBox.setTitle(QCoreApplication.translate("PassBuilderTab", u"Available Passes", None))
        self.passesHint.setText(QCoreApplication.translate("PassBuilderTab", u"Defaults (Beauty, Alpha, ...) are always included - select extras here", None))
        self.passesHint.setStyleSheet(QCoreApplication.translate("PassBuilderTab", u"color: #888888; font-style: italic; font-size: 9pt;", None))
#if QT_CONFIG(tooltip)
        self.Passes.setToolTip(QCoreApplication.translate("PassBuilderTab", u"Select the passes you want in the file (multi-select enabled)", None))
#endif // QT_CONFIG(tooltip)
        self.buildOptionsGroupBox.setTitle(QCoreApplication.translate("PassBuilderTab", u"Build Options", None))
        self.BuildTypeButton.setProperty(u"role", QCoreApplication.translate("PassBuilderTab", u"secondary", None))
        self.BuildTypeButton.setText(QCoreApplication.translate("PassBuilderTab", u"Location: Local", None))
#if QT_CONFIG(tooltip)
        self.BuildTypeButton.setToolTip(QCoreApplication.translate("PassBuilderTab", u"Click to choose build location (local PC or render farm)", None))
#endif // QT_CONFIG(tooltip)
        self.publishToLabel.setText(QCoreApplication.translate("PassBuilderTab", u"Publish To:", None))
#if QT_CONFIG(tooltip)
        self.PublishProductCombo.setToolTip(QCoreApplication.translate("PassBuilderTab", u"Select an existing AYON product or type a new name", None))
#endif // QT_CONFIG(tooltip)
        self.PublishProductCombo.setPlaceholderText(QCoreApplication.translate("PassBuilderTab", u"Select or type product name", None))
        self.BuildPasses.setProperty(u"role", QCoreApplication.translate("PassBuilderTab", u"primary", None))
#if QT_CONFIG(tooltip)
        self.BuildPasses.setToolTip(QCoreApplication.translate("PassBuilderTab", u"Build render with selected passes (Ctrl+Return)", None))
#endif // QT_CONFIG(tooltip)
        self.BuildPasses.setText(QCoreApplication.translate("PassBuilderTab", u"Build", None))
#if QT_CONFIG(shortcut)
        self.BuildPasses.setShortcut(QCoreApplication.translate("PassBuilderTab", u"Ctrl+Return", None))
#endif // QT_CONFIG(shortcut)
        self.PassBuilderStatusLabel.setText("")
        pass
    # retranslateUi

