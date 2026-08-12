# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'cleaner.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QListWidget,
    QListWidgetItem, QProgressBar, QPushButton, QSizePolicy,
    QSlider, QSpacerItem, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget)

class Ui_CleanerTab(object):
    def setupUi(self, CleanerTab):
        if not CleanerTab.objectName():
            CleanerTab.setObjectName(u"CleanerTab")
        CleanerTab.resize(1400, 850)
        self.mainLayout = QVBoxLayout(CleanerTab)
        self.mainLayout.setSpacing(0)
        self.mainLayout.setObjectName(u"mainLayout")
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.cleanerTabWidget = QTabWidget(CleanerTab)
        self.cleanerTabWidget.setObjectName(u"cleanerTabWidget")
        self.shotCleanupTab = QWidget()
        self.shotCleanupTab.setObjectName(u"shotCleanupTab")
        self.shotCleanupLayout = QVBoxLayout(self.shotCleanupTab)
        self.shotCleanupLayout.setSpacing(24)
        self.shotCleanupLayout.setObjectName(u"shotCleanupLayout")
        self.shotCleanupLayout.setContentsMargins(24, 24, 24, 24)
        self.cleanerHeaderLayout = QHBoxLayout()
        self.cleanerHeaderLayout.setObjectName(u"cleanerHeaderLayout")
        self.statsLayout = QVBoxLayout()
        self.statsLayout.setObjectName(u"statsLayout")
        self.FolderSize = QLabel(self.shotCleanupTab)
        self.FolderSize.setObjectName(u"FolderSize")

        self.statsLayout.addWidget(self.FolderSize)

        self.HipNumber = QLabel(self.shotCleanupTab)
        self.HipNumber.setObjectName(u"HipNumber")

        self.statsLayout.addWidget(self.HipNumber)


        self.cleanerHeaderLayout.addLayout(self.statsLayout)

        self.horizontalSpacer_3 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.cleanerHeaderLayout.addItem(self.horizontalSpacer_3)

        self.RescanCleanFiles = QPushButton(self.shotCleanupTab)
        self.RescanCleanFiles.setObjectName(u"RescanCleanFiles")
        self.RescanCleanFiles.setMinimumSize(QSize(120, 35))

        self.cleanerHeaderLayout.addWidget(self.RescanCleanFiles)


        self.shotCleanupLayout.addLayout(self.cleanerHeaderLayout)

        self.listsLayout = QHBoxLayout()
        self.listsLayout.setSpacing(20)
        self.listsLayout.setObjectName(u"listsLayout")
        self.rendersCleanGroupBox = QGroupBox(self.shotCleanupTab)
        self.rendersCleanGroupBox.setObjectName(u"rendersCleanGroupBox")
        self.rendersCleanLayout = QVBoxLayout(self.rendersCleanGroupBox)
        self.rendersCleanLayout.setObjectName(u"rendersCleanLayout")
        self.LatestRender = QLabel(self.rendersCleanGroupBox)
        self.LatestRender.setObjectName(u"LatestRender")
        self.LatestRender.setWordWrap(True)

        self.rendersCleanLayout.addWidget(self.LatestRender)

        self.RendersClean = QListWidget(self.rendersCleanGroupBox)
        self.RendersClean.setObjectName(u"RendersClean")
        self.RendersClean.setAlternatingRowColors(True)
        self.RendersClean.setSelectionMode(QAbstractItemView.MultiSelection)

        self.rendersCleanLayout.addWidget(self.RendersClean)


        self.listsLayout.addWidget(self.rendersCleanGroupBox)

        self.usdsCleanGroupBox = QGroupBox(self.shotCleanupTab)
        self.usdsCleanGroupBox.setObjectName(u"usdsCleanGroupBox")
        self.usdsCleanLayout = QVBoxLayout(self.usdsCleanGroupBox)
        self.usdsCleanLayout.setObjectName(u"usdsCleanLayout")
        self.LatestUSD = QLabel(self.usdsCleanGroupBox)
        self.LatestUSD.setObjectName(u"LatestUSD")
        self.LatestUSD.setWordWrap(True)

        self.usdsCleanLayout.addWidget(self.LatestUSD)

        self.USDSClean = QListWidget(self.usdsCleanGroupBox)
        self.USDSClean.setObjectName(u"USDSClean")
        self.USDSClean.setAlternatingRowColors(True)
        self.USDSClean.setSelectionMode(QAbstractItemView.MultiSelection)

        self.usdsCleanLayout.addWidget(self.USDSClean)


        self.listsLayout.addWidget(self.usdsCleanGroupBox)


        self.shotCleanupLayout.addLayout(self.listsLayout)

        self.cleanOptionsLayout = QHBoxLayout()
        self.cleanOptionsLayout.setObjectName(u"cleanOptionsLayout")
        self.CleanRender = QCheckBox(self.shotCleanupTab)
        self.CleanRender.setObjectName(u"CleanRender")

        self.cleanOptionsLayout.addWidget(self.CleanRender)

        self.CleanUSD = QCheckBox(self.shotCleanupTab)
        self.CleanUSD.setObjectName(u"CleanUSD")

        self.cleanOptionsLayout.addWidget(self.CleanUSD)

        self.HIPBackups = QCheckBox(self.shotCleanupTab)
        self.HIPBackups.setObjectName(u"HIPBackups")

        self.cleanOptionsLayout.addWidget(self.HIPBackups)

        self.HIPBackupsLabel = QLabel(self.shotCleanupTab)
        self.HIPBackupsLabel.setObjectName(u"HIPBackupsLabel")

        self.cleanOptionsLayout.addWidget(self.HIPBackupsLabel)

        self.horizontalSpacer_4 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.cleanOptionsLayout.addItem(self.horizontalSpacer_4)

        self.CleanFiles = QPushButton(self.shotCleanupTab)
        self.CleanFiles.setObjectName(u"CleanFiles")
        self.CleanFiles.setEnabled(False)
        self.CleanFiles.setMinimumSize(QSize(150, 40))

        self.cleanOptionsLayout.addWidget(self.CleanFiles)


        self.shotCleanupLayout.addLayout(self.cleanOptionsLayout)

        self.progressBar = QProgressBar(self.shotCleanupTab)
        self.progressBar.setObjectName(u"progressBar")
        self.progressBar.setMinimumSize(QSize(0, 25))
        self.progressBar.setValue(0)
        self.progressBar.setAlignment(Qt.AlignCenter)
        self.progressBar.setTextVisible(True)

        self.shotCleanupLayout.addWidget(self.progressBar)

        self.cleanerTabWidget.addTab(self.shotCleanupTab, "")
        self.galleryCleanupTab = QWidget()
        self.galleryCleanupTab.setObjectName(u"galleryCleanupTab")
        self.galleryCleanupLayout = QVBoxLayout(self.galleryCleanupTab)
        self.galleryCleanupLayout.setSpacing(16)
        self.galleryCleanupLayout.setObjectName(u"galleryCleanupLayout")
        self.galleryCleanupLayout.setContentsMargins(24, 24, 24, 24)
        self.galleryHeaderLayout = QHBoxLayout()
        self.galleryHeaderLayout.setObjectName(u"galleryHeaderLayout")
        self.galleryStatsLayout = QVBoxLayout()
        self.galleryStatsLayout.setObjectName(u"galleryStatsLayout")
        self.GalleryPathLabel = QLabel(self.galleryCleanupTab)
        self.GalleryPathLabel.setObjectName(u"GalleryPathLabel")

        self.galleryStatsLayout.addWidget(self.GalleryPathLabel)

        self.galleryTotalsLayout = QHBoxLayout()
        self.galleryTotalsLayout.setObjectName(u"galleryTotalsLayout")
        self.GalleryTotalSize = QLabel(self.galleryCleanupTab)
        self.GalleryTotalSize.setObjectName(u"GalleryTotalSize")

        self.galleryTotalsLayout.addWidget(self.GalleryTotalSize)

        self.GalleryTotalFiles = QLabel(self.galleryCleanupTab)
        self.GalleryTotalFiles.setObjectName(u"GalleryTotalFiles")

        self.galleryTotalsLayout.addWidget(self.GalleryTotalFiles)

        self.gallerySpacer1 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.galleryTotalsLayout.addItem(self.gallerySpacer1)


        self.galleryStatsLayout.addLayout(self.galleryTotalsLayout)


        self.galleryHeaderLayout.addLayout(self.galleryStatsLayout)

        self.gallerySpacer2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.galleryHeaderLayout.addItem(self.gallerySpacer2)

        self.GalleryScanButton = QPushButton(self.galleryCleanupTab)
        self.GalleryScanButton.setObjectName(u"GalleryScanButton")
        self.GalleryScanButton.setMinimumSize(QSize(120, 35))

        self.galleryHeaderLayout.addWidget(self.GalleryScanButton)


        self.galleryCleanupLayout.addLayout(self.galleryHeaderLayout)

        self.GalleryStatsTree = QTreeWidget(self.galleryCleanupTab)
        self.GalleryStatsTree.setObjectName(u"GalleryStatsTree")
        self.GalleryStatsTree.setAlternatingRowColors(True)
        self.GalleryStatsTree.setRootIsDecorated(True)
        self.GalleryStatsTree.setUniformRowHeights(True)
        self.GalleryStatsTree.setHeaderHidden(False)

        self.galleryCleanupLayout.addWidget(self.GalleryStatsTree)

        self.galleryAgeLayout = QHBoxLayout()
        self.galleryAgeLayout.setObjectName(u"galleryAgeLayout")
        self.galleryAgeFilterLabel = QLabel(self.galleryCleanupTab)
        self.galleryAgeFilterLabel.setObjectName(u"galleryAgeFilterLabel")

        self.galleryAgeLayout.addWidget(self.galleryAgeFilterLabel)

        self.GalleryAgeSlider = QSlider(self.galleryCleanupTab)
        self.GalleryAgeSlider.setObjectName(u"GalleryAgeSlider")
        self.GalleryAgeSlider.setMinimum(0)
        self.GalleryAgeSlider.setMaximum(365)
        self.GalleryAgeSlider.setValue(0)
        self.GalleryAgeSlider.setOrientation(Qt.Horizontal)
        self.GalleryAgeSlider.setTickPosition(QSlider.TicksBelow)
        self.GalleryAgeSlider.setTickInterval(30)

        self.galleryAgeLayout.addWidget(self.GalleryAgeSlider)

        self.GalleryAgeLabel = QLabel(self.galleryCleanupTab)
        self.GalleryAgeLabel.setObjectName(u"GalleryAgeLabel")
        self.GalleryAgeLabel.setMinimumSize(QSize(100, 0))

        self.galleryAgeLayout.addWidget(self.GalleryAgeLabel)


        self.galleryCleanupLayout.addLayout(self.galleryAgeLayout)

        self.galleryActionLayout = QHBoxLayout()
        self.galleryActionLayout.setObjectName(u"galleryActionLayout")
        self.GalleryPreviewSize = QLabel(self.galleryCleanupTab)
        self.GalleryPreviewSize.setObjectName(u"GalleryPreviewSize")

        self.galleryActionLayout.addWidget(self.GalleryPreviewSize)

        self.gallerySpacer3 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.galleryActionLayout.addItem(self.gallerySpacer3)

        self.GalleryCleanupButton = QPushButton(self.galleryCleanupTab)
        self.GalleryCleanupButton.setObjectName(u"GalleryCleanupButton")
        self.GalleryCleanupButton.setEnabled(False)
        self.GalleryCleanupButton.setMinimumSize(QSize(150, 40))

        self.galleryActionLayout.addWidget(self.GalleryCleanupButton)


        self.galleryCleanupLayout.addLayout(self.galleryActionLayout)

        self.galleryProgressBar = QProgressBar(self.galleryCleanupTab)
        self.galleryProgressBar.setObjectName(u"galleryProgressBar")
        self.galleryProgressBar.setMinimumSize(QSize(0, 25))
        self.galleryProgressBar.setValue(0)
        self.galleryProgressBar.setAlignment(Qt.AlignCenter)
        self.galleryProgressBar.setTextVisible(True)

        self.galleryCleanupLayout.addWidget(self.galleryProgressBar)

        self.cleanerTabWidget.addTab(self.galleryCleanupTab, "")

        self.mainLayout.addWidget(self.cleanerTabWidget)


        self.retranslateUi(CleanerTab)

        self.cleanerTabWidget.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(CleanerTab)
    # setupUi

    def retranslateUi(self, CleanerTab):
        self.FolderSize.setText(QCoreApplication.translate("CleanerTab", u"Total Size: \u2014", None))
        self.HipNumber.setText(QCoreApplication.translate("CleanerTab", u"Amount of Hipfiles: \u2014", None))
        self.RescanCleanFiles.setProperty(u"role", QCoreApplication.translate("CleanerTab", u"secondary", None))
        self.RescanCleanFiles.setText(QCoreApplication.translate("CleanerTab", u"Rescan", None))
