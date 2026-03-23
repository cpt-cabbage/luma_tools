# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'canvas.ui'
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
    QPushButton, QSizePolicy, QSlider, QSpacerItem,
    QToolButton, QVBoxLayout, QWidget)
class Ui_CanvasTab(object):
    def setupUi(self, CanvasTab):
        if not CanvasTab.objectName():
            CanvasTab.setObjectName(u"CanvasTab")
        CanvasTab.resize(1400, 850)
        self.canvasMainLayout = QVBoxLayout(CanvasTab)
        self.canvasMainLayout.setSpacing(0)
        self.canvasMainLayout.setObjectName(u"canvasMainLayout")
        self.canvasMainLayout.setContentsMargins(0, 0, 0, 0)
        self.CanvasToolbar = QFrame(CanvasTab)
        self.CanvasToolbar.setObjectName(u"CanvasToolbar")
        self.CanvasToolbar.setFrameShape(QFrame.NoFrame)
        self.CanvasToolbar.setMinimumSize(QSize(0, 36))
        self.toolbarMainLayout = QHBoxLayout(self.CanvasToolbar)
        self.toolbarMainLayout.setSpacing(4)
        self.toolbarMainLayout.setObjectName(u"toolbarMainLayout")
        self.toolbarMainLayout.setContentsMargins(8, 4, 8, 4)
        self.CanvasDropdown = QToolButton(self.CanvasToolbar)
        self.CanvasDropdown.setObjectName(u"CanvasDropdown")
        self.CanvasDropdown.setPopupMode(QToolButton.InstantPopup)
        self.CanvasDropdown.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.CanvasDropdown.setMinimumSize(QSize(150, 26))

        self.toolbarMainLayout.addWidget(self.CanvasDropdown)

        self.sepCanvas = QFrame(self.CanvasToolbar)
        self.sepCanvas.setObjectName(u"sepCanvas")
        self.sepCanvas.setFrameShape(QFrame.VLine)
        self.sepCanvas.setFrameShadow(QFrame.Sunken)

        self.toolbarMainLayout.addWidget(self.sepCanvas)

        self.labelFile = QLabel(self.CanvasToolbar)
        self.labelFile.setObjectName(u"labelFile")

        self.toolbarMainLayout.addWidget(self.labelFile)

        self.CanvasFileMenu = QPushButton(self.CanvasToolbar)
        self.CanvasFileMenu.setObjectName(u"CanvasFileMenu")
        self.CanvasFileMenu.setMinimumSize(QSize(90, 26))

        self.toolbarMainLayout.addWidget(self.CanvasFileMenu)

        self.sep1 = QFrame(self.CanvasToolbar)
        self.sep1.setObjectName(u"sep1")
        self.sep1.setFrameShape(QFrame.VLine)
        self.sep1.setFrameShadow(QFrame.Sunken)

        self.toolbarMainLayout.addWidget(self.sep1)

        self.labelEdit = QLabel(self.CanvasToolbar)
        self.labelEdit.setObjectName(u"labelEdit")

        self.toolbarMainLayout.addWidget(self.labelEdit)

        self.CanvasUndo = QPushButton(self.CanvasToolbar)
        self.CanvasUndo.setObjectName(u"CanvasUndo")
        self.CanvasUndo.setEnabled(False)
        self.CanvasUndo.setMinimumSize(QSize(55, 26))

        self.toolbarMainLayout.addWidget(self.CanvasUndo)

        self.CanvasRedo = QPushButton(self.CanvasToolbar)
        self.CanvasRedo.setObjectName(u"CanvasRedo")
        self.CanvasRedo.setEnabled(False)
        self.CanvasRedo.setMinimumSize(QSize(55, 26))

        self.toolbarMainLayout.addWidget(self.CanvasRedo)

        self.sep2 = QFrame(self.CanvasToolbar)
        self.sep2.setObjectName(u"sep2")
        self.sep2.setFrameShape(QFrame.VLine)
        self.sep2.setFrameShadow(QFrame.Sunken)

        self.toolbarMainLayout.addWidget(self.sep2)

        self.labelTools = QLabel(self.CanvasToolbar)
        self.labelTools.setObjectName(u"labelTools")

        self.toolbarMainLayout.addWidget(self.labelTools)

        self.CanvasToolSelect = QPushButton(self.CanvasToolbar)
        self.CanvasToolSelect.setObjectName(u"CanvasToolSelect")
        self.CanvasToolSelect.setCheckable(True)
        self.CanvasToolSelect.setChecked(True)
        self.CanvasToolSelect.setMinimumSize(QSize(70, 26))

        self.toolbarMainLayout.addWidget(self.CanvasToolSelect)

        self.CanvasToolPan = QPushButton(self.CanvasToolbar)
        self.CanvasToolPan.setObjectName(u"CanvasToolPan")
        self.CanvasToolPan.setCheckable(True)
        self.CanvasToolPan.setMinimumSize(QSize(60, 26))

        self.toolbarMainLayout.addWidget(self.CanvasToolPan)

        self.CanvasToolConnect = QPushButton(self.CanvasToolbar)
        self.CanvasToolConnect.setObjectName(u"CanvasToolConnect")
        self.CanvasToolConnect.setCheckable(True)
        self.CanvasToolConnect.setMinimumSize(QSize(80, 26))

        self.toolbarMainLayout.addWidget(self.CanvasToolConnect)

        self.CanvasToolAnnotate = QPushButton(self.CanvasToolbar)
        self.CanvasToolAnnotate.setObjectName(u"CanvasToolAnnotate")
        self.CanvasToolAnnotate.setCheckable(True)
        self.CanvasToolAnnotate.setMinimumSize(QSize(65, 26))

        self.toolbarMainLayout.addWidget(self.CanvasToolAnnotate)

        self.CanvasToolGroup = QPushButton(self.CanvasToolbar)
        self.CanvasToolGroup.setObjectName(u"CanvasToolGroup")
        self.CanvasToolGroup.setCheckable(True)
        self.CanvasToolGroup.setMinimumSize(QSize(60, 26))

        self.toolbarMainLayout.addWidget(self.CanvasToolGroup)

        self.CanvasToolCrop = QPushButton(self.CanvasToolbar)
        self.CanvasToolCrop.setObjectName(u"CanvasToolCrop")
        self.CanvasToolCrop.setCheckable(True)
        self.CanvasToolCrop.setMinimumSize(QSize(65, 26))

        self.toolbarMainLayout.addWidget(self.CanvasToolCrop)

        self.CanvasToolDraw = QPushButton(self.CanvasToolbar)
        self.CanvasToolDraw.setObjectName(u"CanvasToolDraw")
        self.CanvasToolDraw.setCheckable(True)
        self.CanvasToolDraw.setMinimumSize(QSize(70, 26))

        self.toolbarMainLayout.addWidget(self.CanvasToolDraw)

        self.sep3 = QFrame(self.CanvasToolbar)
        self.sep3.setObjectName(u"sep3")
        self.sep3.setFrameShape(QFrame.VLine)
        self.sep3.setFrameShadow(QFrame.Sunken)

        self.toolbarMainLayout.addWidget(self.sep3)

        self.CanvasViewMenu = QPushButton(self.CanvasToolbar)
        self.CanvasViewMenu.setObjectName(u"CanvasViewMenu")
        self.CanvasViewMenu.setMinimumSize(QSize(70, 26))

        self.toolbarMainLayout.addWidget(self.CanvasViewMenu)

        self.toolbarSpacer1 = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.toolbarMainLayout.addItem(self.toolbarSpacer1)

        self.CanvasToolbarToggle = QPushButton(self.CanvasToolbar)
        self.CanvasToolbarToggle.setObjectName(u"CanvasToolbarToggle")
        self.CanvasToolbarToggle.setMinimumSize(QSize(36, 26))
        self.CanvasToolbarToggle.setMaximumSize(QSize(36, 26))

        self.toolbarMainLayout.addWidget(self.CanvasToolbarToggle)


        self.canvasMainLayout.addWidget(self.CanvasToolbar)

        self.CanvasToolbarContent = QWidget(CanvasTab)
        self.CanvasToolbarContent.setObjectName(u"CanvasToolbarContent")
        self.CanvasToolbarContent.setMinimumSize(QSize(0, 34))
        self.toolbarSecondaryLayout = QHBoxLayout(self.CanvasToolbarContent)
        self.toolbarSecondaryLayout.setSpacing(4)
        self.toolbarSecondaryLayout.setObjectName(u"toolbarSecondaryLayout")
        self.toolbarSecondaryLayout.setContentsMargins(8, 3, 8, 3)
        self.labelGrid = QLabel(self.CanvasToolbarContent)
        self.labelGrid.setObjectName(u"labelGrid")

        self.toolbarSecondaryLayout.addWidget(self.labelGrid)

        self.CanvasToggleGrid = QPushButton(self.CanvasToolbarContent)
        self.CanvasToggleGrid.setObjectName(u"CanvasToggleGrid")
        self.CanvasToggleGrid.setCheckable(True)
        self.CanvasToggleGrid.setMinimumSize(QSize(50, 24))

        self.toolbarSecondaryLayout.addWidget(self.CanvasToggleGrid)

        self.CanvasToggleSnap = QPushButton(self.CanvasToolbarContent)
        self.CanvasToggleSnap.setObjectName(u"CanvasToggleSnap")
        self.CanvasToggleSnap.setCheckable(True)
        self.CanvasToggleSnap.setMinimumSize(QSize(50, 24))

        self.toolbarSecondaryLayout.addWidget(self.CanvasToggleSnap)

        self.sep5 = QFrame(self.CanvasToolbarContent)
        self.sep5.setObjectName(u"sep5")
        self.sep5.setFrameShape(QFrame.VLine)
        self.sep5.setFrameShadow(QFrame.Sunken)

        self.toolbarSecondaryLayout.addWidget(self.sep5)

        self.labelZoom = QLabel(self.CanvasToolbarContent)
        self.labelZoom.setObjectName(u"labelZoom")

        self.toolbarSecondaryLayout.addWidget(self.labelZoom)

        self.CanvasZoomSlider = QSlider(self.CanvasToolbarContent)
        self.CanvasZoomSlider.setObjectName(u"CanvasZoomSlider")
        self.CanvasZoomSlider.setMinimum(5)
        self.CanvasZoomSlider.setMaximum(320)
        self.CanvasZoomSlider.setValue(100)
        self.CanvasZoomSlider.setOrientation(Qt.Horizontal)
        self.CanvasZoomSlider.setMinimumSize(QSize(100, 0))
        self.CanvasZoomSlider.setMaximumSize(QSize(140, 16777215))

        self.toolbarSecondaryLayout.addWidget(self.CanvasZoomSlider)

        self.CanvasZoomPercent = QLabel(self.CanvasToolbarContent)
        self.CanvasZoomPercent.setObjectName(u"CanvasZoomPercent")
        self.CanvasZoomPercent.setMinimumSize(QSize(40, 0))
        self.CanvasZoomPercent.setAlignment(Qt.AlignRight|Qt.AlignVCenter)

        self.toolbarSecondaryLayout.addWidget(self.CanvasZoomPercent)

        self.CanvasFitAll = QPushButton(self.CanvasToolbarContent)
        self.CanvasFitAll.setObjectName(u"CanvasFitAll")
        self.CanvasFitAll.setMinimumSize(QSize(55, 24))

        self.toolbarSecondaryLayout.addWidget(self.CanvasFitAll)

        self.CanvasFitSelection = QPushButton(self.CanvasToolbarContent)
        self.CanvasFitSelection.setObjectName(u"CanvasFitSelection")
        self.CanvasFitSelection.setEnabled(False)
        self.CanvasFitSelection.setMinimumSize(QSize(55, 24))

        self.toolbarSecondaryLayout.addWidget(self.CanvasFitSelection)

        self.CanvasResetZoom = QPushButton(self.CanvasToolbarContent)
        self.CanvasResetZoom.setObjectName(u"CanvasResetZoom")
        self.CanvasResetZoom.setMinimumSize(QSize(45, 24))

        self.toolbarSecondaryLayout.addWidget(self.CanvasResetZoom)

        self.CanvasGoOrigin = QPushButton(self.CanvasToolbarContent)
        self.CanvasGoOrigin.setObjectName(u"CanvasGoOrigin")
        self.CanvasGoOrigin.setMinimumSize(QSize(50, 24))

        self.toolbarSecondaryLayout.addWidget(self.CanvasGoOrigin)

        self.toolbarSpacer2 = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.toolbarSecondaryLayout.addItem(self.toolbarSpacer2)

        self.CanvasColorSampler = QPushButton(self.CanvasToolbarContent)
        self.CanvasColorSampler.setObjectName(u"CanvasColorSampler")
        self.CanvasColorSampler.setMinimumSize(QSize(65, 24))

        self.toolbarSecondaryLayout.addWidget(self.CanvasColorSampler)


        self.canvasMainLayout.addWidget(self.CanvasToolbarContent)

        self.CanvasContentArea = QWidget(CanvasTab)
        self.CanvasContentArea.setObjectName(u"CanvasContentArea")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.CanvasContentArea.sizePolicy().hasHeightForWidth())
        self.CanvasContentArea.setSizePolicy(sizePolicy)
        self.contentAreaLayout = QHBoxLayout(self.CanvasContentArea)
        self.contentAreaLayout.setSpacing(0)
        self.contentAreaLayout.setObjectName(u"contentAreaLayout")
        self.contentAreaLayout.setContentsMargins(0, 0, 0, 0)
        self.CanvasContainer = QWidget(self.CanvasContentArea)
        self.CanvasContainer.setObjectName(u"CanvasContainer")
        sizePolicy.setHeightForWidth(self.CanvasContainer.sizePolicy().hasHeightForWidth())
        self.CanvasContainer.setSizePolicy(sizePolicy)

        self.contentAreaLayout.addWidget(self.CanvasContainer)

        self.CanvasMinimapContainer = QFrame(self.CanvasContentArea)
        self.CanvasMinimapContainer.setObjectName(u"CanvasMinimapContainer")
        self.CanvasMinimapContainer.setMinimumSize(QSize(150, 100))
        self.CanvasMinimapContainer.setMaximumSize(QSize(200, 150))
        self.CanvasMinimapContainer.setFrameShape(QFrame.Box)
        self.CanvasMinimapContainer.setVisible(False)
        self.minimapLayout = QVBoxLayout(self.CanvasMinimapContainer)
        self.minimapLayout.setSpacing(0)
        self.minimapLayout.setObjectName(u"minimapLayout")
        self.minimapLayout.setContentsMargins(2, 2, 2, 2)
        self.CanvasMinimapLabel = QLabel(self.CanvasMinimapContainer)
        self.CanvasMinimapLabel.setObjectName(u"CanvasMinimapLabel")
        self.CanvasMinimapLabel.setAlignment(Qt.AlignCenter)

        self.minimapLayout.addWidget(self.CanvasMinimapLabel)


        self.contentAreaLayout.addWidget(self.CanvasMinimapContainer)


        self.canvasMainLayout.addWidget(self.CanvasContentArea)

        self.CanvasStatusBar = QFrame(CanvasTab)
        self.CanvasStatusBar.setObjectName(u"CanvasStatusBar")
        self.CanvasStatusBar.setFrameShape(QFrame.NoFrame)
        self.CanvasStatusBar.setMinimumSize(QSize(0, 24))
        self.CanvasStatusBar.setMaximumSize(QSize(16777215, 24))
        self.statusBarLayout = QHBoxLayout(self.CanvasStatusBar)
        self.statusBarLayout.setSpacing(16)
        self.statusBarLayout.setObjectName(u"statusBarLayout")
        self.statusBarLayout.setContentsMargins(8, 2, 8, 2)
        self.CanvasCoordinates = QLabel(self.CanvasStatusBar)
        self.CanvasCoordinates.setObjectName(u"CanvasCoordinates")
        self.CanvasCoordinates.setMinimumSize(QSize(120, 0))

        self.statusBarLayout.addWidget(self.CanvasCoordinates)

        self.CanvasToolHint = QLabel(self.CanvasStatusBar)
        self.CanvasToolHint.setObjectName(u"CanvasToolHint")

        self.statusBarLayout.addWidget(self.CanvasToolHint)

        self.statusSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.statusBarLayout.addItem(self.statusSpacer)

        self.CanvasSelectionInfo = QLabel(self.CanvasStatusBar)
        self.CanvasSelectionInfo.setObjectName(u"CanvasSelectionInfo")

        self.statusBarLayout.addWidget(self.CanvasSelectionInfo)


        self.canvasMainLayout.addWidget(self.CanvasStatusBar)


        self.retranslateUi(CanvasTab)

        QMetaObject.connectSlotsByName(CanvasTab)
    # setupUi

    def retranslateUi(self, CanvasTab):
        self.CanvasToolbar.setStyleSheet(QCoreApplication.translate("CanvasTab", u"QFrame#CanvasToolbar { background-color: #2d2d2d; border-bottom: 1px solid #1a1a1a; }", None))
        self.CanvasDropdown.setText(QCoreApplication.translate("CanvasTab", u"Canvas: (none)", None))
