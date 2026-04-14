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
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSlider,
    QSpacerItem, QSpinBox, QVBoxLayout, QWidget)

class Ui_ComfyUITab(object):
    def setupUi(self, ComfyUITab):
        if not ComfyUITab.objectName():
            ComfyUITab.setObjectName(u"ComfyUITab")
        ComfyUITab.resize(1400, 850)
        self.comfyuiOuterLayout = QVBoxLayout(ComfyUITab)
        self.comfyuiOuterLayout.setSpacing(0)
        self.comfyuiOuterLayout.setObjectName(u"comfyuiOuterLayout")
        self.comfyuiOuterLayout.setContentsMargins(0, 0, 0, 0)
        self.comfyuiScrollArea = QScrollArea(ComfyUITab)
        self.comfyuiScrollArea.setObjectName(u"comfyuiScrollArea")
        self.comfyuiScrollArea.setWidgetResizable(True)
        self.comfyuiScrollArea.setFrameShape(QFrame.NoFrame)
        self.comfyuiScrollContent = QWidget()
        self.comfyuiScrollContent.setObjectName(u"comfyuiScrollContent")
        self.comfyuiLayout = QVBoxLayout(self.comfyuiScrollContent)
        self.comfyuiLayout.setSpacing(12)
        self.comfyuiLayout.setObjectName(u"comfyuiLayout")
        self.comfyuiLayout.setContentsMargins(16, 12, 16, 12)
        self.comfyuiModelFrame = QFrame(self.comfyuiScrollContent)
        self.comfyuiModelFrame.setObjectName(u"comfyuiModelFrame")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.comfyuiModelFrame.sizePolicy().hasHeightForWidth())
        self.comfyuiModelFrame.setSizePolicy(sizePolicy)
        self.comfyuiModelFrame.setStyleSheet(u"\n"
"            QFrame#comfyuiModelFrame {\n"
"              background-color: #282c34;\n"
"              border: 1px solid #3c414b;\n"
"              border-radius: 8px;\n"
"            }\n"
"          ")
        self.comfyuiWorkflowLayout = QVBoxLayout(self.comfyuiModelFrame)
        self.comfyuiWorkflowLayout.setSpacing(8)
        self.comfyuiWorkflowLayout.setObjectName(u"comfyuiWorkflowLayout")
        self.comfyuiWorkflowLayout.setContentsMargins(16, 12, 16, 14)
        self.modelHeaderLayout = QHBoxLayout()
        self.modelHeaderLayout.setSpacing(10)
        self.modelHeaderLayout.setObjectName(u"modelHeaderLayout")
        self.modelStepTitle = QLabel(self.comfyuiModelFrame)
        self.modelStepTitle.setObjectName(u"modelStepTitle")
        self.modelStepTitle.setStyleSheet(u"color: #e0e0e0; font-size: 13px; font-weight: bold;")

        self.modelHeaderLayout.addWidget(self.modelStepTitle)

        self.spacerItem = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.modelHeaderLayout.addItem(self.spacerItem)


        self.comfyuiWorkflowLayout.addLayout(self.modelHeaderLayout)

        self.comfyuiPresetButtonsLayout = QHBoxLayout()
        self.comfyuiPresetButtonsLayout.setSpacing(6)
        self.comfyuiPresetButtonsLayout.setObjectName(u"comfyuiPresetButtonsLayout")
        self.ComfyUIChoosePreset = QPushButton(self.comfyuiModelFrame)
        self.ComfyUIChoosePreset.setObjectName(u"ComfyUIChoosePreset")
        self.ComfyUIChoosePreset.setVisible(False)
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(1)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.ComfyUIChoosePreset.sizePolicy().hasHeightForWidth())
        self.ComfyUIChoosePreset.setSizePolicy(sizePolicy1)
        self.ComfyUIChoosePreset.setMinimumSize(QSize(0, 38))
        self.ComfyUIChoosePreset.setStyleSheet(u"\n"
"                 QPushButton {\n"
"                   background-color: #2c313a;\n"
"                   border: 1px dashed #4a9eff;\n"
"                   border-radius: 6px;\n"
"                   color: #4a9eff;\n"
"                   font-size: 13px;\n"
"                   font-weight: 500;\n"
"                   padding: 6px 16px;\n"
"                   text-align: left;\n"
"                 }\n"
"                 QPushButton:hover {\n"
"                   background-color: #333842;\n"
"                   border-style: solid;\n"
"                 }\n"
"               ")

        self.comfyuiPresetButtonsLayout.addWidget(self.ComfyUIChoosePreset)


        self.comfyuiWorkflowLayout.addLayout(self.comfyuiPresetButtonsLayout)

        self.modelGridContainer = QWidget(self.comfyuiModelFrame)
        self.modelGridContainer.setObjectName(u"modelGridContainer")
        sizePolicy.setHeightForWidth(self.modelGridContainer.sizePolicy().hasHeightForWidth())
        self.modelGridContainer.setSizePolicy(sizePolicy)
        self.modelGridContainerLayout = QVBoxLayout(self.modelGridContainer)
        self.modelGridContainerLayout.setSpacing(0)
        self.modelGridContainerLayout.setObjectName(u"modelGridContainerLayout")
        self.modelGridContainerLayout.setContentsMargins(0, 0, 0, 0)

        self.comfyuiWorkflowLayout.addWidget(self.modelGridContainer)

        self.selectedModelHeader = QWidget(self.comfyuiModelFrame)
        self.selectedModelHeader.setObjectName(u"selectedModelHeader")
        self.selectedModelHeader.setVisible(False)
        self.selectedModelHeaderLayout = QVBoxLayout(self.selectedModelHeader)
        self.selectedModelHeaderLayout.setSpacing(4)
        self.selectedModelHeaderLayout.setObjectName(u"selectedModelHeaderLayout")
        self.selectedModelHeaderLayout.setContentsMargins(0, 0, 0, 0)
        self.selectedModelTitleRow = QHBoxLayout()
        self.selectedModelTitleRow.setSpacing(8)
        self.selectedModelTitleRow.setObjectName(u"selectedModelTitleRow")
        self.selectedModelName = QLabel(self.selectedModelHeader)
        self.selectedModelName.setObjectName(u"selectedModelName")
        self.selectedModelName.setStyleSheet(u"color: #e0e0e0; font-size: 14px; font-weight: bold;")

        self.selectedModelTitleRow.addWidget(self.selectedModelName)

        self.selectedModelBadge = QLabel(self.selectedModelHeader)
        self.selectedModelBadge.setObjectName(u"selectedModelBadge")
        self.selectedModelBadge.setStyleSheet(u"background-color: rgba(74, 158, 255, 0.15); color: #4a9eff; border-radius: 3px; padding: 2px 8px; font-size: 10px; font-weight: bold;")

        self.selectedModelTitleRow.addWidget(self.selectedModelBadge)

        self.spacerItem1 = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.selectedModelTitleRow.addItem(self.spacerItem1)

        self.workflowSettingsBtn = QPushButton(self.selectedModelHeader)
        self.workflowSettingsBtn.setObjectName(u"workflowSettingsBtn")
        self.workflowSettingsBtn.setVisible(False)
        self.workflowSettingsBtn.setMinimumSize(QSize(28, 28))
        self.workflowSettingsBtn.setMaximumSize(QSize(28, 28))
        self.workflowSettingsBtn.setIconSize(QSize(16, 16))
        self.workflowSettingsBtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.workflowSettingsBtn.setStyleSheet(u"QPushButton { background-color: transparent; border: 1px solid #3c414b; border-radius: 4px; color: #c5cad3; } QPushButton:hover { border-color: #4a9eff; color: #4a9eff; }")

        self.selectedModelTitleRow.addWidget(self.workflowSettingsBtn)

        self.editModelBtn = QPushButton(self.selectedModelHeader)
        self.editModelBtn.setObjectName(u"editModelBtn")
        self.editModelBtn.setVisible(False)
        self.editModelBtn.setMinimumSize(QSize(0, 28))
        self.editModelBtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.editModelBtn.setStyleSheet(u"QPushButton { background-color: transparent; border: 1px solid #3c414b; border-radius: 4px; color: #c5cad3; padding: 0 10px; font-size: 11px; } QPushButton:hover { border-color: #4a9eff; color: #4a9eff; }")

        self.selectedModelTitleRow.addWidget(self.editModelBtn)

        self.changeModelBtn = QPushButton(self.selectedModelHeader)
        self.changeModelBtn.setObjectName(u"changeModelBtn")
        self.changeModelBtn.setMinimumSize(QSize(0, 28))
        self.changeModelBtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.changeModelBtn.setStyleSheet(u"QPushButton { background-color: #2c313a; border: 1px solid #4a9eff; border-radius: 4px; color: #4a9eff; padding: 0 12px; font-size: 11px; font-weight: 500; } QPushButton:hover { background-color: #333842; }")

        self.selectedModelTitleRow.addWidget(self.changeModelBtn)


        self.selectedModelHeaderLayout.addLayout(self.selectedModelTitleRow)

        self.selectedModelDesc = QLabel(self.selectedModelHeader)
        self.selectedModelDesc.setObjectName(u"selectedModelDesc")
        self.selectedModelDesc.setWordWrap(True)
        self.selectedModelDesc.setStyleSheet(u"color: #797e89; font-size: 11px;")

        self.selectedModelHeaderLayout.addWidget(self.selectedModelDesc)


        self.comfyuiWorkflowLayout.addWidget(self.selectedModelHeader)

        self.modelInfoContainer = QWidget(self.comfyuiModelFrame)
        self.modelInfoContainer.setObjectName(u"modelInfoContainer")
        self.modelInfoContainer.setVisible(False)
        self.modelInfoLayout = QVBoxLayout(self.modelInfoContainer)
        self.modelInfoLayout.setSpacing(6)
        self.modelInfoLayout.setObjectName(u"modelInfoLayout")
        self.modelInfoLayout.setContentsMargins(0, 0, 0, 0)

        self.comfyuiWorkflowLayout.addWidget(self.modelInfoContainer)

        self.ComfyUIWorkflowPath = QLabel(self.comfyuiModelFrame)
        self.ComfyUIWorkflowPath.setObjectName(u"ComfyUIWorkflowPath")
        self.ComfyUIWorkflowPath.setVisible(False)

        self.comfyuiWorkflowLayout.addWidget(self.ComfyUIWorkflowPath)


        self.comfyuiLayout.addWidget(self.comfyuiModelFrame)

        self.comfyuiInputFrame = QFrame(self.comfyuiScrollContent)
        self.comfyuiInputFrame.setObjectName(u"comfyuiInputFrame")
        self.comfyuiInputFrame.setStyleSheet(u"\n"
"            QFrame#comfyuiInputFrame {\n"
"              background-color: #282c34;\n"
"              border: 1px solid #3c414b;\n"
"              border-radius: 8px;\n"
"            }\n"
"          ")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(3)
        sizePolicy2.setHeightForWidth(self.comfyuiInputFrame.sizePolicy().hasHeightForWidth())
        self.comfyuiInputFrame.setSizePolicy(sizePolicy2)
        self.comfyuiInputFrame.setMinimumSize(QSize(0, 180))
        self.inputOuterLayout = QVBoxLayout(self.comfyuiInputFrame)
        self.inputOuterLayout.setSpacing(8)
        self.inputOuterLayout.setObjectName(u"inputOuterLayout")
        self.inputOuterLayout.setContentsMargins(16, 12, 16, 14)
        self.inputHeaderLayout = QHBoxLayout()
        self.inputHeaderLayout.setSpacing(10)
        self.inputHeaderLayout.setObjectName(u"inputHeaderLayout")
        self.inputStepTitle = QLabel(self.comfyuiInputFrame)
        self.inputStepTitle.setObjectName(u"inputStepTitle")
        self.inputStepTitle.setStyleSheet(u"color: #e0e0e0; font-size: 13px; font-weight: bold;")

        self.inputHeaderLayout.addWidget(self.inputStepTitle)

        self.spacerItem2 = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.inputHeaderLayout.addItem(self.spacerItem2)


        self.inputOuterLayout.addLayout(self.inputHeaderLayout)

        self.variantSelectorContainer = QWidget(self.comfyuiInputFrame)
        self.variantSelectorContainer.setObjectName(u"variantSelectorContainer")
        self.variantSelectorContainer.setVisible(False)
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.variantSelectorContainer.sizePolicy().hasHeightForWidth())
        self.variantSelectorContainer.setSizePolicy(sizePolicy3)
        self.variantSelectorLayout = QVBoxLayout(self.variantSelectorContainer)
        self.variantSelectorLayout.setSpacing(0)
        self.variantSelectorLayout.setObjectName(u"variantSelectorLayout")
        self.variantSelectorLayout.setContentsMargins(0, 0, 0, 0)

        self.inputOuterLayout.addWidget(self.variantSelectorContainer)

        self.noteBanner = QFrame(self.comfyuiInputFrame)
        self.noteBanner.setObjectName(u"noteBanner")
        self.noteBanner.setVisible(False)
        self.noteBanner.setFrameShape(QFrame.StyledPanel)
        self.noteBanner.setStyleSheet(u"\n"
"               QFrame#noteBanner {\n"
"                 background-color: rgba(74, 158, 255, 0.10);\n"
"                 border: 1px solid rgba(74, 158, 255, 0.35);\n"
"                 border-radius: 6px;\n"
"               }\n"
"             ")
        self.noteBannerLayout = QHBoxLayout(self.noteBanner)
        self.noteBannerLayout.setSpacing(8)
        self.noteBannerLayout.setObjectName(u"noteBannerLayout")
        self.noteBannerLayout.setContentsMargins(10, 6, 10, 6)
        self.noteText = QLabel(self.noteBanner)
        self.noteText.setObjectName(u"noteText")
        self.noteText.setWordWrap(True)
        self.noteText.setStyleSheet(u"color: #c5cad3; font-size: 11px;")

        self.noteBannerLayout.addWidget(self.noteText)


        self.inputOuterLayout.addWidget(self.noteBanner)

        self.comfyuiEditableNodesLayout = QVBoxLayout()
        self.comfyuiEditableNodesLayout.setSpacing(6)
        self.comfyuiEditableNodesLayout.setObjectName(u"comfyuiEditableNodesLayout")

        self.inputOuterLayout.addLayout(self.comfyuiEditableNodesLayout)


        self.comfyuiLayout.addWidget(self.comfyuiInputFrame)

        self.submitBar = QWidget(self.comfyuiScrollContent)
        self.submitBar.setObjectName(u"submitBar")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.submitBar.sizePolicy().hasHeightForWidth())
        self.submitBar.setSizePolicy(sizePolicy4)
        self.settingsAndSubmitLayout = QHBoxLayout(self.submitBar)
        self.settingsAndSubmitLayout.setSpacing(12)
        self.settingsAndSubmitLayout.setObjectName(u"settingsAndSubmitLayout")
        self.settingsAndSubmitLayout.setContentsMargins(0, 0, 0, 0)
        self.comfyuiSettingsFrame = QFrame(self.submitBar)
        self.comfyuiSettingsFrame.setObjectName(u"comfyuiSettingsFrame")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy5.setHorizontalStretch(1)
        sizePolicy5.setVerticalStretch(0)
        sizePolicy5.setHeightForWidth(self.comfyuiSettingsFrame.sizePolicy().hasHeightForWidth())
        self.comfyuiSettingsFrame.setSizePolicy(sizePolicy5)
        self.comfyuiSettingsFrame.setStyleSheet(u"\n"
"              QFrame#comfyuiSettingsFrame {\n"
"                background-color: #282c34;\n"
"                border: 1px solid #3c414b;\n"
"                border-radius: 8px;\n"
"              }\n"
"            ")
        self.comfyuiSettingsLayout = QVBoxLayout(self.comfyuiSettingsFrame)
        self.comfyuiSettingsLayout.setSpacing(8)
        self.comfyuiSettingsLayout.setObjectName(u"comfyuiSettingsLayout")
        self.comfyuiSettingsLayout.setContentsMargins(16, 12, 16, 14)
        self.settingsHeaderLayout = QHBoxLayout()
        self.settingsHeaderLayout.setSpacing(10)
        self.settingsHeaderLayout.setObjectName(u"settingsHeaderLayout")
        self.settingsStepTitle = QLabel(self.comfyuiSettingsFrame)
        self.settingsStepTitle.setObjectName(u"settingsStepTitle")
        self.settingsStepTitle.setStyleSheet(u"color: #e0e0e0; font-size: 13px; font-weight: bold;")

        self.settingsHeaderLayout.addWidget(self.settingsStepTitle)

        self.spacerItem3 = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.settingsHeaderLayout.addItem(self.spacerItem3)

        self.advancedGearBtn = QPushButton(self.comfyuiSettingsFrame)
        self.advancedGearBtn.setObjectName(u"advancedGearBtn")
        self.advancedGearBtn.setMinimumSize(QSize(26, 26))
        self.advancedGearBtn.setMaximumSize(QSize(26, 26))
        self.advancedGearBtn.setIconSize(QSize(16, 16))
        self.advancedGearBtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.advancedGearBtn.setStyleSheet(u"QPushButton { background-color: transparent; border: 1px solid #3c414b; border-radius: 4px; color: #c5cad3; } QPushButton:hover { border-color: #4a9eff; color: #4a9eff; }")

        self.settingsHeaderLayout.addWidget(self.advancedGearBtn)


        self.comfyuiSettingsLayout.addLayout(self.settingsHeaderLayout)

        self.genCountLayout = QHBoxLayout()
        self.genCountLayout.setSpacing(8)
        self.genCountLayout.setObjectName(u"genCountLayout")
        self.label_count = QLabel(self.comfyuiSettingsFrame)
        self.label_count.setObjectName(u"label_count")
        self.label_count.setMinimumWidth(80)

        self.genCountLayout.addWidget(self.label_count)

        self.ComfyUIGenerationCount = QSlider(self.comfyuiSettingsFrame)
        self.ComfyUIGenerationCount.setObjectName(u"ComfyUIGenerationCount")
        sizePolicy1.setHeightForWidth(self.ComfyUIGenerationCount.sizePolicy().hasHeightForWidth())
        self.ComfyUIGenerationCount.setSizePolicy(sizePolicy1)
        self.ComfyUIGenerationCount.setMinimum(1)
        self.ComfyUIGenerationCount.setMaximum(100)
        self.ComfyUIGenerationCount.setValue(1)
        self.ComfyUIGenerationCount.setOrientation(Qt.Horizontal)
        self.ComfyUIGenerationCount.setTickPosition(QSlider.TicksBelow)
        self.ComfyUIGenerationCount.setTickInterval(10)

        self.genCountLayout.addWidget(self.ComfyUIGenerationCount)

        self.label_count_value = QLabel(self.comfyuiSettingsFrame)
        self.label_count_value.setObjectName(u"label_count_value")
        self.label_count_value.setMinimumWidth(30)
        self.label_count_value.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        self.label_count_value.setStyleSheet(u"color: #4a9eff; font-weight: bold; font-size: 13px;")

        self.genCountLayout.addWidget(self.label_count_value)


        self.comfyuiSettingsLayout.addLayout(self.genCountLayout)

        self.advancedToggleBtn = QPushButton(self.comfyuiSettingsFrame)
        self.advancedToggleBtn.setObjectName(u"advancedToggleBtn")
        self.advancedToggleBtn.setVisible(False)
        self.advancedToggleBtn.setStyleSheet(u"\n"
"                 QPushButton {\n"
"                   background-color: transparent;\n"
"                   border: none;\n"
"                   color: #797e89;\n"
"                   font-size: 11px;\n"
"                   text-align: left;\n"
"                   padding: 2px 0px;\n"
"                 }\n"
"                 QPushButton:hover {\n"
"                   color: #4a9eff;\n"
"                 }\n"
"               ")
        self.advancedToggleBtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.comfyuiSettingsLayout.addWidget(self.advancedToggleBtn)

        self.advancedSettingsContainer = QWidget(self.comfyuiSettingsFrame)
        self.advancedSettingsContainer.setObjectName(u"advancedSettingsContainer")
        self.advancedSettingsContainer.setVisible(False)
        self.advancedSettingsLayout = QVBoxLayout(self.advancedSettingsContainer)
        self.advancedSettingsLayout.setSpacing(6)
        self.advancedSettingsLayout.setObjectName(u"advancedSettingsLayout")
        self.advancedSettingsLayout.setContentsMargins(0, 4, 0, 0)
        self.advancedSeparator = QFrame(self.advancedSettingsContainer)
        self.advancedSeparator.setObjectName(u"advancedSeparator")
        self.advancedSeparator.setFrameShape(QFrame.HLine)
        self.advancedSeparator.setStyleSheet(u"color: #3c414b;")

        self.advancedSettingsLayout.addWidget(self.advancedSeparator)

        self.seedLayout = QHBoxLayout()
        self.seedLayout.setSpacing(8)
        self.seedLayout.setObjectName(u"seedLayout")
        self.label_seed = QLabel(self.advancedSettingsContainer)
        self.label_seed.setObjectName(u"label_seed")
        self.label_seed.setMinimumWidth(80)

        self.seedLayout.addWidget(self.label_seed)

        self.ComfyUISeed = QSpinBox(self.advancedSettingsContainer)
        self.ComfyUISeed.setObjectName(u"ComfyUISeed")
        sizePolicy1.setHeightForWidth(self.ComfyUISeed.sizePolicy().hasHeightForWidth())
        self.ComfyUISeed.setSizePolicy(sizePolicy1)
        self.ComfyUISeed.setMinimum(0)
        self.ComfyUISeed.setMaximum(2147483647)

        self.seedLayout.addWidget(self.ComfyUISeed)

        self.ComfyUIRandomizeSeed = QPushButton(self.advancedSettingsContainer)
        self.ComfyUIRandomizeSeed.setObjectName(u"ComfyUIRandomizeSeed")
        self.ComfyUIRandomizeSeed.setMinimumSize(QSize(24, 24))
        self.ComfyUIRandomizeSeed.setMaximumSize(QSize(24, 24))
        self.ComfyUIRandomizeSeed.setIconSize(QSize(16, 16))

        self.seedLayout.addWidget(self.ComfyUIRandomizeSeed, 0, Qt.AlignVCenter)


        self.advancedSettingsLayout.addLayout(self.seedLayout)

        self.nameLayout = QHBoxLayout()
        self.nameLayout.setSpacing(8)
        self.nameLayout.setObjectName(u"nameLayout")
        self.ComfyUINameToggle = QCheckBox(self.advancedSettingsContainer)
        self.ComfyUINameToggle.setObjectName(u"ComfyUINameToggle")
        self.ComfyUINameToggle.setChecked(False)

        self.nameLayout.addWidget(self.ComfyUINameToggle)

        self.ComfyUIName = QLineEdit(self.advancedSettingsContainer)
        self.ComfyUIName.setObjectName(u"ComfyUIName")
        self.ComfyUIName.setMaxLength(60)
        self.ComfyUIName.setVisible(False)

        self.nameLayout.addWidget(self.ComfyUIName)


        self.advancedSettingsLayout.addLayout(self.nameLayout)

        self.serverBehaviorLayout = QHBoxLayout()
        self.serverBehaviorLayout.setSpacing(6)
        self.serverBehaviorLayout.setObjectName(u"serverBehaviorLayout")
        self.serverBehaviorLabel = QLabel(self.advancedSettingsContainer)
        self.serverBehaviorLabel.setObjectName(u"serverBehaviorLabel")

        self.serverBehaviorLayout.addWidget(self.serverBehaviorLabel)

        self.ServerBehaviorCombo = QComboBox(self.advancedSettingsContainer)
        self.ServerBehaviorCombo.setObjectName(u"ServerBehaviorCombo")
        self.ServerBehaviorCombo.setMinimumWidth(140)

        self.serverBehaviorLayout.addWidget(self.ServerBehaviorCombo)

        self.serverWaitTimeoutLabel = QLabel(self.advancedSettingsContainer)
        self.serverWaitTimeoutLabel.setObjectName(u"serverWaitTimeoutLabel")

        self.serverBehaviorLayout.addWidget(self.serverWaitTimeoutLabel)

        self.ServerWaitTimeoutSpinBox = QSpinBox(self.advancedSettingsContainer)
        self.ServerWaitTimeoutSpinBox.setObjectName(u"ServerWaitTimeoutSpinBox")
        self.ServerWaitTimeoutSpinBox.setMinimum(1)
        self.ServerWaitTimeoutSpinBox.setMaximum(60)
        self.ServerWaitTimeoutSpinBox.setValue(5)

        self.serverBehaviorLayout.addWidget(self.ServerWaitTimeoutSpinBox)

        self.spacerItem4 = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.serverBehaviorLayout.addItem(self.spacerItem4)


        self.advancedSettingsLayout.addLayout(self.serverBehaviorLayout)

        self.networkOutputDisplayLayout = QHBoxLayout()
        self.networkOutputDisplayLayout.setObjectName(u"networkOutputDisplayLayout")
        self.label_network_output = QLabel(self.advancedSettingsContainer)
        self.label_network_output.setObjectName(u"label_network_output")
        self.label_network_output.setMinimumWidth(80)

        self.networkOutputDisplayLayout.addWidget(self.label_network_output)

        self.ComfyUINetworkPathDisplay = QLabel(self.advancedSettingsContainer)
        self.ComfyUINetworkPathDisplay.setObjectName(u"ComfyUINetworkPathDisplay")
        sizePolicy5.setHeightForWidth(self.ComfyUINetworkPathDisplay.sizePolicy().hasHeightForWidth())
        self.ComfyUINetworkPathDisplay.setSizePolicy(sizePolicy5)
        self.ComfyUINetworkPathDisplay.setStyleSheet(u"color: #797e89; font-style: italic; font-size: 11px;")

        self.networkOutputDisplayLayout.addWidget(self.ComfyUINetworkPathDisplay)


        self.advancedSettingsLayout.addLayout(self.networkOutputDisplayLayout)


        self.comfyuiSettingsLayout.addWidget(self.advancedSettingsContainer)


        self.settingsAndSubmitLayout.addWidget(self.comfyuiSettingsFrame)

        self.comfyuiSubmitFrame = QFrame(self.submitBar)
        self.comfyuiSubmitFrame.setObjectName(u"comfyuiSubmitFrame")
        sizePolicy5.setHeightForWidth(self.comfyuiSubmitFrame.sizePolicy().hasHeightForWidth())
        self.comfyuiSubmitFrame.setSizePolicy(sizePolicy5)
        self.comfyuiSubmitFrame.setStyleSheet(u"\n"
"              QFrame#comfyuiSubmitFrame {\n"
"                background-color: #282c34;\n"
"                border: 1px solid #3c414b;\n"
"                border-radius: 8px;\n"
"              }\n"
"            ")
        self.comfyuiSubmitLayout = QVBoxLayout(self.comfyuiSubmitFrame)
        self.comfyuiSubmitLayout.setSpacing(10)
        self.comfyuiSubmitLayout.setObjectName(u"comfyuiSubmitLayout")
        self.comfyuiSubmitLayout.setContentsMargins(16, 12, 16, 14)
        self.submitHeaderLayout = QHBoxLayout()
        self.submitHeaderLayout.setSpacing(10)
        self.submitHeaderLayout.setObjectName(u"submitHeaderLayout")
        self.submitStepTitle = QLabel(self.comfyuiSubmitFrame)
        self.submitStepTitle.setObjectName(u"submitStepTitle")
        self.submitStepTitle.setStyleSheet(u"color: #e0e0e0; font-size: 13px; font-weight: bold;")

        self.submitHeaderLayout.addWidget(self.submitStepTitle)

        self.spacerItem5 = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.submitHeaderLayout.addItem(self.spacerItem5)


        self.comfyuiSubmitLayout.addLayout(self.submitHeaderLayout)

        self.serverStatusBanner = QFrame(self.comfyuiSubmitFrame)
        self.serverStatusBanner.setObjectName(u"serverStatusBanner")
        self.serverStatusBanner.setVisible(False)
        self.serverStatusBanner.setMinimumHeight(32)
        self.serverStatusLayout = QHBoxLayout(self.serverStatusBanner)
        self.serverStatusLayout.setObjectName(u"serverStatusLayout")
        self.serverStatusLayout.setContentsMargins(10, 6, 10, 6)

        self.comfyuiSubmitLayout.addWidget(self.serverStatusBanner)

        self.submitButtonsLayout = QHBoxLayout()
        self.submitButtonsLayout.setSpacing(8)
        self.submitButtonsLayout.setObjectName(u"submitButtonsLayout")
        self.ComfyUISubmit = QPushButton(self.comfyuiSubmitFrame)
        self.ComfyUISubmit.setObjectName(u"ComfyUISubmit")
        self.ComfyUISubmit.setMinimumSize(QSize(0, 42))
        self.ComfyUISubmit.setStyleSheet(u"\n"
"                   QPushButton {\n"
"                     background-color: #4a9eff;\n"
"                     color: white;\n"
"                     border: none;\n"
"                     border-radius: 6px;\n"
"                     font-size: 13px;\n"
"                     font-weight: bold;\n"
"                     padding: 8px 24px;\n"
"                   }\n"
"                   QPushButton:hover {\n"
"                     background-color: #5cadff;\n"
"                   }\n"
"                   QPushButton:pressed {\n"
"                     background-color: #3a8eef;\n"
"                   }\n"
"                   QPushButton:disabled {\n"
"                     background-color: #3c414b;\n"
"                     color: #797e89;\n"
"                   }\n"
"                 ")

        self.submitButtonsLayout.addWidget(self.ComfyUISubmit)

        self.ComfyUICancelJobs = QPushButton(self.comfyuiSubmitFrame)
        self.ComfyUICancelJobs.setObjectName(u"ComfyUICancelJobs")
        self.ComfyUICancelJobs.setMinimumSize(QSize(100, 42))
        self.ComfyUICancelJobs.setVisible(False)
        self.ComfyUICancelJobs.setStyleSheet(u"\n"
"                   QPushButton {\n"
"                     background-color: #ef4444;\n"
"                     color: white;\n"
"                     border: none;\n"
"                     border-radius: 6px;\n"
"                     font-size: 12px;\n"
"                     font-weight: bold;\n"
"                     padding: 8px 16px;\n"
"                   }\n"
"                   QPushButton:hover {\n"
"                     background-color: #f87171;\n"
"                   }\n"
"                   QPushButton:disabled {\n"
"                     background-color: #3c414b;\n"
"                     color: #797e89;\n"
"                   }\n"
"                 ")

        self.submitButtonsLayout.addWidget(self.ComfyUICancelJobs)


        self.comfyuiSubmitLayout.addLayout(self.submitButtonsLayout)


        self.settingsAndSubmitLayout.addWidget(self.comfyuiSubmitFrame)


        self.comfyuiLayout.addWidget(self.submitBar)

        self.comfyuiIterateFrame = QFrame(self.comfyuiScrollContent)
        self.comfyuiIterateFrame.setObjectName(u"comfyuiIterateFrame")
        self.comfyuiIterateFrame.setFrameShape(QFrame.StyledPanel)
        self.comfyuiIterateFrame.setVisible(False)
        self.comfyuiIterateFrame.setStyleSheet(u"\n"
"            QFrame {\n"
"              background-color: #282c34;\n"
"              border: 1px solid #3c414b;\n"
"              border-radius: 8px;\n"
"            }\n"
"          ")
        self.iterateLayout = QVBoxLayout(self.comfyuiIterateFrame)
        self.iterateLayout.setSpacing(8)
        self.iterateLayout.setObjectName(u"iterateLayout")
        self.iterateLayout.setContentsMargins(16, 12, 16, 14)
        self.ComfyUIIterateTitle = QLabel(self.comfyuiIterateFrame)
        self.ComfyUIIterateTitle.setObjectName(u"ComfyUIIterateTitle")
        self.ComfyUIIterateTitle.setStyleSheet(u"font-weight: bold; font-size: 13px; color: #e0e0e0; border: none;")

        self.iterateLayout.addWidget(self.ComfyUIIterateTitle)

        self.ComfyUIIterateStatus = QLabel(self.comfyuiIterateFrame)
        self.ComfyUIIterateStatus.setObjectName(u"ComfyUIIterateStatus")
        self.ComfyUIIterateStatus.setStyleSheet(u"color: #797e89; border: none;")

        self.iterateLayout.addWidget(self.ComfyUIIterateStatus)

        self.ComfyUIIterateProgress = QProgressBar(self.comfyuiIterateFrame)
        self.ComfyUIIterateProgress.setObjectName(u"ComfyUIIterateProgress")
        self.ComfyUIIterateProgress.setMaximum(100)
        self.ComfyUIIterateProgress.setValue(0)
        self.ComfyUIIterateProgress.setTextVisible(False)
        self.ComfyUIIterateProgress.setStyleSheet(u"\n"
"               QProgressBar {\n"
"                 background-color: #1a1d21;\n"
"                 border: none;\n"
"                 border-radius: 4px;\n"
"                 height: 8px;\n"
"               }\n"
"               QProgressBar::chunk {\n"
"                 background-color: #4a9eff;\n"
"                 border-radius: 4px;\n"
"               }\n"
"             ")

        self.iterateLayout.addWidget(self.ComfyUIIterateProgress)

        self.ComfyUIIteratePreview = QLabel(self.comfyuiIterateFrame)
        self.ComfyUIIteratePreview.setObjectName(u"ComfyUIIteratePreview")
        self.ComfyUIIteratePreview.setMinimumSize(QSize(200, 200))
        self.ComfyUIIteratePreview.setAlignment(Qt.AlignCenter)
        self.ComfyUIIteratePreview.setStyleSheet(u"background-color: #1a1d21; border: 1px solid #3c414b; border-radius: 6px;")

        self.iterateLayout.addWidget(self.ComfyUIIteratePreview)

        self.ComfyUIUseAsInput = QPushButton(self.comfyuiIterateFrame)
        self.ComfyUIUseAsInput.setObjectName(u"ComfyUIUseAsInput")
        self.ComfyUIUseAsInput.setEnabled(False)
        self.ComfyUIUseAsInput.setStyleSheet(u"\n"
"               QPushButton {\n"
"                 background-color: #2c313a;\n"
"                 border: 1px solid #4a9eff;\n"
"                 border-radius: 6px;\n"
"                 color: #4a9eff;\n"
"                 padding: 8px 16px;\n"
"                 font-size: 12px;\n"
"               }\n"
"               QPushButton:hover {\n"
"                 background-color: #333842;\n"
"               }\n"
"               QPushButton:disabled {\n"
"                 border-color: #3c414b;\n"
"                 color: #797e89;\n"
"               }\n"
"             ")

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
        self.modelStepTitle.setText(QCoreApplication.translate("ComfyUITab", u"Choose Model", None))
        self.ComfyUIChoosePreset.setText(QCoreApplication.translate("ComfyUITab", u"Choose Model...", None))
