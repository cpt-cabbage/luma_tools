# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'comfyui.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSlider,
    QSpacerItem, QSpinBox, QVBoxLayout, QWidget)

class Ui_ComfyUITab(object):
    def setupUi(self, ComfyUITab):
        if not ComfyUITab.objectName():
            ComfyUITab.setObjectName(u"ComfyUITab")
        ComfyUITab.resize(1400, 850)
        self.comfyuiOuterLayout = QVBoxLayout(ComfyUITab)
        self.comfyuiOuterLayout.setSpacing(4)
        self.comfyuiOuterLayout.setObjectName(u"comfyuiOuterLayout")
        self.comfyuiOuterLayout.setContentsMargins(6, 6, 6, 6)
        self.comfyuiScrollArea = QScrollArea(ComfyUITab)
        self.comfyuiScrollArea.setObjectName(u"comfyuiScrollArea")
        self.comfyuiScrollArea.setWidgetResizable(True)
        self.comfyuiScrollArea.setFrameShape(QFrame.NoFrame)
        self.comfyuiScrollContent = QWidget()
        self.comfyuiScrollContent.setObjectName(u"comfyuiScrollContent")
        self.comfyuiLayout = QVBoxLayout(self.comfyuiScrollContent)
        self.comfyuiLayout.setSpacing(4)
        self.comfyuiLayout.setObjectName(u"comfyuiLayout")
        self.comfyuiLayout.setContentsMargins(4, 4, 4, 4)
        self.comfyuiWorkflowGroupBox = QGroupBox(self.comfyuiScrollContent)
        self.comfyuiWorkflowGroupBox.setObjectName(u"comfyuiWorkflowGroupBox")
        self.comfyuiWorkflowLayout = QVBoxLayout(self.comfyuiWorkflowGroupBox)
        self.comfyuiWorkflowLayout.setSpacing(6)
        self.comfyuiWorkflowLayout.setObjectName(u"comfyuiWorkflowLayout")
        self.comfyuiPresetButtonsLayout = QHBoxLayout()
        self.comfyuiPresetButtonsLayout.setSpacing(6)
        self.comfyuiPresetButtonsLayout.setObjectName(u"comfyuiPresetButtonsLayout")
        self.ComfyUIChoosePreset = QPushButton(self.comfyuiWorkflowGroupBox)
        self.ComfyUIChoosePreset.setObjectName(u"ComfyUIChoosePreset")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.ComfyUIChoosePreset.sizePolicy().hasHeightForWidth())
        self.ComfyUIChoosePreset.setSizePolicy(sizePolicy)
        self.ComfyUIChoosePreset.setMinimumSize(QSize(0, 32))

        self.comfyuiPresetButtonsLayout.addWidget(self.ComfyUIChoosePreset)


        self.comfyuiWorkflowLayout.addLayout(self.comfyuiPresetButtonsLayout)

        self.ComfyUIWorkflowPath = QLabel(self.comfyuiWorkflowGroupBox)
        self.ComfyUIWorkflowPath.setObjectName(u"ComfyUIWorkflowPath")
        self.ComfyUIWorkflowPath.setWordWrap(True)
        self.ComfyUIWorkflowPath.setVisible(False)

        self.comfyuiWorkflowLayout.addWidget(self.ComfyUIWorkflowPath)


        self.comfyuiLayout.addWidget(self.comfyuiWorkflowGroupBox)

        self.comfyuiEditableNodesGroupBox = QGroupBox(self.comfyuiScrollContent)
        self.comfyuiEditableNodesGroupBox.setObjectName(u"comfyuiEditableNodesGroupBox")
        self.comfyuiEditableNodesGroupBox.setMinimumSize(QSize(0, 300))
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(4)
        sizePolicy1.setHeightForWidth(self.comfyuiEditableNodesGroupBox.sizePolicy().hasHeightForWidth())
        self.comfyuiEditableNodesGroupBox.setSizePolicy(sizePolicy1)
        self.comfyuiEditableNodesLayout = QVBoxLayout(self.comfyuiEditableNodesGroupBox)
        self.comfyuiEditableNodesLayout.setObjectName(u"comfyuiEditableNodesLayout")

        self.comfyuiLayout.addWidget(self.comfyuiEditableNodesGroupBox)

        self.settingsAndSubmitLayout = QHBoxLayout()
        self.settingsAndSubmitLayout.setSpacing(6)
        self.settingsAndSubmitLayout.setObjectName(u"settingsAndSubmitLayout")
        self.comfyuiSettingsGroupBox = QGroupBox(self.comfyuiScrollContent)
        self.comfyuiSettingsGroupBox.setObjectName(u"comfyuiSettingsGroupBox")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy2.setHorizontalStretch(1)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.comfyuiSettingsGroupBox.sizePolicy().hasHeightForWidth())
        self.comfyuiSettingsGroupBox.setSizePolicy(sizePolicy2)
        self.comfyuiSettingsLayout = QVBoxLayout(self.comfyuiSettingsGroupBox)
        self.comfyuiSettingsLayout.setSpacing(6)
        self.comfyuiSettingsLayout.setObjectName(u"comfyuiSettingsLayout")
        self.networkOutputDisplayLayout = QHBoxLayout()
        self.networkOutputDisplayLayout.setSpacing(6)
        self.networkOutputDisplayLayout.setObjectName(u"networkOutputDisplayLayout")
        self.label_network_output = QLabel(self.comfyuiSettingsGroupBox)
        self.label_network_output.setObjectName(u"label_network_output")
        self.label_network_output.setMinimumWidth(160)
        self.label_network_output.setMaximumWidth(160)

        self.networkOutputDisplayLayout.addWidget(self.label_network_output)

        self.ComfyUINetworkPathDisplay = QLabel(self.comfyuiSettingsGroupBox)
        self.ComfyUINetworkPathDisplay.setObjectName(u"ComfyUINetworkPathDisplay")
        sizePolicy2.setHeightForWidth(self.ComfyUINetworkPathDisplay.sizePolicy().hasHeightForWidth())
        self.ComfyUINetworkPathDisplay.setSizePolicy(sizePolicy2)

        self.networkOutputDisplayLayout.addWidget(self.ComfyUINetworkPathDisplay)


        self.comfyuiSettingsLayout.addLayout(self.networkOutputDisplayLayout)

        self.genCountLayout = QHBoxLayout()
        self.genCountLayout.setSpacing(6)
        self.genCountLayout.setObjectName(u"genCountLayout")
        self.label_count = QLabel(self.comfyuiSettingsGroupBox)
        self.label_count.setObjectName(u"label_count")
        self.label_count.setMinimumWidth(160)
        self.label_count.setMaximumWidth(160)

        self.genCountLayout.addWidget(self.label_count)

        self.ComfyUIGenerationCount = QSlider(self.comfyuiSettingsGroupBox)
        self.ComfyUIGenerationCount.setObjectName(u"ComfyUIGenerationCount")
        sizePolicy.setHeightForWidth(self.ComfyUIGenerationCount.sizePolicy().hasHeightForWidth())
        self.ComfyUIGenerationCount.setSizePolicy(sizePolicy)
        self.ComfyUIGenerationCount.setMinimum(1)
        self.ComfyUIGenerationCount.setMaximum(100)
        self.ComfyUIGenerationCount.setValue(1)
        self.ComfyUIGenerationCount.setOrientation(Qt.Horizontal)
        self.ComfyUIGenerationCount.setTickPosition(QSlider.TicksBelow)
        self.ComfyUIGenerationCount.setTickInterval(10)

        self.genCountLayout.addWidget(self.ComfyUIGenerationCount)

        self.label_count_value = QLabel(self.comfyuiSettingsGroupBox)
        self.label_count_value.setObjectName(u"label_count_value")
        self.label_count_value.setMinimumWidth(30)
        self.label_count_value.setAlignment(Qt.AlignRight|Qt.AlignVCenter)

        self.genCountLayout.addWidget(self.label_count_value)


        self.comfyuiSettingsLayout.addLayout(self.genCountLayout)

        self.seedLayout = QHBoxLayout()
        self.seedLayout.setSpacing(6)
        self.seedLayout.setObjectName(u"seedLayout")
        self.label_seed = QLabel(self.comfyuiSettingsGroupBox)
        self.label_seed.setObjectName(u"label_seed")
        self.label_seed.setMinimumWidth(160)
        self.label_seed.setMaximumWidth(160)

        self.seedLayout.addWidget(self.label_seed)

        self.ComfyUISeed = QSpinBox(self.comfyuiSettingsGroupBox)
        self.ComfyUISeed.setObjectName(u"ComfyUISeed")
        sizePolicy.setHeightForWidth(self.ComfyUISeed.sizePolicy().hasHeightForWidth())
        self.ComfyUISeed.setSizePolicy(sizePolicy)
        self.ComfyUISeed.setMinimum(0)
        self.ComfyUISeed.setMaximum(2147483647)

        self.seedLayout.addWidget(self.ComfyUISeed)

        self.ComfyUIRandomizeSeed = QPushButton(self.comfyuiSettingsGroupBox)
        self.ComfyUIRandomizeSeed.setObjectName(u"ComfyUIRandomizeSeed")
        self.ComfyUIRandomizeSeed.setMinimumSize(QSize(24, 24))
        self.ComfyUIRandomizeSeed.setMaximumSize(QSize(24, 24))
        self.ComfyUIRandomizeSeed.setIconSize(QSize(16, 16))

        self.seedLayout.addWidget(self.ComfyUIRandomizeSeed, 0, Qt.AlignVCenter)


        self.comfyuiSettingsLayout.addLayout(self.seedLayout)


        self.settingsAndSubmitLayout.addWidget(self.comfyuiSettingsGroupBox)

        self.comfyuiSubmitGroupBox = QGroupBox(self.comfyuiScrollContent)
        self.comfyuiSubmitGroupBox.setObjectName(u"comfyuiSubmitGroupBox")
        sizePolicy2.setHeightForWidth(self.comfyuiSubmitGroupBox.sizePolicy().hasHeightForWidth())
        self.comfyuiSubmitGroupBox.setSizePolicy(sizePolicy2)
        self.comfyuiSubmitLayout = QVBoxLayout(self.comfyuiSubmitGroupBox)
        self.comfyuiSubmitLayout.setSpacing(6)
        self.comfyuiSubmitLayout.setObjectName(u"comfyuiSubmitLayout")
        self.ComfyUIAutoAddToCanvas = QCheckBox(self.comfyuiSubmitGroupBox)
        self.ComfyUIAutoAddToCanvas.setObjectName(u"ComfyUIAutoAddToCanvas")
        self.ComfyUIAutoAddToCanvas.setChecked(False)

        self.comfyuiSubmitLayout.addWidget(self.ComfyUIAutoAddToCanvas)

        self.nameLayout = QHBoxLayout()
        self.nameLayout.setSpacing(6)
        self.nameLayout.setObjectName(u"nameLayout")
        self.label_name = QLabel(self.comfyuiSubmitGroupBox)
        self.label_name.setObjectName(u"label_name")

        self.nameLayout.addWidget(self.label_name)

        self.ComfyUIName = QLineEdit(self.comfyuiSubmitGroupBox)
        self.ComfyUIName.setObjectName(u"ComfyUIName")
        self.ComfyUIName.setMaxLength(60)

        self.nameLayout.addWidget(self.ComfyUIName)


        self.comfyuiSubmitLayout.addLayout(self.nameLayout)

        self.submitButtonsLayout = QHBoxLayout()
        self.submitButtonsLayout.setSpacing(8)
        self.submitButtonsLayout.setObjectName(u"submitButtonsLayout")
        self.ComfyUISubmit = QPushButton(self.comfyuiSubmitGroupBox)
        self.ComfyUISubmit.setObjectName(u"ComfyUISubmit")
        self.ComfyUISubmit.setMinimumSize(QSize(0, 40))

        self.submitButtonsLayout.addWidget(self.ComfyUISubmit)

        self.ComfyUICancelJobs = QPushButton(self.comfyuiSubmitGroupBox)
        self.ComfyUICancelJobs.setObjectName(u"ComfyUICancelJobs")
        self.ComfyUICancelJobs.setMinimumSize(QSize(100, 40))
        self.ComfyUICancelJobs.setVisible(False)

        self.submitButtonsLayout.addWidget(self.ComfyUICancelJobs)


        self.comfyuiSubmitLayout.addLayout(self.submitButtonsLayout)


        self.settingsAndSubmitLayout.addWidget(self.comfyuiSubmitGroupBox)


        self.comfyuiLayout.addLayout(self.settingsAndSubmitLayout)

        self.comfyuiIterateFrame = QFrame(self.comfyuiScrollContent)
        self.comfyuiIterateFrame.setObjectName(u"comfyuiIterateFrame")
        self.comfyuiIterateFrame.setFrameShape(QFrame.StyledPanel)
        self.comfyuiIterateFrame.setVisible(False)
        self.iterateLayout = QVBoxLayout(self.comfyuiIterateFrame)
        self.iterateLayout.setSpacing(6)
        self.iterateLayout.setObjectName(u"iterateLayout")
        self.ComfyUIIterateTitle = QLabel(self.comfyuiIterateFrame)
        self.ComfyUIIterateTitle.setObjectName(u"ComfyUIIterateTitle")

        self.iterateLayout.addWidget(self.ComfyUIIterateTitle)

        self.ComfyUIIterateStatus = QLabel(self.comfyuiIterateFrame)
        self.ComfyUIIterateStatus.setObjectName(u"ComfyUIIterateStatus")

        self.iterateLayout.addWidget(self.ComfyUIIterateStatus)

        self.ComfyUIIterateProgress = QProgressBar(self.comfyuiIterateFrame)
        self.ComfyUIIterateProgress.setObjectName(u"ComfyUIIterateProgress")
        self.ComfyUIIterateProgress.setMaximum(100)
        self.ComfyUIIterateProgress.setValue(0)
        self.ComfyUIIterateProgress.setTextVisible(False)

        self.iterateLayout.addWidget(self.ComfyUIIterateProgress)

        self.ComfyUIIteratePreview = QLabel(self.comfyuiIterateFrame)
        self.ComfyUIIteratePreview.setObjectName(u"ComfyUIIteratePreview")
        self.ComfyUIIteratePreview.setMinimumSize(QSize(200, 200))
        self.ComfyUIIteratePreview.setAlignment(Qt.AlignCenter)

        self.iterateLayout.addWidget(self.ComfyUIIteratePreview)

        self.ComfyUIUseAsInput = QPushButton(self.comfyuiIterateFrame)
        self.ComfyUIUseAsInput.setObjectName(u"ComfyUIUseAsInput")
        self.ComfyUIUseAsInput.setEnabled(False)

        self.iterateLayout.addWidget(self.ComfyUIUseAsInput)


        self.comfyuiLayout.addWidget(self.comfyuiIterateFrame)

        self.verticalSpacer_comfy = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.comfyuiLayout.addItem(self.verticalSpacer_comfy)

        self.comfyuiScrollArea.setWidget(self.comfyuiScrollContent)

        self.comfyuiOuterLayout.addWidget(self.comfyuiScrollArea)


        self.retranslateUi(ComfyUITab)

        QMetaObject.connectSlotsByName(ComfyUITab)
    # setupUi

    def retranslateUi(self, ComfyUITab):
        self.comfyuiWorkflowGroupBox.setTitle(QCoreApplication.translate("ComfyUITab", u"Model", None))
        self.ComfyUIChoosePreset.setText(QCoreApplication.translate("ComfyUITab", u"Choose Model", None))