#if QT_CONFIG(tooltip)
        self.CanvasDropdown.setToolTip(QCoreApplication.translate("CanvasTab", u"Switch canvas or create new", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasDropdown.setStyleSheet(QCoreApplication.translate("CanvasTab", u"QToolButton { color: #4a9eff; font-weight: bold; padding: 4px 8px; }\n"
"QToolButton::menu-indicator { image: none; width: 0px; }", None))
        self.sepCanvas.setStyleSheet(QCoreApplication.translate("CanvasTab", u"color: #444;", None))
        self.labelFile.setText(QCoreApplication.translate("CanvasTab", u"File:", None))
        self.labelFile.setStyleSheet(QCoreApplication.translate("CanvasTab", u"color: #888; font-weight: bold;", None))
        self.CanvasFileMenu.setText(QCoreApplication.translate("CanvasTab", u"Export/Import", None))
#if QT_CONFIG(tooltip)
        self.CanvasFileMenu.setToolTip(QCoreApplication.translate("CanvasTab", u"Export canvas to .luma file or import from file", None))
#endif // QT_CONFIG(tooltip)
        self.sep1.setStyleSheet(QCoreApplication.translate("CanvasTab", u"color: #444;", None))
        self.labelEdit.setText(QCoreApplication.translate("CanvasTab", u"Edit:", None))
        self.labelEdit.setStyleSheet(QCoreApplication.translate("CanvasTab", u"color: #888; font-weight: bold;", None))
        self.CanvasUndo.setText(QCoreApplication.translate("CanvasTab", u"Undo", None))
#if QT_CONFIG(tooltip)
        self.CanvasUndo.setToolTip(QCoreApplication.translate("CanvasTab", u"Undo last action (Ctrl+Z)", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasRedo.setText(QCoreApplication.translate("CanvasTab", u"Redo", None))
#if QT_CONFIG(tooltip)
        self.CanvasRedo.setToolTip(QCoreApplication.translate("CanvasTab", u"Redo last action (Ctrl+Y)", None))
#endif // QT_CONFIG(tooltip)
        self.sep2.setStyleSheet(QCoreApplication.translate("CanvasTab", u"color: #444;", None))
        self.labelTools.setText(QCoreApplication.translate("CanvasTab", u"Tools:", None))
        self.labelTools.setStyleSheet(QCoreApplication.translate("CanvasTab", u"color: #888; font-weight: bold;", None))
        self.CanvasToolSelect.setText(QCoreApplication.translate("CanvasTab", u"Select [V]", None))
#if QT_CONFIG(tooltip)
        self.CanvasToolSelect.setToolTip(QCoreApplication.translate("CanvasTab", u"Select and move items - click to select, drag to move, Shift+click for multi-select", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasToolPan.setText(QCoreApplication.translate("CanvasTab", u"Pan [H]", None))
#if QT_CONFIG(tooltip)
        self.CanvasToolPan.setToolTip(QCoreApplication.translate("CanvasTab", u"Pan the canvas - also works with Space+Drag or Middle Mouse", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasToolConnect.setText(QCoreApplication.translate("CanvasTab", u"Connect [C]", None))
#if QT_CONFIG(tooltip)
        self.CanvasToolConnect.setToolTip(QCoreApplication.translate("CanvasTab", u"Draw connections between images to show relationships", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasToolAnnotate.setText(QCoreApplication.translate("CanvasTab", u"Note [N]", None))
#if QT_CONFIG(tooltip)
        self.CanvasToolAnnotate.setToolTip(QCoreApplication.translate("CanvasTab", u"Add sticky notes to the canvas", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasToolGroup.setText(QCoreApplication.translate("CanvasTab", u"Region", None))
#if QT_CONFIG(tooltip)
        self.CanvasToolGroup.setToolTip(QCoreApplication.translate("CanvasTab", u"Create a colored region to group items visually", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasToolCrop.setText(QCoreApplication.translate("CanvasTab", u"Crop [K]", None))
#if QT_CONFIG(tooltip)
        self.CanvasToolCrop.setToolTip(QCoreApplication.translate("CanvasTab", u"Crop images non-destructively - original data is preserved", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasToolDraw.setText(QCoreApplication.translate("CanvasTab", u"Draw [D]", None))
#if QT_CONFIG(tooltip)
        self.CanvasToolDraw.setToolTip(QCoreApplication.translate("CanvasTab", u"Toggle drawing tools panel - freehand pen, shapes, lines", None))
#endif // QT_CONFIG(tooltip)
        self.sep3.setStyleSheet(QCoreApplication.translate("CanvasTab", u"color: #444;", None))
        self.CanvasViewMenu.setText(QCoreApplication.translate("CanvasTab", u"Arrange", None))
#if QT_CONFIG(tooltip)
        self.CanvasViewMenu.setToolTip(QCoreApplication.translate("CanvasTab", u"Alignment, distribution, auto-arrange, and z-order controls", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasToolbarToggle.setText(QCoreApplication.translate("CanvasTab", u"-", None))
#if QT_CONFIG(tooltip)
        self.CanvasToolbarToggle.setToolTip(QCoreApplication.translate("CanvasTab", u"Toggle secondary toolbar", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasToolbarToggle.setStyleSheet(QCoreApplication.translate("CanvasTab", u"padding: 0px;", None))
        self.CanvasToolbarContent.setStyleSheet(QCoreApplication.translate("CanvasTab", u"background-color: #262626;", None))
        self.labelGrid.setText(QCoreApplication.translate("CanvasTab", u"Grid:", None))
        self.labelGrid.setStyleSheet(QCoreApplication.translate("CanvasTab", u"color: #888; font-weight: bold;", None))
        self.CanvasToggleGrid.setText(QCoreApplication.translate("CanvasTab", u"Show", None))
#if QT_CONFIG(tooltip)
        self.CanvasToggleGrid.setToolTip(QCoreApplication.translate("CanvasTab", u"Toggle grid display (50px cells)", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasToggleSnap.setText(QCoreApplication.translate("CanvasTab", u"Snap", None))
#if QT_CONFIG(tooltip)
        self.CanvasToggleSnap.setToolTip(QCoreApplication.translate("CanvasTab", u"Enable snapping to grid and neighboring items", None))
#endif // QT_CONFIG(tooltip)
        self.sep5.setStyleSheet(QCoreApplication.translate("CanvasTab", u"color: #444;", None))
        self.labelZoom.setText(QCoreApplication.translate("CanvasTab", u"Zoom:", None))
        self.labelZoom.setStyleSheet(QCoreApplication.translate("CanvasTab", u"color: #888; font-weight: bold;", None))
#if QT_CONFIG(tooltip)
        self.CanvasZoomSlider.setToolTip(QCoreApplication.translate("CanvasTab", u"Zoom level (5% - 320%) - use mouse wheel or +/- keys", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasZoomPercent.setText(QCoreApplication.translate("CanvasTab", u"100%", None))
        self.CanvasZoomPercent.setStyleSheet(QCoreApplication.translate("CanvasTab", u"color: #aaa;", None))
        self.CanvasFitAll.setText(QCoreApplication.translate("CanvasTab", u"Fit All", None))
#if QT_CONFIG(tooltip)
        self.CanvasFitAll.setToolTip(QCoreApplication.translate("CanvasTab", u"Fit all items in view (Ctrl+Space)", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasFitSelection.setText(QCoreApplication.translate("CanvasTab", u"Fit Sel", None))
#if QT_CONFIG(tooltip)
        self.CanvasFitSelection.setToolTip(QCoreApplication.translate("CanvasTab", u"Fit selected items in view", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasResetZoom.setText(QCoreApplication.translate("CanvasTab", u"100%", None))
#if QT_CONFIG(tooltip)
        self.CanvasResetZoom.setToolTip(QCoreApplication.translate("CanvasTab", u"Reset zoom to 100% (Ctrl+0)", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasGoOrigin.setText(QCoreApplication.translate("CanvasTab", u"Origin", None))
#if QT_CONFIG(tooltip)
        self.CanvasGoOrigin.setToolTip(QCoreApplication.translate("CanvasTab", u"Center view on origin (0, 0) - press Home key", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasColorSampler.setText(QCoreApplication.translate("CanvasTab", u"Color [S]", None))
#if QT_CONFIG(tooltip)
        self.CanvasColorSampler.setToolTip(QCoreApplication.translate("CanvasTab", u"Color sampler - hold S and click on image to sample color. Last 5 colors saved.", None))
#endif // QT_CONFIG(tooltip)
        self.CanvasContainer.setStyleSheet(QCoreApplication.translate("CanvasTab", u"background-color: #1a1a1a;", None))
        self.CanvasMinimapContainer.setStyleSheet(QCoreApplication.translate("CanvasTab", u"background-color: #2d2d2d; border: 1px solid #444;", None))
        self.CanvasMinimapLabel.setText(QCoreApplication.translate("CanvasTab", u"Minimap", None))
        self.CanvasStatusBar.setStyleSheet(QCoreApplication.translate("CanvasTab", u"background-color: #252525; border-top: 1px solid #1a1a1a;", None))
        self.CanvasCoordinates.setText(QCoreApplication.translate("CanvasTab", u"X: 0  Y: 0", None))
        self.CanvasCoordinates.setStyleSheet(QCoreApplication.translate("CanvasTab", u"color: #888; font-family: monospace;", None))
        self.CanvasToolHint.setText(QCoreApplication.translate("CanvasTab", u"Select: Click items, Shift+click for multi-select, drag to move", None))
        self.CanvasToolHint.setStyleSheet(QCoreApplication.translate("CanvasTab", u"color: #666;", None))
        self.CanvasSelectionInfo.setText("")
        self.CanvasSelectionInfo.setStyleSheet(QCoreApplication.translate("CanvasTab", u"color: #888;", None))
        pass
    # retranslateUi

