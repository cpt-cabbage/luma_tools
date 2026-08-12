# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'mp4_maker.ui'
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
    QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QSizePolicy, QSpacerItem,
    QSpinBox, QVBoxLayout, QWidget)

class Ui_MP4MakerTab(object):
    def setupUi(self, MP4MakerTab):
        if not MP4MakerTab.objectName():
            MP4MakerTab.setObjectName(u"MP4MakerTab")
        MP4MakerTab.resize(1400, 850)
        self.mp4Layout = QVBoxLayout(MP4MakerTab)
        self.mp4Layout.setSpacing(24)
        self.mp4Layout.setObjectName(u"mp4Layout")
        self.mp4Layout.setContentsMargins(24, 24, 24, 24)
        self.mp4RenderPathGroupBox = QGroupBox(MP4MakerTab)
        self.mp4RenderPathGroupBox.setObjectName(u"mp4RenderPathGroupBox")
        self.mp4RenderPathLayout = QVBoxLayout(self.mp4RenderPathGroupBox)
        self.mp4RenderPathLayout.setObjectName(u"mp4RenderPathLayout")
        self.MP4RenderPath = QLabel(self.mp4RenderPathGroupBox)
        self.MP4RenderPath.setObjectName(u"MP4RenderPath")
        self.MP4RenderPath.setWordWrap(True)
        self.MP4RenderPath.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.mp4RenderPathLayout.addWidget(self.MP4RenderPath)

        self.mp4VersionLayout = QHBoxLayout()
        self.mp4VersionLayout.setObjectName(u"mp4VersionLayout")
        self.MP4SourceButton = QPushButton(self.mp4RenderPathGroupBox)
        self.MP4SourceButton.setObjectName(u"MP4SourceButton")
        self.MP4SourceButton.setMinimumSize(QSize(140, 28))

        self.mp4VersionLayout.addWidget(self.MP4SourceButton)

        self.mp4VersionLabel = QLabel(self.mp4RenderPathGroupBox)
        self.mp4VersionLabel.setObjectName(u"mp4VersionLabel")

        self.mp4VersionLayout.addWidget(self.mp4VersionLabel)

        self.MP4CurrentVer = QSpinBox(self.mp4RenderPathGroupBox)
        self.MP4CurrentVer.setObjectName(u"MP4CurrentVer")
        self.MP4CurrentVer.setMinimumSize(QSize(80, 28))
        self.MP4CurrentVer.setAlignment(Qt.AlignCenter)
        self.MP4CurrentVer.setButtonSymbols(QAbstractSpinBox.PlusMinus)
        self.MP4CurrentVer.setMinimum(0)
        self.MP4CurrentVer.setMaximum(999)

        self.mp4VersionLayout.addWidget(self.MP4CurrentVer)

        self.MP4BrowseCustomPath = QPushButton(self.mp4RenderPathGroupBox)
        self.MP4BrowseCustomPath.setObjectName(u"MP4BrowseCustomPath")
        self.MP4BrowseCustomPath.setMinimumSize(QSize(100, 28))
        self.MP4BrowseCustomPath.setVisible(False)

        self.mp4VersionLayout.addWidget(self.MP4BrowseCustomPath)

        self.MP4ScanRenders = QPushButton(self.mp4RenderPathGroupBox)
        self.MP4ScanRenders.setObjectName(u"MP4ScanRenders")
        self.MP4ScanRenders.setMinimumSize(QSize(80, 28))

        self.mp4VersionLayout.addWidget(self.MP4ScanRenders)

        self.mp4VersionSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.mp4VersionLayout.addItem(self.mp4VersionSpacer)


        self.mp4RenderPathLayout.addLayout(self.mp4VersionLayout)

        self.mp4CustomPathLayout = QHBoxLayout()
        self.mp4CustomPathLayout.setObjectName(u"mp4CustomPathLayout")
        self.MP4CustomPathLabel = QLabel(self.mp4RenderPathGroupBox)
        self.MP4CustomPathLabel.setObjectName(u"MP4CustomPathLabel")
        self.MP4CustomPathLabel.setStyleSheet(u"color: #888888; font-size: 9pt;")
        self.MP4CustomPathLabel.setVisible(False)

        self.mp4CustomPathLayout.addWidget(self.MP4CustomPathLabel)

        self.mp4CustomPathSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.mp4CustomPathLayout.addItem(self.mp4CustomPathSpacer)


        self.mp4RenderPathLayout.addLayout(self.mp4CustomPathLayout)


        self.mp4Layout.addWidget(self.mp4RenderPathGroupBox)

        self.mp4ContentLayout = QHBoxLayout()
        self.mp4ContentLayout.setSpacing(20)
        self.mp4ContentLayout.setObjectName(u"mp4ContentLayout")
        self.mp4RendersGroupBox = QGroupBox(MP4MakerTab)
        self.mp4RendersGroupBox.setObjectName(u"mp4RendersGroupBox")
        self.mp4RendersLayout = QVBoxLayout(self.mp4RendersGroupBox)
        self.mp4RendersLayout.setObjectName(u"mp4RendersLayout")
        self.MP4RendersList = QListWidget(self.mp4RendersGroupBox)
        self.MP4RendersList.setObjectName(u"MP4RendersList")
        self.MP4RendersList.setAlternatingRowColors(True)
        self.MP4RendersList.setSelectionMode(QAbstractItemView.SingleSelection)

        self.mp4RendersLayout.addWidget(self.MP4RendersList)


        self.mp4ContentLayout.addWidget(self.mp4RendersGroupBox)

        self.mp4OptionsGroupBox = QGroupBox(MP4MakerTab)
        self.mp4OptionsGroupBox.setObjectName(u"mp4OptionsGroupBox")
        self.mp4OptionsGroupBox.setMinimumSize(QSize(280, 0))
        self.mp4OptionsGroupBox.setMaximumSize(QSize(320, 16777215))
        self.mp4OptionsLayout = QVBoxLayout(self.mp4OptionsGroupBox)
        self.mp4OptionsLayout.setObjectName(u"mp4OptionsLayout")
        self.MP4QualityButton = QPushButton(self.mp4OptionsGroupBox)
        self.MP4QualityButton.setObjectName(u"MP4QualityButton")

        self.mp4OptionsLayout.addWidget(self.MP4QualityButton)

        self.mp4OptionsSpacer1 = QSpacerItem(20, 16, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self.mp4OptionsLayout.addItem(self.mp4OptionsSpacer1)

        self.mp4RangeLayout = QHBoxLayout()
        self.mp4RangeLayout.setObjectName(u"mp4RangeLayout")
        self.mp4RangeLabel = QLabel(self.mp4OptionsGroupBox)
        self.mp4RangeLabel.setObjectName(u"mp4RangeLabel")

        self.mp4RangeLayout.addWidget(self.mp4RangeLabel)

        self.MP4StartFrame = QSpinBox(self.mp4OptionsGroupBox)
        self.MP4StartFrame.setObjectName(u"MP4StartFrame")
        self.MP4StartFrame.setMinimumSize(QSize(70, 28))
        self.MP4StartFrame.setAlignment(Qt.AlignCenter)
        self.MP4StartFrame.setMinimum(-999999)
        self.MP4StartFrame.setMaximum(999999)

        self.mp4RangeLayout.addWidget(self.MP4StartFrame)

        self.MP4EndFrame = QSpinBox(self.mp4OptionsGroupBox)
        self.MP4EndFrame.setObjectName(u"MP4EndFrame")
        self.MP4EndFrame.setMinimumSize(QSize(70, 28))
        self.MP4EndFrame.setAlignment(Qt.AlignCenter)
        self.MP4EndFrame.setMinimum(-999999)
        self.MP4EndFrame.setMaximum(999999)

        self.mp4RangeLayout.addWidget(self.MP4EndFrame)

        self.mp4RangeSpacer = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.mp4RangeLayout.addItem(self.mp4RangeSpacer)


        self.mp4OptionsLayout.addLayout(self.mp4RangeLayout)

        self.MP4BurnInTimecode = QCheckBox(self.mp4OptionsGroupBox)
        self.MP4BurnInTimecode.setObjectName(u"MP4BurnInTimecode")

        self.mp4OptionsLayout.addWidget(self.MP4BurnInTimecode)

        self.MP4AddToGallery = QCheckBox(self.mp4OptionsGroupBox)
        self.MP4AddToGallery.setObjectName(u"MP4AddToGallery")
        self.MP4AddToGallery.setChecked(True)

        self.mp4OptionsLayout.addWidget(self.MP4AddToGallery)

        self.MP4PublishToAyon = QCheckBox(self.mp4OptionsGroupBox)
        self.MP4PublishToAyon.setObjectName(u"MP4PublishToAyon")
        self.MP4PublishToAyon.setChecked(False)

        self.mp4OptionsLayout.addWidget(self.MP4PublishToAyon)

        self.MP4PublishOnFarm = QCheckBox(self.mp4OptionsGroupBox)
        self.MP4PublishOnFarm.setObjectName(u"MP4PublishOnFarm")
        self.MP4PublishOnFarm.setChecked(False)
        self.MP4PublishOnFarm.setVisible(False)

        self.mp4OptionsLayout.addWidget(self.MP4PublishOnFarm)

        self.mp4OptionsSpacer2 = QSpacerItem(20, 16, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self.mp4OptionsLayout.addItem(self.mp4OptionsSpacer2)

        self.mp4OutputLabel = QLabel(self.mp4OptionsGroupBox)
        self.mp4OutputLabel.setObjectName(u"mp4OutputLabel")

        self.mp4OptionsLayout.addWidget(self.mp4OutputLabel)

        self.mp4BrowseLayout = QHBoxLayout()
        self.mp4BrowseLayout.setObjectName(u"mp4BrowseLayout")
        self.MP4BrowseOutput = QPushButton(self.mp4OptionsGroupBox)
        self.MP4BrowseOutput.setObjectName(u"MP4BrowseOutput")
        self.MP4BrowseOutput.setMinimumSize(QSize(0, 32))

        self.mp4BrowseLayout.addWidget(self.MP4BrowseOutput)


        self.mp4OptionsLayout.addLayout(self.mp4BrowseLayout)

        self.MP4OutputPath = QLabel(self.mp4OptionsGroupBox)
        self.MP4OutputPath.setObjectName(u"MP4OutputPath")
        self.MP4OutputPath.setWordWrap(True)

        self.mp4OptionsLayout.addWidget(self.MP4OutputPath)

        self.mp4OptionsSpacer3 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.mp4OptionsLayout.addItem(self.mp4OptionsSpacer3)

        self.MP4Generate = QPushButton(self.mp4OptionsGroupBox)
        self.MP4Generate.setObjectName(u"MP4Generate")
        self.MP4Generate.setEnabled(False)
        self.MP4Generate.setMinimumSize(QSize(0, 50))

        self.mp4OptionsLayout.addWidget(self.MP4Generate)


        self.mp4ContentLayout.addWidget(self.mp4OptionsGroupBox)


        self.mp4Layout.addLayout(self.mp4ContentLayout)

        self.MP4StatusLabel = QLabel(MP4MakerTab)
        self.MP4StatusLabel.setObjectName(u"MP4StatusLabel")
        self.MP4StatusLabel.setWordWrap(True)
        self.MP4StatusLabel.setStyleSheet(u"color: #888888; font-size: 9pt;")
        self.MP4StatusLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.mp4Layout.addWidget(self.MP4StatusLabel)


        self.retranslateUi(MP4MakerTab)

        QMetaObject.connectSlotsByName(MP4MakerTab)
    # setupUi

    def retranslateUi(self, MP4MakerTab):
        self.mp4RenderPathGroupBox.setTitle(QCoreApplication.translate("MP4MakerTab", u"Render Path", None))
        self.MP4RenderPath.setText(QCoreApplication.translate("MP4MakerTab", u"No path selected", None))
        self.MP4SourceButton.setText(QCoreApplication.translate("MP4MakerTab", u"Source: For Comp", None))
#if QT_CONFIG(tooltip)
        self.MP4SourceButton.setToolTip(QCoreApplication.translate("MP4MakerTab", u"Click to select the render source", None))
#endif // QT_CONFIG(tooltip)
        self.mp4VersionLabel.setText(QCoreApplication.translate("MP4MakerTab", u"Version:", None))
        self.MP4BrowseCustomPath.setText(QCoreApplication.translate("MP4MakerTab", u"Browse...", None))
#if QT_CONFIG(tooltip)
        self.MP4ScanRenders.setToolTip(QCoreApplication.translate("MP4MakerTab", u"Rescan version and find render files", None))
#endif // QT_CONFIG(tooltip)
        self.MP4ScanRenders.setText(QCoreApplication.translate("MP4MakerTab", u"Rescan", None))
        self.MP4CustomPathLabel.setText(QCoreApplication.translate("MP4MakerTab", u"Custom path: None", None))
        self.mp4RendersGroupBox.setTitle(QCoreApplication.translate("MP4MakerTab", u"Renders", None))
#if QT_CONFIG(tooltip)
        self.MP4RendersList.setToolTip(QCoreApplication.translate("MP4MakerTab", u"Render sequences found in the current version - select the sequence to convert to MP4", None))
#endif // QT_CONFIG(tooltip)
        self.mp4OptionsGroupBox.setTitle(QCoreApplication.translate("MP4MakerTab", u"MP4 Options", None))
        self.MP4QualityButton.setText(QCoreApplication.translate("MP4MakerTab", u"Quality: High (CRF 18)", None))
#if QT_CONFIG(tooltip)
        self.MP4QualityButton.setToolTip(QCoreApplication.translate("MP4MakerTab", u"Click to select output quality (lower CRF = higher quality)", None))
#endif // QT_CONFIG(tooltip)
        self.mp4RangeLabel.setText(QCoreApplication.translate("MP4MakerTab", u"Range:", None))
#if QT_CONFIG(tooltip)
        self.mp4RangeLabel.setToolTip(QCoreApplication.translate("MP4MakerTab", u"Frame range to encode - defaults to the full range of the selected sequence", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.MP4StartFrame.setToolTip(QCoreApplication.translate("MP4MakerTab", u"First frame to encode (clamped to the selected sequence)", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.MP4EndFrame.setToolTip(QCoreApplication.translate("MP4MakerTab", u"Last frame to encode (clamped to the selected sequence)", None))
#endif // QT_CONFIG(tooltip)
        self.MP4BurnInTimecode.setText(QCoreApplication.translate("MP4MakerTab", u"Burn-in Timecode", None))
#if QT_CONFIG(tooltip)
        self.MP4BurnInTimecode.setToolTip(QCoreApplication.translate("MP4MakerTab", u"Draw the frame number onto each frame of the MP4 (requires a system font)", None))
#endif // QT_CONFIG(tooltip)
        self.MP4AddToGallery.setText(QCoreApplication.translate("MP4MakerTab", u"Add to Gallery", None))
#if QT_CONFIG(tooltip)
        self.MP4AddToGallery.setToolTip(QCoreApplication.translate("MP4MakerTab", u"Copy the generated MP4 to your gallery folder for easy browsing", None))
#endif // QT_CONFIG(tooltip)
        self.MP4PublishToAyon.setText(QCoreApplication.translate("MP4MakerTab", u"Publish to AYON", None))
#if QT_CONFIG(tooltip)
        self.MP4PublishToAyon.setToolTip(QCoreApplication.translate("MP4MakerTab", u"Publish the generated MP4 as a review file to AYON. The product name is derived automatically from the MP4 filename (review_<filename>).", None))
#endif // QT_CONFIG(tooltip)
        self.MP4PublishOnFarm.setText(QCoreApplication.translate("MP4MakerTab", u"Publish on Farm", None))
#if QT_CONFIG(tooltip)
        self.MP4PublishOnFarm.setToolTip(QCoreApplication.translate("MP4MakerTab", u"Submit the AYON publish job to Deadline farm instead of publishing locally", None))
#endif // QT_CONFIG(tooltip)
        self.mp4OutputLabel.setText(QCoreApplication.translate("MP4MakerTab", u"Output Location:", None))
        self.MP4BrowseOutput.setText(QCoreApplication.translate("MP4MakerTab", u"Browse...", None))
        self.MP4OutputPath.setText(QCoreApplication.translate("MP4MakerTab", u"No output location selected", None))
        self.MP4OutputPath.setStyleSheet(QCoreApplication.translate("MP4MakerTab", u"color: #888888; font-size: 9pt;", None))
#if QT_CONFIG(tooltip)
        self.MP4Generate.setToolTip(QCoreApplication.translate("MP4MakerTab", u"Generate MP4 from selected render (Ctrl+Return)", None))
#endif // QT_CONFIG(tooltip)
        self.MP4Generate.setText(QCoreApplication.translate("MP4MakerTab", u"Generate MP4", None))
#if QT_CONFIG(shortcut)
        self.MP4Generate.setShortcut(QCoreApplication.translate("MP4MakerTab", u"Ctrl+Return", None))
#endif // QT_CONFIG(shortcut)
        self.MP4StatusLabel.setText("")
        pass
    # retranslateUi