#if QT_CONFIG(tooltip)
        self.ComfyUIChoosePreset.setToolTip(QCoreApplication.translate("ComfyUITab", u"Click to browse and select a workflow model", None))
#endif // QT_CONFIG(tooltip)
        self.ComfyUIWorkflowPath.setText(QCoreApplication.translate("ComfyUITab", u"No model selected", None))
        self.ComfyUIWorkflowPath.setStyleSheet(QCoreApplication.translate("ComfyUITab", u"color: #888888; font-style: italic;", None))
        self.comfyuiEditableNodesGroupBox.setTitle(QCoreApplication.translate("ComfyUITab", u"Input", None))
        self.comfyuiSettingsGroupBox.setTitle(QCoreApplication.translate("ComfyUITab", u"Generation Settings", None))
        self.label_network_output.setText(QCoreApplication.translate("ComfyUITab", u"Output:", None))
        self.ComfyUINetworkPathDisplay.setText(QCoreApplication.translate("ComfyUITab", u"(Not configured - set in Settings tab)", None))
        self.ComfyUINetworkPathDisplay.setStyleSheet(QCoreApplication.translate("ComfyUITab", u"color: #888888; font-style: italic;", None))
#if QT_CONFIG(tooltip)
        self.ComfyUINetworkPathDisplay.setToolTip(QCoreApplication.translate("ComfyUITab", u"Network path where ComfyUI writes outputs (configured in Settings tab)", None))