#if QT_CONFIG(tooltip)
        self.ComfyUIChoosePreset.setToolTip(QCoreApplication.translate("ComfyUITab", u"Click to browse and select a workflow model", None))
#endif // QT_CONFIG(tooltip)
        self.selectedModelName.setText(QCoreApplication.translate("ComfyUITab", u"Model", None))
        self.selectedModelBadge.setText(QCoreApplication.translate("ComfyUITab", u"IMAGE", None))
        self.workflowSettingsBtn.setText("")
#if QT_CONFIG(tooltip)
        self.workflowSettingsBtn.setToolTip(QCoreApplication.translate("ComfyUITab", u"Workflow settings", None))
#endif // QT_CONFIG(tooltip)
        self.editModelBtn.setText(QCoreApplication.translate("ComfyUITab", u"Edit", None))
#if QT_CONFIG(tooltip)
        self.editModelBtn.setToolTip(QCoreApplication.translate("ComfyUITab", u"Edit model preset (admin only)", None))
#endif // QT_CONFIG(tooltip)
        self.changeModelBtn.setText(QCoreApplication.translate("ComfyUITab", u"Change", None))
#if QT_CONFIG(tooltip)
        self.changeModelBtn.setToolTip(QCoreApplication.translate("ComfyUITab", u"Pick a different model", None))
