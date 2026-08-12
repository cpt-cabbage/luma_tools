# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'gallery.ui'
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
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QSpacerItem,
    QVBoxLayout, QWidget)

class Ui_GalleryTab(object):
    def setupUi(self, GalleryTab):
        if not GalleryTab.objectName():
            GalleryTab.setObjectName(u"GalleryTab")
        GalleryTab.resize(1400, 850)
        self.galleryMainLayout = QVBoxLayout(GalleryTab)
        self.galleryMainLayout.setSpacing(8)
        self.galleryMainLayout.setObjectName(u"galleryMainLayout")
        self.galleryMainLayout.setContentsMargins(16, 16, 16, 16)
        self.galleryHeaderLayout = QHBoxLayout()
        self.galleryHeaderLayout.setObjectName(u"galleryHeaderLayout")
        self.GalleryUserButton = QPushButton(GalleryTab)
        self.GalleryUserButton.setObjectName(u"GalleryUserButton")

        self.galleryHeaderLayout.addWidget(self.GalleryUserButton)

        self.GallerySortButton = QPushButton(GalleryTab)
        self.GallerySortButton.setObjectName(u"GallerySortButton")

        self.galleryHeaderLayout.addWidget(self.GallerySortButton)

        self.GalleryShortcutsButton = QPushButton(GalleryTab)
        self.GalleryShortcutsButton.setObjectName(u"GalleryShortcutsButton")
        self.GalleryShortcutsButton.setMaximumSize(QSize(34, 16777215))
        self.GalleryShortcutsButton.setFlat(True)

        self.galleryHeaderLayout.addWidget(self.GalleryShortcutsButton)

        self.galleryHeaderSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.galleryHeaderLayout.addItem(self.galleryHeaderSpacer)

        self.GalleryOpenExplorer = QPushButton(GalleryTab)
        self.GalleryOpenExplorer.setObjectName(u"GalleryOpenExplorer")
        self.GalleryOpenExplorer.setMinimumSize(QSize(120, 0))

        self.galleryHeaderLayout.addWidget(self.GalleryOpenExplorer)

        self.GalleryRefresh = QPushButton(GalleryTab)
        self.GalleryRefresh.setObjectName(u"GalleryRefresh")
        self.GalleryRefresh.setMinimumSize(QSize(80, 0))

        self.galleryHeaderLayout.addWidget(self.GalleryRefresh)


        self.galleryMainLayout.addLayout(self.galleryHeaderLayout)

        self.galleryScrollArea = QScrollArea(GalleryTab)
        self.galleryScrollArea.setObjectName(u"galleryScrollArea")
        self.galleryScrollArea.setWidgetResizable(True)
        self.galleryScrollArea.setFrameShape(QFrame.NoFrame)
        self.galleryScrollContent = QWidget()
        self.galleryScrollContent.setObjectName(u"galleryScrollContent")
        self.galleryContentLayout = QVBoxLayout(self.galleryScrollContent)
        self.galleryContentLayout.setObjectName(u"galleryContentLayout")
        self.galleryThumbnailContainer = QWidget(self.galleryScrollContent)
        self.galleryThumbnailContainer.setObjectName(u"galleryThumbnailContainer")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.galleryThumbnailContainer.sizePolicy().hasHeightForWidth())
        self.galleryThumbnailContainer.setSizePolicy(sizePolicy)

        self.galleryContentLayout.addWidget(self.galleryThumbnailContainer)

        self.galleryScrollArea.setWidget(self.galleryScrollContent)

        self.galleryMainLayout.addWidget(self.galleryScrollArea)

        self.galleryFooterLayout = QHBoxLayout()
        self.galleryFooterLayout.setObjectName(u"galleryFooterLayout")
        self.GalleryStatus = QLabel(GalleryTab)
        self.GalleryStatus.setObjectName(u"GalleryStatus")

        self.galleryFooterLayout.addWidget(self.GalleryStatus)

        self.galleryFooterSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.galleryFooterLayout.addItem(self.galleryFooterSpacer)

        self.GalleryViewOnlyLabel = QLabel(GalleryTab)
        self.GalleryViewOnlyLabel.setObjectName(u"GalleryViewOnlyLabel")

        self.galleryFooterLayout.addWidget(self.GalleryViewOnlyLabel)


        self.galleryMainLayout.addLayout(self.galleryFooterLayout)


        self.retranslateUi(GalleryTab)

        QMetaObject.connectSlotsByName(GalleryTab)
    # setupUi

    def retranslateUi(self, GalleryTab):
        self.GalleryUserButton.setProperty(u"role", QCoreApplication.translate("GalleryTab", u"secondary", None))
        self.GalleryUserButton.setText(QCoreApplication.translate("GalleryTab", u"User: You", None))
#if QT_CONFIG(tooltip)
        self.GalleryUserButton.setToolTip(QCoreApplication.translate("GalleryTab", u"Click to select user gallery to view", None))
#endif // QT_CONFIG(tooltip)
        self.GallerySortButton.setProperty(u"role", QCoreApplication.translate("GalleryTab", u"secondary", None))
        self.GallerySortButton.setText(QCoreApplication.translate("GalleryTab", u"Date", None))
#if QT_CONFIG(tooltip)
        self.GallerySortButton.setToolTip(QCoreApplication.translate("GalleryTab", u"Click to change sort field", None))
#endif // QT_CONFIG(tooltip)
        self.GalleryShortcutsButton.setProperty(u"iconOnly", QCoreApplication.translate("GalleryTab", u"true", None))
        self.GalleryShortcutsButton.setProperty(u"role", QCoreApplication.translate("GalleryTab", u"ghost", None))
        self.GalleryShortcutsButton.setText(QCoreApplication.translate("GalleryTab", u"\u2328", None))
#if QT_CONFIG(tooltip)
        self.GalleryShortcutsButton.setToolTip(QCoreApplication.translate("GalleryTab", u"Keyboard shortcuts", None))
#endif // QT_CONFIG(tooltip)
        self.GalleryOpenExplorer.setProperty(u"role", QCoreApplication.translate("GalleryTab", u"secondary", None))
        self.GalleryOpenExplorer.setText(QCoreApplication.translate("GalleryTab", u"Open in Explorer", None))
#if QT_CONFIG(tooltip)
        self.GalleryOpenExplorer.setToolTip(QCoreApplication.translate("GalleryTab", u"Open the gallery folder in Windows Explorer", None))
#endif // QT_CONFIG(tooltip)
        self.GalleryRefresh.setProperty(u"role", QCoreApplication.translate("GalleryTab", u"secondary", None))
        self.GalleryRefresh.setText(QCoreApplication.translate("GalleryTab", u"Refresh", None))
        self.GalleryStatus.setProperty(u"textRole", QCoreApplication.translate("GalleryTab", u"help", None))
        self.GalleryStatus.setText(QCoreApplication.translate("GalleryTab", u"No images found", None))
        self.GalleryViewOnlyLabel.setProperty(u"variant", QCoreApplication.translate("GalleryTab", u"badge", None))
        self.GalleryViewOnlyLabel.setText(QCoreApplication.translate("GalleryTab", u"View Only", None))
        pass
    # retranslateUi