#endif // QT_CONFIG(tooltip)
        self.label_count.setText(QCoreApplication.translate("ComfyUITab", u"Successive Generations:", None))
        self.label_count_value.setText(QCoreApplication.translate("ComfyUITab", u"1", None))
        self.label_seed.setText(QCoreApplication.translate("ComfyUITab", u"Seed:", None))
#if QT_CONFIG(tooltip)
        self.ComfyUISeed.setToolTip(QCoreApplication.translate("ComfyUITab", u"Random seed for generation", None))
#endif // QT_CONFIG(tooltip)
        self.ComfyUIRandomizeSeed.setText("")
#if QT_CONFIG(tooltip)
        self.ComfyUIRandomizeSeed.setToolTip(QCoreApplication.translate("ComfyUITab", u"Generate a new random seed", None))
#endif // QT_CONFIG(tooltip)
        self.comfyuiSubmitGroupBox.setTitle(QCoreApplication.translate("ComfyUITab", u"Submit", None))
        self.ComfyUIAutoAddToCanvas.setText(QCoreApplication.translate("ComfyUITab", u"Auto-add to Canvas", None))
#if QT_CONFIG(tooltip)
        self.ComfyUIAutoAddToCanvas.setToolTip(QCoreApplication.translate("ComfyUITab", u"Automatically add generated images to the Canvas tab", None))