#if QT_CONFIG(tooltip)
        self.RescanCleanFiles.setToolTip(QCoreApplication.translate("CleanerTab", u"Scan the shot's task directory for render versions, USD versions, HIP backups and comp usage", None))
#endif // QT_CONFIG(tooltip)
        self.rendersCleanGroupBox.setTitle(QCoreApplication.translate("CleanerTab", u"Renders", None))
        self.LatestRender.setText(QCoreApplication.translate("CleanerTab", u"Latest: None", None))
        self.usdsCleanGroupBox.setTitle(QCoreApplication.translate("CleanerTab", u"USD Files", None))
        self.LatestUSD.setProperty(u"state", QCoreApplication.translate("CleanerTab", u"success", None))
        self.LatestUSD.setProperty(u"textRole", QCoreApplication.translate("CleanerTab", u"label", None))
        self.LatestUSD.setText(QCoreApplication.translate("CleanerTab", u"Latest: None", None))
        self.CleanRender.setText(QCoreApplication.translate("CleanerTab", u"Clean Renders", None))
#if QT_CONFIG(tooltip)
        self.CleanRender.setToolTip(QCoreApplication.translate("CleanerTab", u"Delete the render version folders selected in the Renders list (under img/renders/). The latest render version and any versions referenced by the newest comp file are automatically deselected and kept.", None))
