# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'republish.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QAbstractSpinBox, QApplication, QCheckBox,
    QComboBox, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QSizePolicy,
    QSpacerItem, QSpinBox, QVBoxLayout, QWidget)

class Ui_RePublishTab(object):
    def setupUi(self, RePublishTab):
        if not RePublishTab.objectName():
            RePublishTab.setObjectName(u"RePublishTab")
        RePublishTab.resize(1400, 850)
        self.republishLayout = QVBoxLayout(RePublishTab)
        self.republishLayout.setSpacing(24)
        self.republishLayout.setObjectName(u"republishLayout")
        self.republishLayout.setContentsMargins(24, 24, 24, 24)
        self.republishRenderPathGroupBox = QGroupBox(RePublishTab)
        self.republishRenderPathGroupBox.setObjectName(u"republishRenderPathGroupBox")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.republishRenderPathGroupBox.sizePolicy().hasHeightForWidth())
        self.republishRenderPathGroupBox.setSizePolicy(sizePolicy)
        self.republishRenderPathLayout = QVBoxLayout(self.republishRenderPathGroupBox)
        self.republishRenderPathLayout.setObjectName(u"republishRenderPathLayout")
        self.RePublishRenderPath = QLabel(self.republishRenderPathGroupBox)
        self.RePublishRenderPath.setObjectName(u"RePublishRenderPath")
        self.RePublishRenderPath.setWordWrap(True)
        self.RePublishRenderPath.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.republishRenderPathLayout.addWidget(self.RePublishRenderPath)

        self.republishVersionLayout = QHBoxLayout()
        self.republishVersionLayout.setObjectName(u"republishVersionLayout")
        self.RePublishSourceButton = QPushButton(self.republishRenderPathGroupBox)
        self.RePublishSourceButton.setObjectName(u"RePublishSourceButton")
        self.RePublishSourceButton.setMinimumSize(QSize(140, 28))

        self.republishVersionLayout.addWidget(self.RePublishSourceButton)

        self.RePublishVersionLabel = QLabel(self.republishRenderPathGroupBox)
        self.RePublishVersionLabel.setObjectName(u"RePublishVersionLabel")

        self.republishVersionLayout.addWidget(self.RePublishVersionLabel)

        self.RePublishCurrentVer = QSpinBox(self.republishRenderPathGroupBox)
        self.RePublishCurrentVer.setObjectName(u"RePublishCurrentVer")
        self.RePublishCurrentVer.setMinimumSize(QSize(80, 28))
        self.RePublishCurrentVer.setAlignment(Qt.AlignCenter)
        self.RePublishCurrentVer.setButtonSymbols(QAbstractSpinBox.PlusMinus)
        self.RePublishCurrentVer.setMinimum(0)
        self.RePublishCurrentVer.setMaximum(999)

        self.republishVersionLayout.addWidget(self.RePublishCurrentVer)

        self.RePublishBrowseCustomPath = QPushButton(self.republishRenderPathGroupBox)
        self.RePublishBrowseCustomPath.setObjectName(u"RePublishBrowseCustomPath")
        self.RePublishBrowseCustomPath.setMinimumSize(QSize(100, 28))
        self.RePublishBrowseCustomPath.setVisible(False)

        self.republishVersionLayout.addWidget(self.RePublishBrowseCustomPath)

        self.RePublishScanRenders = QPushButton(self.republishRenderPathGroupBox)
        self.RePublishScanRenders.setObjectName(u"RePublishScanRenders")
        self.RePublishScanRenders.setMinimumSize(QSize(80, 28))

        self.republishVersionLayout.addWidget(self.RePublishScanRenders)

        self.republishVersionSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.republishVersionLayout.addItem(self.republishVersionSpacer)


        self.republishRenderPathLayout.addLayout(self.republishVersionLayout)

        self.republishCustomPathLayout = QHBoxLayout()
        self.republishCustomPathLayout.setObjectName(u"republishCustomPathLayout")
        self.RePublishCustomPathLabel = QLabel(self.republishRenderPathGroupBox)
        self.RePublishCustomPathLabel.setObjectName(u"RePublishCustomPathLabel")
        self.RePublishCustomPathLabel.setVisible(False)

        self.republishCustomPathLayout.addWidget(self.RePublishCustomPathLabel)

        self.RePublishUseCurrentTask = QCheckBox(self.republishRenderPathGroupBox)
        self.RePublishUseCurrentTask.setObjectName(u"RePublishUseCurrentTask")
        self.RePublishUseCurrentTask.setEnabled(False)
        self.RePublishUseCurrentTask.setVisible(False)

        self.republishCustomPathLayout.addWidget(self.RePublishUseCurrentTask)

        self.republishCustomPathSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.republishCustomPathLayout.addItem(self.republishCustomPathSpacer)


        self.republishRenderPathLayout.addLayout(self.republishCustomPathLayout)


        self.republishLayout.addWidget(self.republishRenderPathGroupBox)

        self.republishContentLayout = QHBoxLayout()
        self.republishContentLayout.setSpacing(20)
        self.republishContentLayout.setObjectName(u"republishContentLayout")
        self.republishRendersGroupBox = QGroupBox(RePublishTab)
        self.republishRendersGroupBox.setObjectName(u"republishRendersGroupBox")
        self.republishRendersListLayout = QVBoxLayout(self.republishRendersGroupBox)
        self.republishRendersListLayout.setObjectName(u"republishRendersListLayout")
        self.RePublishRendersList = QListWidget(self.republishRendersGroupBox)
        self.RePublishRendersList.setObjectName(u"RePublishRendersList")
        self.RePublishRendersList.setAlternatingRowColors(True)
        self.RePublishRendersList.setSelectionMode(QAbstractItemView.SingleSelection)

        self.republishRendersListLayout.addWidget(self.RePublishRendersList)


        self.republishContentLayout.addWidget(self.republishRendersGroupBox)

        self.republishOptionsGroupBox = QGroupBox(RePublishTab)
        self.republishOptionsGroupBox.setObjectName(u"republishOptionsGroupBox")
        self.republishOptionsGroupBox.setMinimumSize(QSize(280, 0))
        self.republishOptionsGroupBox.setMaximumSize(QSize(320, 16777215))
        self.republishOptionsLayout = QVBoxLayout(self.republishOptionsGroupBox)
        self.republishOptionsLayout.setObjectName(u"republishOptionsLayout")
        self.RePublishTaskButton = QPushButton(self.republishOptionsGroupBox)
        self.RePublishTaskButton.setObjectName(u"RePublishTaskButton")

        self.republishOptionsLayout.addWidget(self.RePublishTaskButton)

        self.republishOptionsSpacer1 = QSpacerItem(20, 16, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self.republishOptionsLayout.addItem(self.republishOptionsSpacer1)

        self.RePublishUseFarm = QCheckBox(self.republishOptionsGroupBox)
        self.RePublishUseFarm.setObjectName(u"RePublishUseFarm")
        self.RePublishUseFarm.setChecked(False)

        self.republishOptionsLayout.addWidget(self.RePublishUseFarm)

        self.republishOptionsSpacer2 = QSpacerItem(20, 16, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self.republishOptionsLayout.addItem(self.republishOptionsSpacer2)

        self.republishProductNameLabel = QLabel(self.republishOptionsGroupBox)
        self.republishProductNameLabel.setObjectName(u"republishProductNameLabel")

        self.republishOptionsLayout.addWidget(self.republishProductNameLabel)

        self.RePublishProductName = QComboBox(self.republishOptionsGroupBox)
        self.RePublishProductName.setObjectName(u"RePublishProductName")
        self.RePublishProductName.setEditable(True)

        self.republishOptionsLayout.addWidget(self.RePublishProductName)

        self.republishOptionsSpacer3 = QSpacerItem(20, 16, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self.republishOptionsLayout.addItem(self.republishOptionsSpacer3)

        self.RePublishStatusLabel = QLabel(self.republishOptionsGroupBox)
        self.RePublishStatusLabel.setObjectName(u"RePublishStatusLabel")
        self.RePublishStatusLabel.setWordWrap(True)

        self.republishOptionsLayout.addWidget(self.RePublishStatusLabel)

        self.republishOptionsSpacer4 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.republishOptionsLayout.addItem(self.republishOptionsSpacer4)

        self.RePublishPublish = QPushButton(self.republishOptionsGroupBox)
        self.RePublishPublish.setObjectName(u"RePublishPublish")
        self.RePublishPublish.setEnabled(False)
        self.RePublishPublish.setMinimumSize(QSize(0, 50))

        self.republishOptionsLayout.addWidget(self.RePublishPublish)


        self.republishContentLayout.addWidget(self.republishOptionsGroupBox)


        self.republishLayout.addLayout(self.republishContentLayout)


        self.retranslateUi(RePublishTab)

        QMetaObject.connectSlotsByName(RePublishTab)
    # setupUi

    def retranslateUi(self, RePublishTab):
        self.republishRenderPathGroupBox.setTitle(QCoreApplication.translate("RePublishTab", u"Render Path", None))
        self.RePublishRenderPath.setProperty(u"variant", QCoreApplication.translate("RePublishTab", u"path", None))
        self.RePublishRenderPath.setText(QCoreApplication.translate("RePublishTab", u"No path selected", None))
        self.RePublishSourceButton.setProperty(u"role", QCoreApplication.translate("RePublishTab", u"secondary", None))
        self.RePublishSourceButton.setText(QCoreApplication.translate("RePublishTab", u"Source: For Comp", None))
#if QT_CONFIG(tooltip)
        self.RePublishSourceButton.setToolTip(QCoreApplication.translate("RePublishTab", u"Click to select the render source", None))
#endif // QT_CONFIG(tooltip)
        self.RePublishVersionLabel.setText(QCoreApplication.translate("RePublishTab", u"Version:", None))
        self.RePublishBrowseCustomPath.setProperty(u"density", QCoreApplication.translate("RePublishTab", u"sm", None))
        self.RePublishBrowseCustomPath.setProperty(u"role", QCoreApplication.translate("RePublishTab", u"secondary", None))
        self.RePublishBrowseCustomPath.setText(QCoreApplication.translate("RePublishTab", u"Browse...", None))
        self.RePublishScanRenders.setProperty(u"role", QCoreApplication.translate("RePublishTab", u"secondary", None))
#if QT_CONFIG(tooltip)
        self.RePublishScanRenders.setToolTip(QCoreApplication.translate("RePublishTab", u"Rescan version and find render files", None))
#endif // QT_CONFIG(tooltip)
        self.RePublishScanRenders.setText(QCoreApplication.translate("RePublishTab", u"Rescan", None))
        self.RePublishCustomPathLabel.setProperty(u"variant", QCoreApplication.translate("RePublishTab", u"path", None))
        self.RePublishCustomPathLabel.setText(QCoreApplication.translate("RePublishTab", u"Custom path: None", None))
        self.RePublishUseCurrentTask.setText(QCoreApplication.translate("RePublishTab", u"Publish to Current AYON Task", None))
#if QT_CONFIG(tooltip)
        self.RePublishUseCurrentTask.setToolTip(QCoreApplication.translate("RePublishTab", u"When enabled, publishes to the current AYON task context instead of inferring from the custom path", None))
#endif // QT_CONFIG(tooltip)
        self.republishRendersGroupBox.setTitle(QCoreApplication.translate("RePublishTab", u"Renders", None))
#if QT_CONFIG(tooltip)
        self.RePublishRendersList.setToolTip(QCoreApplication.translate("RePublishTab", u"Render sequences found in the current version - select the sequence to publish to AYON", None))
#endif // QT_CONFIG(tooltip)
        self.republishOptionsGroupBox.setTitle(QCoreApplication.translate("RePublishTab", u"Publish Options", None))
        self.RePublishTaskButton.setProperty(u"role", QCoreApplication.translate("RePublishTab", u"secondary", None))
        self.RePublishTaskButton.setText(QCoreApplication.translate("RePublishTab", u"Task: lighting", None))
#if QT_CONFIG(tooltip)
        self.RePublishTaskButton.setToolTip(QCoreApplication.translate("RePublishTab", u"Click to select the task for publishing", None))
#endif // QT_CONFIG(tooltip)
        self.RePublishUseFarm.setText(QCoreApplication.translate("RePublishTab", u"Publish on Farm", None))
        self.republishProductNameLabel.setText(QCoreApplication.translate("RePublishTab", u"Publish To:", None))
#if QT_CONFIG(tooltip)
        self.RePublishProductName.setToolTip(QCoreApplication.translate("RePublishTab", u"Select an existing AYON product or type a new name", None))
#endif // QT_CONFIG(tooltip)
        self.RePublishProductName.setPlaceholderText(QCoreApplication.translate("RePublishTab", u"Select or type product name", None))
        self.RePublishStatusLabel.setProperty(u"textRole", QCoreApplication.translate("RePublishTab", u"help", None))
        self.RePublishStatusLabel.setText(QCoreApplication.translate("RePublishTab", u"Status: Ready", None))
        self.RePublishPublish.setProperty(u"role", QCoreApplication.translate("RePublishTab", u"ayon", None))
#if QT_CONFIG(tooltip)
        self.RePublishPublish.setToolTip(QCoreApplication.translate("RePublishTab", u"Publish the selected render sequence to AYON (Ctrl+Return)", None))
#endif // QT_CONFIG(tooltip)
        self.RePublishPublish.setText(QCoreApplication.translate("RePublishTab", u"Publish to AYON", None))
#if QT_CONFIG(shortcut)
        self.RePublishPublish.setShortcut(QCoreApplication.translate("RePublishTab", u"Ctrl+Return", None))
#endif // QT_CONFIG(shortcut)
        pass
    # retranslateUi