#endif // QT_CONFIG(tooltip)
        self.label_name.setText(QCoreApplication.translate("ComfyUITab", u"Name:", None))
        self.ComfyUIName.setPlaceholderText(QCoreApplication.translate("ComfyUITab", u"Optional - prefixes output filenames", None))
#if QT_CONFIG(tooltip)
        self.ComfyUIName.setToolTip(QCoreApplication.translate("ComfyUITab", u"Optional label prepended to output filenames for easier identification", None))
#endif // QT_CONFIG(tooltip)
        self.ComfyUISubmit.setText(QCoreApplication.translate("ComfyUITab", u"Submit to Farm", None))
        self.ComfyUICancelJobs.setText(QCoreApplication.translate("ComfyUITab", u"Cancel Jobs", None))
#if QT_CONFIG(tooltip)
        self.ComfyUICancelJobs.setToolTip(QCoreApplication.translate("ComfyUITab", u"Cancel all running ComfyUI jobs", None))
#endif // QT_CONFIG(tooltip)
        self.ComfyUIIterateTitle.setText(QCoreApplication.translate("ComfyUITab", u"Iterate Mode", None))
        self.ComfyUIIterateTitle.setStyleSheet(QCoreApplication.translate("ComfyUITab", u"font-weight: bold; font-size: 12px;", None))
        self.ComfyUIIterateStatus.setText(QCoreApplication.translate("ComfyUITab", u"Ready", None))
        self.ComfyUIIterateStatus.setStyleSheet(QCoreApplication.translate("ComfyUITab", u"color: #888888;", None))
        self.ComfyUIIteratePreview.setText("")
        self.ComfyUIIteratePreview.setStyleSheet(QCoreApplication.translate("ComfyUITab", u"background-color: #2c313a; border: 1px solid #3c414b; border-radius: 4px;", None))
        self.ComfyUIUseAsInput.setText(QCoreApplication.translate("ComfyUITab", u"Use as Input", None))
#if QT_CONFIG(tooltip)
        self.ComfyUIUseAsInput.setToolTip(QCoreApplication.translate("ComfyUITab", u"Copy the generated image path to the input image field for the next iteration", None))
#endif // QT_CONFIG(tooltip)
        pass
    # retranslateUi