#endif // QT_CONFIG(tooltip)
        self.selectedModelDesc.setText("")
        self.ComfyUIWorkflowPath.setText(QCoreApplication.translate("ComfyUITab", u"No model selected", None))
        self.inputStepTitle.setText(QCoreApplication.translate("ComfyUITab", u"Input", None))
        self.noteText.setText("")
        self.settingsStepTitle.setText(QCoreApplication.translate("ComfyUITab", u"Settings", None))
        self.advancedGearBtn.setText("")
#if QT_CONFIG(tooltip)
        self.advancedGearBtn.setToolTip(QCoreApplication.translate("ComfyUITab", u"Advanced settings (seed, name, server behavior, output path)", None))
#endif // QT_CONFIG(tooltip)
        self.label_count.setText(QCoreApplication.translate("ComfyUITab", u"How many:", None))
#if QT_CONFIG(tooltip)
        self.label_count.setToolTip(QCoreApplication.translate("ComfyUITab", u"Number of images to generate. Each gets a different seed for variety.", None))
#endif // QT_CONFIG(tooltip)
        self.label_count_value.setText(QCoreApplication.translate("ComfyUITab", u"1", None))
        self.advancedToggleBtn.setText(QCoreApplication.translate("ComfyUITab", u"Advanced Settings...", None))
        self.label_seed.setText(QCoreApplication.translate("ComfyUITab", u"Seed:", None))