#endif // QT_CONFIG(tooltip)
        self.CleanUSD.setText(QCoreApplication.translate("CleanerTab", u"Clean USDs", None))
#if QT_CONFIG(tooltip)
        self.CleanUSD.setToolTip(QCoreApplication.translate("CleanerTab", u"Delete the USD version folders selected in the USD Files list. The latest USD version is kept (it is never added to the list).", None))
#endif // QT_CONFIG(tooltip)
        self.HIPBackups.setText(QCoreApplication.translate("CleanerTab", u"Clean Backups", None))
#if QT_CONFIG(tooltip)
        self.HIPBackups.setToolTip(QCoreApplication.translate("CleanerTab", u"Delete the entire Houdini auto-backup folder ('backup') for this task. Working HIP files themselves are never touched.", None))
#endif // QT_CONFIG(tooltip)
        self.HIPBackupsLabel.setText("")
        self.CleanFiles.setProperty(u"role", QCoreApplication.translate("CleanerTab", u"danger", None))
        self.CleanFiles.setText(QCoreApplication.translate("CleanerTab", u"Run Cleaner", None))
#if QT_CONFIG(tooltip)
        self.CleanFiles.setToolTip(QCoreApplication.translate("CleanerTab", u"Delete the checked categories after confirmation. Enabled once a scan has found something to clean.", None))
#endif // QT_CONFIG(tooltip)
        self.cleanerTabWidget.setTabText(self.cleanerTabWidget.indexOf(self.shotCleanupTab), QCoreApplication.translate("CleanerTab", u"Shot Cleanup", None))
        self.GalleryPathLabel.setText(QCoreApplication.translate("CleanerTab", u"Gallery: Not configured", None))
        self.GalleryTotalSize.setText(QCoreApplication.translate("CleanerTab", u"Total Size: --", None))
        self.GalleryTotalFiles.setText(QCoreApplication.translate("CleanerTab", u"Total Files: --", None))
        self.GalleryScanButton.setProperty(u"role", QCoreApplication.translate("CleanerTab", u"secondary", None))
        self.GalleryScanButton.setText(QCoreApplication.translate("CleanerTab", u"Scan Gallery", None))
        ___qtreewidgetitem = self.GalleryStatsTree.headerItem()
        ___qtreewidgetitem.setText(2, QCoreApplication.translate("CleanerTab", u"Size", None));
        ___qtreewidgetitem.setText(1, QCoreApplication.translate("CleanerTab", u"Files", None));
        ___qtreewidgetitem.setText(0, QCoreApplication.translate("CleanerTab", u"Category", None));
        self.galleryAgeFilterLabel.setText(QCoreApplication.translate("CleanerTab", u"Older than:", None))
        self.GalleryAgeLabel.setText(QCoreApplication.translate("CleanerTab", u"All ages", None))
        self.GalleryPreviewSize.setText(QCoreApplication.translate("CleanerTab", u"Selected: -- files (--)", None))
        self.GalleryCleanupButton.setProperty(u"role", QCoreApplication.translate("CleanerTab", u"danger", None))
        self.GalleryCleanupButton.setText(QCoreApplication.translate("CleanerTab", u"Delete Selected", None))
        self.cleanerTabWidget.setTabText(self.cleanerTabWidget.indexOf(self.galleryCleanupTab), QCoreApplication.translate("CleanerTab", u"Gallery Cleanup", None))
        pass
    # retranslateUi