#if QT_CONFIG(tooltip)
        self.label_seed.setToolTip(QCoreApplication.translate("ComfyUITab", u"Same seed + same settings = same result. Useful for recreating outputs.", None))
#endif // QT_CONFIG(tooltip)
        self.ComfyUIRandomizeSeed.setText("")
#if QT_CONFIG(tooltip)
        self.ComfyUIRandomizeSeed.setToolTip(QCoreApplication.translate("ComfyUITab", u"Generate a new random seed", None))
#endif // QT_CONFIG(tooltip)
        self.ComfyUINameToggle.setText(QCoreApplication.translate("ComfyUITab", u"Custom name:", None))
#if QT_CONFIG(tooltip)
        self.ComfyUINameToggle.setToolTip(QCoreApplication.translate("ComfyUITab", u"Add a custom label to output filenames for easier identification", None))
#endif // QT_CONFIG(tooltip)
        self.ComfyUIName.setPlaceholderText(QCoreApplication.translate("ComfyUITab", u"Prefixes output filenames", None))
        self.serverBehaviorLabel.setText(QCoreApplication.translate("ComfyUITab", u"If server offline:", None))
        self.serverWaitTimeoutLabel.setText(QCoreApplication.translate("ComfyUITab", u"Timeout:", None))
        self.ServerWaitTimeoutSpinBox.setSuffix(QCoreApplication.translate("ComfyUITab", u" min", None))
        self.label_network_output.setText(QCoreApplication.translate("ComfyUITab", u"Output path:", None))
        self.ComfyUINetworkPathDisplay.setText(QCoreApplication.translate("ComfyUITab", u"(Not configured)", None))
        self.submitStepTitle.setText(QCoreApplication.translate("ComfyUITab", u"Submit", None))
        self.ComfyUISubmit.setText(QCoreApplication.translate("ComfyUITab", u"Submit to Farm", None))
        self.ComfyUICancelJobs.setText(QCoreApplication.translate("ComfyUITab", u"Cancel Jobs", None))
        self.ComfyUIIterateTitle.setText(QCoreApplication.translate("ComfyUITab", u"Progress", None))
        self.ComfyUIIterateStatus.setText(QCoreApplication.translate("ComfyUITab", u"Ready", None))
        self.ComfyUIIteratePreview.setText("")
        self.ComfyUIUseAsInput.setText(QCoreApplication.translate("ComfyUITab", u"Use as Input for Next Run", None))
        pass
    # retranslateUi

