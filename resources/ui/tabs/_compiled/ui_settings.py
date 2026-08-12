# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'settings.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox,
    QDoubleSpinBox, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QSizePolicy,
    QSpacerItem, QSpinBox, QVBoxLayout, QWidget)

class Ui_SettingsTab(object):
    def setupUi(self, SettingsTab):
        if not SettingsTab.objectName():
            SettingsTab.setObjectName(u"SettingsTab")
        SettingsTab.resize(1400, 850)
        self.settingsMainLayout = QVBoxLayout(SettingsTab)
        self.settingsMainLayout.setSpacing(0)
        self.settingsMainLayout.setObjectName(u"settingsMainLayout")
        self.settingsMainLayout.setContentsMargins(0, 0, 0, 0)
        self.settingsScrollArea = QScrollArea(SettingsTab)
        self.settingsScrollArea.setObjectName(u"settingsScrollArea")
        self.settingsScrollArea.setWidgetResizable(True)
        self.settingsScrollArea.setFrameShape(QFrame.NoFrame)
        self.settingsScrollContent = QWidget()
        self.settingsScrollContent.setObjectName(u"settingsScrollContent")
        self.settingsScrollContent.setGeometry(QRect(0, 0, 1352, 852))
        self.settingsLayout = QVBoxLayout(self.settingsScrollContent)
        self.settingsLayout.setSpacing(24)
        self.settingsLayout.setObjectName(u"settingsLayout")
        self.settingsLayout.setContentsMargins(24, 24, 24, 24)
        self.infoGroupBox = QGroupBox(self.settingsScrollContent)
        self.infoGroupBox.setObjectName(u"infoGroupBox")
        self.infoLayout = QVBoxLayout(self.infoGroupBox)
        self.infoLayout.setObjectName(u"infoLayout")
        self.versionLayout = QHBoxLayout()
        self.versionLayout.setObjectName(u"versionLayout")
        self.versionLabel = QLabel(self.infoGroupBox)
        self.versionLabel.setObjectName(u"versionLabel")

        self.versionLayout.addWidget(self.versionLabel)

        self.versionValueLabel = QLabel(self.infoGroupBox)
        self.versionValueLabel.setObjectName(u"versionValueLabel")

        self.versionLayout.addWidget(self.versionValueLabel)

        self.showVersionHistoryButton = QPushButton(self.infoGroupBox)
        self.showVersionHistoryButton.setObjectName(u"showVersionHistoryButton")
        self.showVersionHistoryButton.setMinimumSize(QSize(120, 28))

        self.versionLayout.addWidget(self.showVersionHistoryButton)

        self.submitFeatureRequestButton = QPushButton(self.infoGroupBox)
        self.submitFeatureRequestButton.setObjectName(u"submitFeatureRequestButton")
        self.submitFeatureRequestButton.setMinimumSize(QSize(120, 28))

        self.versionLayout.addWidget(self.submitFeatureRequestButton)

        self.viewFeatureRequestsButton = QPushButton(self.infoGroupBox)
        self.viewFeatureRequestsButton.setObjectName(u"viewFeatureRequestsButton")
        self.viewFeatureRequestsButton.setMinimumSize(QSize(120, 28))
        self.viewFeatureRequestsButton.setVisible(False)

        self.versionLayout.addWidget(self.viewFeatureRequestsButton)

        self.versionSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.versionLayout.addItem(self.versionSpacer)


        self.infoLayout.addLayout(self.versionLayout)

        self.newVersionLabel = QLabel(self.infoGroupBox)
        self.newVersionLabel.setObjectName(u"newVersionLabel")
        self.newVersionLabel.setWordWrap(True)
        self.newVersionLabel.setVisible(False)

        self.infoLayout.addWidget(self.newVersionLabel)

        self.pathsGridLayout = QGridLayout()
        self.pathsGridLayout.setObjectName(u"pathsGridLayout")
        self.pathsGridLayout.setHorizontalSpacing(10)
        self.pathsGridLayout.setVerticalSpacing(8)
        self.label_comp = QLabel(self.infoGroupBox)
        self.label_comp.setObjectName(u"label_comp")

        self.pathsGridLayout.addWidget(self.label_comp, 0, 0, 1, 1)

        self.Complabel = QLabel(self.infoGroupBox)
        self.Complabel.setObjectName(u"Complabel")
        self.Complabel.setWordWrap(True)

        self.pathsGridLayout.addWidget(self.Complabel, 0, 1, 1, 1)

        self.label_render = QLabel(self.infoGroupBox)
        self.label_render.setObjectName(u"label_render")

        self.pathsGridLayout.addWidget(self.label_render, 1, 0, 1, 1)

        self.Renderlabel = QLabel(self.infoGroupBox)
        self.Renderlabel.setObjectName(u"Renderlabel")
        self.Renderlabel.setWordWrap(True)

        self.pathsGridLayout.addWidget(self.Renderlabel, 1, 1, 1, 1)

        self.label_usd = QLabel(self.infoGroupBox)
        self.label_usd.setObjectName(u"label_usd")

        self.pathsGridLayout.addWidget(self.label_usd, 2, 0, 1, 1)

        self.USDlabel = QLabel(self.infoGroupBox)
        self.USDlabel.setObjectName(u"USDlabel")
        self.USDlabel.setWordWrap(True)

        self.pathsGridLayout.addWidget(self.USDlabel, 2, 1, 1, 1)

        self.label_hip = QLabel(self.infoGroupBox)
        self.label_hip.setObjectName(u"label_hip")

        self.pathsGridLayout.addWidget(self.label_hip, 3, 0, 1, 1)

        self.HIPlabel = QLabel(self.infoGroupBox)
        self.HIPlabel.setObjectName(u"HIPlabel")
        self.HIPlabel.setWordWrap(True)

        self.pathsGridLayout.addWidget(self.HIPlabel, 3, 1, 1, 1)

        self.label_bundle = QLabel(self.infoGroupBox)
        self.label_bundle.setObjectName(u"label_bundle")

        self.pathsGridLayout.addWidget(self.label_bundle, 4, 0, 1, 1)

        self.BundleLabel = QLabel(self.infoGroupBox)
        self.BundleLabel.setObjectName(u"BundleLabel")
        self.BundleLabel.setWordWrap(True)

        self.pathsGridLayout.addWidget(self.BundleLabel, 4, 1, 1, 1)


        self.infoLayout.addLayout(self.pathsGridLayout)


        self.settingsLayout.addWidget(self.infoGroupBox)

        self.userSettingsGroupBox = QGroupBox(self.settingsScrollContent)
        self.userSettingsGroupBox.setObjectName(u"userSettingsGroupBox")
        self.userSettingsLayout = QVBoxLayout(self.userSettingsGroupBox)
        self.userSettingsLayout.setObjectName(u"userSettingsLayout")
        self.userSettingsLabel = QLabel(self.userSettingsGroupBox)
        self.userSettingsLabel.setObjectName(u"userSettingsLabel")
        self.userSettingsLabel.setWordWrap(True)

        self.userSettingsLayout.addWidget(self.userSettingsLabel)

        self.ShowTrayNotifications = QCheckBox(self.userSettingsGroupBox)
        self.ShowTrayNotifications.setObjectName(u"ShowTrayNotifications")
        self.ShowTrayNotifications.setChecked(True)

        self.userSettingsLayout.addWidget(self.ShowTrayNotifications)

        self.ShowStatusbarLog = QCheckBox(self.userSettingsGroupBox)
        self.ShowStatusbarLog.setObjectName(u"ShowStatusbarLog")
        self.ShowStatusbarLog.setChecked(False)

        self.userSettingsLayout.addWidget(self.ShowStatusbarLog)

        self.integrationSectionLabel = QLabel(self.userSettingsGroupBox)
        self.integrationSectionLabel.setObjectName(u"integrationSectionLabel")

        self.userSettingsLayout.addWidget(self.integrationSectionLabel)

        self.completionSoundLayout = QHBoxLayout()
        self.completionSoundLayout.setObjectName(u"completionSoundLayout")
        self.completionSoundLabel = QLabel(self.userSettingsGroupBox)
        self.completionSoundLabel.setObjectName(u"completionSoundLabel")

        self.completionSoundLayout.addWidget(self.completionSoundLabel)

        self.ComfyUICompletionSoundCombo = QComboBox(self.userSettingsGroupBox)
        self.ComfyUICompletionSoundCombo.addItem("")
        self.ComfyUICompletionSoundCombo.addItem("")
        self.ComfyUICompletionSoundCombo.addItem("")
        self.ComfyUICompletionSoundCombo.setObjectName(u"ComfyUICompletionSoundCombo")
        self.ComfyUICompletionSoundCombo.setMinimumWidth(120)

        self.completionSoundLayout.addWidget(self.ComfyUICompletionSoundCombo)

        self.completionSoundSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.completionSoundLayout.addItem(self.completionSoundSpacer)


        self.userSettingsLayout.addLayout(self.completionSoundLayout)

        self.ComfyUIConvertColorspace = QCheckBox(self.userSettingsGroupBox)
        self.ComfyUIConvertColorspace.setObjectName(u"ComfyUIConvertColorspace")
        self.ComfyUIConvertColorspace.setChecked(True)

        self.userSettingsLayout.addWidget(self.ComfyUIConvertColorspace)

        self.viewerSettingsSectionLabel = QLabel(self.userSettingsGroupBox)
        self.viewerSettingsSectionLabel.setObjectName(u"viewerSettingsSectionLabel")

        self.userSettingsLayout.addWidget(self.viewerSettingsSectionLabel)

        self.ViewerLiveAudioScrub = QCheckBox(self.userSettingsGroupBox)
        self.ViewerLiveAudioScrub.setObjectName(u"ViewerLiveAudioScrub")
        self.ViewerLiveAudioScrub.setChecked(False)

        self.userSettingsLayout.addWidget(self.ViewerLiveAudioScrub)

        self.viewer3DZoomLayout = QHBoxLayout()
        self.viewer3DZoomLayout.setObjectName(u"viewer3DZoomLayout")
        self.Viewer3DZoomLabel = QLabel(self.userSettingsGroupBox)
        self.Viewer3DZoomLabel.setObjectName(u"Viewer3DZoomLabel")

        self.viewer3DZoomLayout.addWidget(self.Viewer3DZoomLabel)

        self.Viewer3DZoomSpinBox = QDoubleSpinBox(self.userSettingsGroupBox)
        self.Viewer3DZoomSpinBox.setObjectName(u"Viewer3DZoomSpinBox")
        self.Viewer3DZoomSpinBox.setMinimum(1.000000000000000)
        self.Viewer3DZoomSpinBox.setMaximum(10.000000000000000)
        self.Viewer3DZoomSpinBox.setSingleStep(0.500000000000000)
        self.Viewer3DZoomSpinBox.setValue(3.500000000000000)

        self.viewer3DZoomLayout.addWidget(self.Viewer3DZoomSpinBox)

        self.viewer3DZoomSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.viewer3DZoomLayout.addItem(self.viewer3DZoomSpacer)


        self.userSettingsLayout.addLayout(self.viewer3DZoomLayout)

        self.thumbnailCacheLayout = QHBoxLayout()
        self.thumbnailCacheLayout.setObjectName(u"thumbnailCacheLayout")
        self.thumbnailCacheLabel = QLabel(self.userSettingsGroupBox)
        self.thumbnailCacheLabel.setObjectName(u"thumbnailCacheLabel")

        self.thumbnailCacheLayout.addWidget(self.thumbnailCacheLabel)

        self.RegenerateThumbnailsButton = QPushButton(self.userSettingsGroupBox)
        self.RegenerateThumbnailsButton.setObjectName(u"RegenerateThumbnailsButton")
        self.RegenerateThumbnailsButton.setMinimumSize(QSize(180, 28))

        self.thumbnailCacheLayout.addWidget(self.RegenerateThumbnailsButton)

        self.thumbnailCacheSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.thumbnailCacheLayout.addItem(self.thumbnailCacheSpacer)


        self.userSettingsLayout.addLayout(self.thumbnailCacheLayout)

        self.defaultPassesLabel = QLabel(self.userSettingsGroupBox)
        self.defaultPassesLabel.setObjectName(u"defaultPassesLabel")
        self.defaultPassesLabel.setWordWrap(True)

        self.userSettingsLayout.addWidget(self.defaultPassesLabel)

        self.passesManagementLayout = QHBoxLayout()
        self.passesManagementLayout.setObjectName(u"passesManagementLayout")
        self.DefaultPassesList = QListWidget(self.userSettingsGroupBox)
        self.DefaultPassesList.setObjectName(u"DefaultPassesList")
        self.DefaultPassesList.setSelectionMode(QAbstractItemView.MultiSelection)
        self.DefaultPassesList.setMinimumHeight(150)

        self.passesManagementLayout.addWidget(self.DefaultPassesList)

        self.passesButtonsLayout = QVBoxLayout()
        self.passesButtonsLayout.setObjectName(u"passesButtonsLayout")
        self.AddPassButton = QPushButton(self.userSettingsGroupBox)
        self.AddPassButton.setObjectName(u"AddPassButton")
        self.AddPassButton.setMinimumSize(QSize(120, 32))

        self.passesButtonsLayout.addWidget(self.AddPassButton)

        self.RemovePassButton = QPushButton(self.userSettingsGroupBox)
        self.RemovePassButton.setObjectName(u"RemovePassButton")
        self.RemovePassButton.setMinimumSize(QSize(120, 32))

        self.passesButtonsLayout.addWidget(self.RemovePassButton)

        self.ResetPassesButton = QPushButton(self.userSettingsGroupBox)
        self.ResetPassesButton.setObjectName(u"ResetPassesButton")
        self.ResetPassesButton.setMinimumSize(QSize(120, 32))

        self.passesButtonsLayout.addWidget(self.ResetPassesButton)

        self.passesButtonsSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.passesButtonsLayout.addItem(self.passesButtonsSpacer)


        self.passesManagementLayout.addLayout(self.passesButtonsLayout)


        self.userSettingsLayout.addLayout(self.passesManagementLayout)

        self.SaveSettingsButton = QPushButton(self.userSettingsGroupBox)
        self.SaveSettingsButton.setObjectName(u"SaveSettingsButton")
        self.SaveSettingsButton.setMinimumSize(QSize(0, 36))

        self.userSettingsLayout.addWidget(self.SaveSettingsButton)


        self.settingsLayout.addWidget(self.userSettingsGroupBox)

        self.globalSettingsGroupBox = QGroupBox(self.settingsScrollContent)
        self.globalSettingsGroupBox.setObjectName(u"globalSettingsGroupBox")
        self.globalSettingsLayout = QVBoxLayout(self.globalSettingsGroupBox)
        self.globalSettingsLayout.setObjectName(u"globalSettingsLayout")
        self.globalSettingsLabel = QLabel(self.globalSettingsGroupBox)
        self.globalSettingsLabel.setObjectName(u"globalSettingsLabel")
        self.globalSettingsLabel.setWordWrap(True)

        self.globalSettingsLayout.addWidget(self.globalSettingsLabel)

        self.globalSettingsPathLayout = QHBoxLayout()
        self.globalSettingsPathLayout.setObjectName(u"globalSettingsPathLayout")
        self.globalSettingsPathLabel = QLabel(self.globalSettingsGroupBox)
        self.globalSettingsPathLabel.setObjectName(u"globalSettingsPathLabel")

        self.globalSettingsPathLayout.addWidget(self.globalSettingsPathLabel)

        self.GlobalSettingsPathEdit = QLineEdit(self.globalSettingsGroupBox)
        self.GlobalSettingsPathEdit.setObjectName(u"GlobalSettingsPathEdit")

        self.globalSettingsPathLayout.addWidget(self.GlobalSettingsPathEdit)

        self.BrowseGlobalSettingsPath = QPushButton(self.globalSettingsGroupBox)
        self.BrowseGlobalSettingsPath.setObjectName(u"BrowseGlobalSettingsPath")

        self.globalSettingsPathLayout.addWidget(self.BrowseGlobalSettingsPath)


        self.globalSettingsLayout.addLayout(self.globalSettingsPathLayout)

        self.globalSettingsCurrentPath = QLabel(self.globalSettingsGroupBox)
        self.globalSettingsCurrentPath.setObjectName(u"globalSettingsCurrentPath")
        self.globalSettingsCurrentPath.setWordWrap(True)

        self.globalSettingsLayout.addWidget(self.globalSettingsCurrentPath)

        self.comfyuiModeLayout = QHBoxLayout()
        self.comfyuiModeLayout.setObjectName(u"comfyuiModeLayout")
        self.ComfyUIModeButton = QPushButton(self.globalSettingsGroupBox)
        self.ComfyUIModeButton.setObjectName(u"ComfyUIModeButton")

        self.comfyuiModeLayout.addWidget(self.ComfyUIModeButton)

        self.comfyuiModeSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.comfyuiModeLayout.addItem(self.comfyuiModeSpacer)


        self.globalSettingsLayout.addLayout(self.comfyuiModeLayout)

        self.comfyuiPathLayout = QHBoxLayout()
        self.comfyuiPathLayout.setObjectName(u"comfyuiPathLayout")
        self.comfyuiPathLabel = QLabel(self.globalSettingsGroupBox)
        self.comfyuiPathLabel.setObjectName(u"comfyuiPathLabel")

        self.comfyuiPathLayout.addWidget(self.comfyuiPathLabel)

        self.ComfyUIPathEdit = QLineEdit(self.globalSettingsGroupBox)
        self.ComfyUIPathEdit.setObjectName(u"ComfyUIPathEdit")

        self.comfyuiPathLayout.addWidget(self.ComfyUIPathEdit)

        self.BrowseComfyUIPath = QPushButton(self.globalSettingsGroupBox)
        self.BrowseComfyUIPath.setObjectName(u"BrowseComfyUIPath")

        self.comfyuiPathLayout.addWidget(self.BrowseComfyUIPath)


        self.globalSettingsLayout.addLayout(self.comfyuiPathLayout)

        self.comfyuiPythonLayout = QHBoxLayout()
        self.comfyuiPythonLayout.setObjectName(u"comfyuiPythonLayout")
        self.comfyuiPythonLabel = QLabel(self.globalSettingsGroupBox)
        self.comfyuiPythonLabel.setObjectName(u"comfyuiPythonLabel")

        self.comfyuiPythonLayout.addWidget(self.comfyuiPythonLabel)

        self.ComfyUIPythonEdit = QLineEdit(self.globalSettingsGroupBox)
        self.ComfyUIPythonEdit.setObjectName(u"ComfyUIPythonEdit")

        self.comfyuiPythonLayout.addWidget(self.ComfyUIPythonEdit)

        self.BrowseComfyUIPython = QPushButton(self.globalSettingsGroupBox)
        self.BrowseComfyUIPython.setObjectName(u"BrowseComfyUIPython")

        self.comfyuiPythonLayout.addWidget(self.BrowseComfyUIPython)


        self.globalSettingsLayout.addLayout(self.comfyuiPythonLayout)

        self.comfyuiCurrentPath = QLabel(self.globalSettingsGroupBox)
        self.comfyuiCurrentPath.setObjectName(u"comfyuiCurrentPath")
        self.comfyuiCurrentPath.setWordWrap(True)

        self.globalSettingsLayout.addWidget(self.comfyuiCurrentPath)

        self.networkOutputLayout = QHBoxLayout()
        self.networkOutputLayout.setObjectName(u"networkOutputLayout")
        self.networkOutputLabel = QLabel(self.globalSettingsGroupBox)
        self.networkOutputLabel.setObjectName(u"networkOutputLabel")

        self.networkOutputLayout.addWidget(self.networkOutputLabel)

        self.NetworkOutputEdit = QLineEdit(self.globalSettingsGroupBox)
        self.NetworkOutputEdit.setObjectName(u"NetworkOutputEdit")

        self.networkOutputLayout.addWidget(self.NetworkOutputEdit)

        self.BrowseNetworkOutput = QPushButton(self.globalSettingsGroupBox)
        self.BrowseNetworkOutput.setObjectName(u"BrowseNetworkOutput")

        self.networkOutputLayout.addWidget(self.BrowseNetworkOutput)


        self.globalSettingsLayout.addLayout(self.networkOutputLayout)

        self.vramModeLayout = QHBoxLayout()
        self.vramModeLayout.setObjectName(u"vramModeLayout")
        self.vramModeLabel = QLabel(self.globalSettingsGroupBox)
        self.vramModeLabel.setObjectName(u"vramModeLabel")

        self.vramModeLayout.addWidget(self.vramModeLabel)

        self.ComfyUIVRAMMode = QComboBox(self.globalSettingsGroupBox)
        self.ComfyUIVRAMMode.addItem("")
        self.ComfyUIVRAMMode.addItem("")
        self.ComfyUIVRAMMode.addItem("")
        self.ComfyUIVRAMMode.addItem("")
        self.ComfyUIVRAMMode.setObjectName(u"ComfyUIVRAMMode")
        self.ComfyUIVRAMMode.setMinimumWidth(200)

        self.vramModeLayout.addWidget(self.ComfyUIVRAMMode)

        self.vramModeSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.vramModeLayout.addItem(self.vramModeSpacer)


        self.globalSettingsLayout.addLayout(self.vramModeLayout)

        self.performanceFlagsLayout = QHBoxLayout()
        self.performanceFlagsLayout.setObjectName(u"performanceFlagsLayout")
        self.ComfyUIFastMode = QCheckBox(self.globalSettingsGroupBox)
        self.ComfyUIFastMode.setObjectName(u"ComfyUIFastMode")

        self.performanceFlagsLayout.addWidget(self.ComfyUIFastMode)

        self.ComfyUIDisableSmartMemory = QCheckBox(self.globalSettingsGroupBox)
        self.ComfyUIDisableSmartMemory.setObjectName(u"ComfyUIDisableSmartMemory")

        self.performanceFlagsLayout.addWidget(self.ComfyUIDisableSmartMemory)

        self.performanceFlagsSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.performanceFlagsLayout.addItem(self.performanceFlagsSpacer)


        self.globalSettingsLayout.addLayout(self.performanceFlagsLayout)

        self.comfyuiTimeoutLayout = QHBoxLayout()
        self.comfyuiTimeoutLayout.setObjectName(u"comfyuiTimeoutLayout")
        self.comfyuiTimeoutLabel = QLabel(self.globalSettingsGroupBox)
        self.comfyuiTimeoutLabel.setObjectName(u"comfyuiTimeoutLabel")

        self.comfyuiTimeoutLayout.addWidget(self.comfyuiTimeoutLabel)

        self.ComfyUITimeoutSpinBox = QSpinBox(self.globalSettingsGroupBox)
        self.ComfyUITimeoutSpinBox.setObjectName(u"ComfyUITimeoutSpinBox")
        self.ComfyUITimeoutSpinBox.setMinimum(1)
        self.ComfyUITimeoutSpinBox.setMaximum(1440)
        self.ComfyUITimeoutSpinBox.setValue(60)

        self.comfyuiTimeoutLayout.addWidget(self.ComfyUITimeoutSpinBox)

        self.timeoutSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.comfyuiTimeoutLayout.addItem(self.timeoutSpacer)


        self.globalSettingsLayout.addLayout(self.comfyuiTimeoutLayout)

        self.adminUsersHeader = QLabel(self.globalSettingsGroupBox)
        self.adminUsersHeader.setObjectName(u"adminUsersHeader")

        self.globalSettingsLayout.addWidget(self.adminUsersHeader)

        self.adminUsersContentLayout = QHBoxLayout()
        self.adminUsersContentLayout.setObjectName(u"adminUsersContentLayout")
        self.AdminUsersList = QListWidget(self.globalSettingsGroupBox)
        self.AdminUsersList.setObjectName(u"AdminUsersList")
        self.AdminUsersList.setSelectionMode(QAbstractItemView.SingleSelection)
        self.AdminUsersList.setMinimumHeight(80)
        self.AdminUsersList.setMaximumHeight(120)

        self.adminUsersContentLayout.addWidget(self.AdminUsersList)

        self.adminUsersButtonsLayout = QVBoxLayout()
        self.adminUsersButtonsLayout.setObjectName(u"adminUsersButtonsLayout")
        self.AddAdminUserButton = QPushButton(self.globalSettingsGroupBox)
        self.AddAdminUserButton.setObjectName(u"AddAdminUserButton")
        self.AddAdminUserButton.setMinimumSize(QSize(100, 28))

        self.adminUsersButtonsLayout.addWidget(self.AddAdminUserButton)

        self.RemoveAdminUserButton = QPushButton(self.globalSettingsGroupBox)
        self.RemoveAdminUserButton.setObjectName(u"RemoveAdminUserButton")
        self.RemoveAdminUserButton.setMinimumSize(QSize(100, 28))

        self.adminUsersButtonsLayout.addWidget(self.RemoveAdminUserButton)

        self.adminUsersButtonsSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.adminUsersButtonsLayout.addItem(self.adminUsersButtonsSpacer)


        self.adminUsersContentLayout.addLayout(self.adminUsersButtonsLayout)


        self.globalSettingsLayout.addLayout(self.adminUsersContentLayout)

        self.categoriesGroupBox = QGroupBox(self.globalSettingsGroupBox)
        self.categoriesGroupBox.setObjectName(u"categoriesGroupBox")
        self.categoriesLayout = QVBoxLayout(self.categoriesGroupBox)
        self.categoriesLayout.setObjectName(u"categoriesLayout")
        self.categoriesInfoLabel = QLabel(self.categoriesGroupBox)
        self.categoriesInfoLabel.setObjectName(u"categoriesInfoLabel")
        self.categoriesInfoLabel.setWordWrap(True)

        self.categoriesLayout.addWidget(self.categoriesInfoLabel)

        self.categoriesListLayout = QHBoxLayout()
        self.categoriesListLayout.setObjectName(u"categoriesListLayout")
        self.CategoriesList = QListWidget(self.categoriesGroupBox)
        self.CategoriesList.setObjectName(u"CategoriesList")
        self.CategoriesList.setMinimumSize(QSize(0, 120))
        self.CategoriesList.setMaximumSize(QSize(16777215, 150))
        self.CategoriesList.setSelectionMode(QAbstractItemView.SingleSelection)

        self.categoriesListLayout.addWidget(self.CategoriesList)

        self.categoriesButtonsLayout = QVBoxLayout()
        self.categoriesButtonsLayout.setObjectName(u"categoriesButtonsLayout")
        self.AddCategoryButton = QPushButton(self.categoriesGroupBox)
        self.AddCategoryButton.setObjectName(u"AddCategoryButton")
        self.AddCategoryButton.setMinimumSize(QSize(100, 28))

        self.categoriesButtonsLayout.addWidget(self.AddCategoryButton)

        self.RemoveCategoryButton = QPushButton(self.categoriesGroupBox)
        self.RemoveCategoryButton.setObjectName(u"RemoveCategoryButton")
        self.RemoveCategoryButton.setMinimumSize(QSize(100, 28))

        self.categoriesButtonsLayout.addWidget(self.RemoveCategoryButton)

        self.MoveCategoryUpButton = QPushButton(self.categoriesGroupBox)
        self.MoveCategoryUpButton.setObjectName(u"MoveCategoryUpButton")
        self.MoveCategoryUpButton.setMinimumSize(QSize(100, 28))

        self.categoriesButtonsLayout.addWidget(self.MoveCategoryUpButton)

        self.MoveCategoryDownButton = QPushButton(self.categoriesGroupBox)
        self.MoveCategoryDownButton.setObjectName(u"MoveCategoryDownButton")
        self.MoveCategoryDownButton.setMinimumSize(QSize(100, 28))

        self.categoriesButtonsLayout.addWidget(self.MoveCategoryDownButton)

        self.categoriesButtonsSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.categoriesButtonsLayout.addItem(self.categoriesButtonsSpacer)


        self.categoriesListLayout.addLayout(self.categoriesButtonsLayout)


        self.categoriesLayout.addLayout(self.categoriesListLayout)


        self.globalSettingsLayout.addWidget(self.categoriesGroupBox)

        self.hdriGroupBox = QGroupBox(self.globalSettingsGroupBox)
        self.hdriGroupBox.setObjectName(u"hdriGroupBox")
        self.hdriLayout = QVBoxLayout(self.hdriGroupBox)
        self.hdriLayout.setObjectName(u"hdriLayout")
        self.hdriInfoLabel = QLabel(self.hdriGroupBox)
        self.hdriInfoLabel.setObjectName(u"hdriInfoLabel")
        self.hdriInfoLabel.setWordWrap(True)

        self.hdriLayout.addWidget(self.hdriInfoLabel)

        self.hdriListLayout = QHBoxLayout()
        self.hdriListLayout.setObjectName(u"hdriListLayout")
        self.HdriListWidget = QListWidget(self.hdriGroupBox)
        self.HdriListWidget.setObjectName(u"HdriListWidget")
        self.HdriListWidget.setMinimumSize(QSize(0, 150))

        self.hdriListLayout.addWidget(self.HdriListWidget)

        self.hdriButtonsLayout = QVBoxLayout()
        self.hdriButtonsLayout.setObjectName(u"hdriButtonsLayout")
        self.AddHdriButton = QPushButton(self.hdriGroupBox)
        self.AddHdriButton.setObjectName(u"AddHdriButton")
        self.AddHdriButton.setMinimumSize(QSize(100, 28))

        self.hdriButtonsLayout.addWidget(self.AddHdriButton)

        self.RemoveHdriButton = QPushButton(self.hdriGroupBox)
        self.RemoveHdriButton.setObjectName(u"RemoveHdriButton")
        self.RemoveHdriButton.setMinimumSize(QSize(100, 28))

        self.hdriButtonsLayout.addWidget(self.RemoveHdriButton)

        self.hdriButtonsSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.hdriButtonsLayout.addItem(self.hdriButtonsSpacer)


        self.hdriListLayout.addLayout(self.hdriButtonsLayout)


        self.hdriLayout.addLayout(self.hdriListLayout)


        self.globalSettingsLayout.addWidget(self.hdriGroupBox)

        self.SaveGlobalSettings = QPushButton(self.globalSettingsGroupBox)
        self.SaveGlobalSettings.setObjectName(u"SaveGlobalSettings")
        self.SaveGlobalSettings.setMinimumSize(QSize(0, 36))

        self.globalSettingsLayout.addWidget(self.SaveGlobalSettings)


        self.settingsLayout.addWidget(self.globalSettingsGroupBox)

        self.settingsVerticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.settingsLayout.addItem(self.settingsVerticalSpacer)

        self.settingsScrollArea.setWidget(self.settingsScrollContent)

        self.settingsMainLayout.addWidget(self.settingsScrollArea)


        self.retranslateUi(SettingsTab)

        QMetaObject.connectSlotsByName(SettingsTab)
    # setupUi

    def retranslateUi(self, SettingsTab):
        self.infoGroupBox.setTitle(QCoreApplication.translate("SettingsTab", u"Info", None))
        self.versionLabel.setText(QCoreApplication.translate("SettingsTab", u"Version:", None))
        self.versionValueLabel.setProperty(u"textRole", QCoreApplication.translate("SettingsTab", u"value", None))
        self.versionValueLabel.setText(QCoreApplication.translate("SettingsTab", u"0.1", None))
        self.showVersionHistoryButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.showVersionHistoryButton.setText(QCoreApplication.translate("SettingsTab", u"Version History", None))
#if QT_CONFIG(tooltip)
        self.showVersionHistoryButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Show version changelog history", None))
#endif // QT_CONFIG(tooltip)
        self.submitFeatureRequestButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.submitFeatureRequestButton.setText(QCoreApplication.translate("SettingsTab", u"Submit Request", None))
#if QT_CONFIG(tooltip)
        self.submitFeatureRequestButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Submit a feature request or bug report", None))
#endif // QT_CONFIG(tooltip)
        self.viewFeatureRequestsButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.viewFeatureRequestsButton.setText(QCoreApplication.translate("SettingsTab", u"View Requests", None))
#if QT_CONFIG(tooltip)
        self.viewFeatureRequestsButton.setToolTip(QCoreApplication.translate("SettingsTab", u"View all feature requests (admin only)", None))
#endif // QT_CONFIG(tooltip)
        self.newVersionLabel.setProperty(u"state", QCoreApplication.translate("SettingsTab", u"warning", None))
        self.newVersionLabel.setProperty(u"variant", QCoreApplication.translate("SettingsTab", u"note", None))
        self.newVersionLabel.setText("")
        self.label_comp.setText(QCoreApplication.translate("SettingsTab", u"Comp Directory:", None))
        self.Complabel.setText(QCoreApplication.translate("SettingsTab", u"Not Found", None))
        self.label_render.setText(QCoreApplication.translate("SettingsTab", u"Render Directory:", None))
        self.Renderlabel.setText(QCoreApplication.translate("SettingsTab", u"Not Found", None))
        self.label_usd.setText(QCoreApplication.translate("SettingsTab", u"USD Directory:", None))
        self.USDlabel.setText(QCoreApplication.translate("SettingsTab", u"Not Found", None))
        self.label_hip.setText(QCoreApplication.translate("SettingsTab", u"HIP File:", None))
        self.HIPlabel.setText(QCoreApplication.translate("SettingsTab", u"Not Found", None))
        self.label_bundle.setText(QCoreApplication.translate("SettingsTab", u"AYON Bundle:", None))
        self.BundleLabel.setText(QCoreApplication.translate("SettingsTab", u"N/A", None))
        self.userSettingsGroupBox.setTitle(QCoreApplication.translate("SettingsTab", u"User Settings (Local)", None))
#if QT_CONFIG(tooltip)
        self.userSettingsGroupBox.setToolTip(QCoreApplication.translate("SettingsTab", u"Personal settings stored locally - these only affect your machine", None))
#endif // QT_CONFIG(tooltip)
        self.userSettingsLabel.setProperty(u"textRole", QCoreApplication.translate("SettingsTab", u"help", None))
        self.userSettingsLabel.setText(QCoreApplication.translate("SettingsTab", u"These settings are stored locally and only affect your machine.", None))
#if QT_CONFIG(tooltip)
        self.ShowTrayNotifications.setToolTip(QCoreApplication.translate("SettingsTab", u"Show Windows system tray notifications when ComfyUI jobs complete", None))
#endif // QT_CONFIG(tooltip)
        self.ShowTrayNotifications.setText(QCoreApplication.translate("SettingsTab", u"Show tray notifications for ComfyUI completions", None))
#if QT_CONFIG(tooltip)
        self.ShowStatusbarLog.setToolTip(QCoreApplication.translate("SettingsTab", u"Show the last log message in the status bar (bottom right). Useful for monitoring activity.", None))
#endif // QT_CONFIG(tooltip)
        self.ShowStatusbarLog.setText(QCoreApplication.translate("SettingsTab", u"Show log messages in status bar", None))
        self.integrationSectionLabel.setProperty(u"textRole", QCoreApplication.translate("SettingsTab", u"micro", None))
        self.integrationSectionLabel.setText(QCoreApplication.translate("SettingsTab", u"ComfyUI + Gallery Integration:", None))
        self.completionSoundLabel.setText(QCoreApplication.translate("SettingsTab", u"Job completion sound:", None))
        self.ComfyUICompletionSoundCombo.setItemText(0, QCoreApplication.translate("SettingsTab", u"None", None))
        self.ComfyUICompletionSoundCombo.setItemText(1, QCoreApplication.translate("SettingsTab", u"Subtle", None))
        self.ComfyUICompletionSoundCombo.setItemText(2, QCoreApplication.translate("SettingsTab", u"System", None))

#if QT_CONFIG(tooltip)
        self.ComfyUICompletionSoundCombo.setToolTip(QCoreApplication.translate("SettingsTab", u"Play a sound when ComfyUI jobs complete", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.ComfyUIConvertColorspace.setToolTip(QCoreApplication.translate("SettingsTab", u"When converting EXR/HDR/DPX/TGA images to PNG for ComfyUI, apply ACES to sRGB color conversion. Disable for simple format conversion without colorspace changes.", None))
#endif // QT_CONFIG(tooltip)
        self.ComfyUIConvertColorspace.setText(QCoreApplication.translate("SettingsTab", u"Apply ACES \u2192 sRGB when converting images for ComfyUI", None))
        self.viewerSettingsSectionLabel.setProperty(u"textRole", QCoreApplication.translate("SettingsTab", u"micro", None))
        self.viewerSettingsSectionLabel.setText(QCoreApplication.translate("SettingsTab", u"Viewer Settings:", None))
#if QT_CONFIG(tooltip)
        self.ViewerLiveAudioScrub.setToolTip(QCoreApplication.translate("SettingsTab", u"When scrubbing the timeline slider or waveform, keep audio playing so you can hear the current position. Default is off (silent scrubbing).", None))
#endif // QT_CONFIG(tooltip)
        self.ViewerLiveAudioScrub.setText(QCoreApplication.translate("SettingsTab", u"Play audio during scrubbing", None))
        self.Viewer3DZoomLabel.setText(QCoreApplication.translate("SettingsTab", u"3D Viewer Default Zoom:", None))
#if QT_CONFIG(tooltip)
        self.Viewer3DZoomSpinBox.setToolTip(QCoreApplication.translate("SettingsTab", u"Default camera distance when viewing 3D models. Lower values = closer zoom.", None))
#endif // QT_CONFIG(tooltip)
        self.thumbnailCacheLabel.setText(QCoreApplication.translate("SettingsTab", u"Gallery Thumbnails:", None))
        self.RegenerateThumbnailsButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.RegenerateThumbnailsButton.setText(QCoreApplication.translate("SettingsTab", u"Regenerate Thumbnails", None))
#if QT_CONFIG(tooltip)
        self.RegenerateThumbnailsButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Clear cached thumbnails and regenerate them. Use this if 3D model thumbnails look incorrect.", None))
#endif // QT_CONFIG(tooltip)
        self.defaultPassesLabel.setText(QCoreApplication.translate("SettingsTab", u"Default Passes (Beauty and Alpha are always included):", None))
#if QT_CONFIG(tooltip)
        self.DefaultPassesList.setToolTip(QCoreApplication.translate("SettingsTab", u"Select/deselect passes to include by default when building", None))
#endif // QT_CONFIG(tooltip)
        self.AddPassButton.setProperty(u"density", QCoreApplication.translate("SettingsTab", u"sm", None))
        self.AddPassButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.AddPassButton.setText(QCoreApplication.translate("SettingsTab", u"Add Pass", None))
#if QT_CONFIG(tooltip)
        self.AddPassButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Add a custom pass name to the default list", None))
#endif // QT_CONFIG(tooltip)
        self.RemovePassButton.setProperty(u"density", QCoreApplication.translate("SettingsTab", u"sm", None))
        self.RemovePassButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.RemovePassButton.setText(QCoreApplication.translate("SettingsTab", u"Remove Pass", None))
#if QT_CONFIG(tooltip)
        self.RemovePassButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Remove selected pass from the default list", None))
#endif // QT_CONFIG(tooltip)
        self.ResetPassesButton.setProperty(u"density", QCoreApplication.translate("SettingsTab", u"sm", None))
        self.ResetPassesButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.ResetPassesButton.setText(QCoreApplication.translate("SettingsTab", u"Reset to Default", None))
#if QT_CONFIG(tooltip)
        self.ResetPassesButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Reset to default pass list (CryptoMaterials, P, depth, uv, normal)", None))
#endif // QT_CONFIG(tooltip)
        self.SaveSettingsButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"primary", None))
        self.SaveSettingsButton.setText(QCoreApplication.translate("SettingsTab", u"Save User Settings", None))
#if QT_CONFIG(tooltip)
        self.SaveSettingsButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Save your local user settings", None))
#endif // QT_CONFIG(tooltip)
        self.globalSettingsGroupBox.setTitle(QCoreApplication.translate("SettingsTab", u"Global Settings (Careful)", None))
#if QT_CONFIG(tooltip)
        self.globalSettingsGroupBox.setToolTip(QCoreApplication.translate("SettingsTab", u"Configure shared settings that apply to all users - requires admin access to modify", None))
#endif // QT_CONFIG(tooltip)
        self.globalSettingsLabel.setText(QCoreApplication.translate("SettingsTab", u"Global settings are shared across all users. Changes affect everyone on the team.", None))
        self.globalSettingsPathLabel.setText(QCoreApplication.translate("SettingsTab", u"Global Settings Path:", None))
        self.GlobalSettingsPathEdit.setPlaceholderText(QCoreApplication.translate("SettingsTab", u"Path to global settings directory...", None))
#if QT_CONFIG(tooltip)
        self.GlobalSettingsPathEdit.setToolTip(QCoreApplication.translate("SettingsTab", u"Path to the directory where global settings are stored (e.g., workflow presets)", None))
#endif // QT_CONFIG(tooltip)
        self.BrowseGlobalSettingsPath.setProperty(u"density", QCoreApplication.translate("SettingsTab", u"sm", None))
        self.BrowseGlobalSettingsPath.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.BrowseGlobalSettingsPath.setText(QCoreApplication.translate("SettingsTab", u"Browse...", None))
#if QT_CONFIG(tooltip)
        self.BrowseGlobalSettingsPath.setToolTip(QCoreApplication.translate("SettingsTab", u"Browse for global settings directory", None))
#endif // QT_CONFIG(tooltip)
        self.globalSettingsCurrentPath.setProperty(u"textRole", QCoreApplication.translate("SettingsTab", u"mono", None))
        self.globalSettingsCurrentPath.setText(QCoreApplication.translate("SettingsTab", u"Current: (default path)", None))
        self.ComfyUIModeButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.ComfyUIModeButton.setText(QCoreApplication.translate("SettingsTab", u"ComfyUI Mode: Embedded", None))
#if QT_CONFIG(tooltip)
        self.ComfyUIModeButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Click to select ComfyUI installation type", None))
#endif // QT_CONFIG(tooltip)
        self.comfyuiPathLabel.setText(QCoreApplication.translate("SettingsTab", u"ComfyUI Path:", None))
        self.ComfyUIPathEdit.setPlaceholderText(QCoreApplication.translate("SettingsTab", u"Path to ComfyUI installation...", None))
#if QT_CONFIG(tooltip)
        self.ComfyUIPathEdit.setToolTip(QCoreApplication.translate("SettingsTab", u"Path to ComfyUI installation directory (contains main.py)", None))
#endif // QT_CONFIG(tooltip)
        self.BrowseComfyUIPath.setProperty(u"density", QCoreApplication.translate("SettingsTab", u"sm", None))
        self.BrowseComfyUIPath.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.BrowseComfyUIPath.setText(QCoreApplication.translate("SettingsTab", u"Browse...", None))
#if QT_CONFIG(tooltip)
        self.BrowseComfyUIPath.setToolTip(QCoreApplication.translate("SettingsTab", u"Browse for ComfyUI installation directory", None))
#endif // QT_CONFIG(tooltip)
        self.comfyuiPythonLabel.setText(QCoreApplication.translate("SettingsTab", u"Python Path:", None))
        self.ComfyUIPythonEdit.setPlaceholderText(QCoreApplication.translate("SettingsTab", u"Path to Python executable (for standalone mode)...", None))
#if QT_CONFIG(tooltip)
        self.ComfyUIPythonEdit.setToolTip(QCoreApplication.translate("SettingsTab", u"Path to Python executable (venv or system) for standalone mode", None))
#endif // QT_CONFIG(tooltip)
        self.BrowseComfyUIPython.setProperty(u"density", QCoreApplication.translate("SettingsTab", u"sm", None))
        self.BrowseComfyUIPython.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.BrowseComfyUIPython.setText(QCoreApplication.translate("SettingsTab", u"Browse...", None))
#if QT_CONFIG(tooltip)
        self.BrowseComfyUIPython.setToolTip(QCoreApplication.translate("SettingsTab", u"Browse for Python executable", None))
#endif // QT_CONFIG(tooltip)
        self.comfyuiCurrentPath.setProperty(u"textRole", QCoreApplication.translate("SettingsTab", u"mono", None))
        self.comfyuiCurrentPath.setText(QCoreApplication.translate("SettingsTab", u"Current: (default path)", None))
        self.networkOutputLabel.setText(QCoreApplication.translate("SettingsTab", u"Network Output Path:", None))
        self.NetworkOutputEdit.setPlaceholderText(QCoreApplication.translate("SettingsTab", u"Network path for outputs...", None))
#if QT_CONFIG(tooltip)
        self.NetworkOutputEdit.setToolTip(QCoreApplication.translate("SettingsTab", u"Shared network path for outputs (accessible by farm and all tools)", None))
#endif // QT_CONFIG(tooltip)
        self.BrowseNetworkOutput.setProperty(u"density", QCoreApplication.translate("SettingsTab", u"sm", None))
        self.BrowseNetworkOutput.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.BrowseNetworkOutput.setText(QCoreApplication.translate("SettingsTab", u"Browse...", None))
#if QT_CONFIG(tooltip)
        self.BrowseNetworkOutput.setToolTip(QCoreApplication.translate("SettingsTab", u"Browse for network output directory", None))
#endif // QT_CONFIG(tooltip)
        self.vramModeLabel.setText(QCoreApplication.translate("SettingsTab", u"VRAM Mode:", None))
#if QT_CONFIG(tooltip)
        self.vramModeLabel.setToolTip(QCoreApplication.translate("SettingsTab", u"ComfyUI GPU memory strategy. --lowvram, --normalvram and --highvram are mutually exclusive launch flags.", None))
#endif // QT_CONFIG(tooltip)
        self.ComfyUIVRAMMode.setItemText(0, QCoreApplication.translate("SettingsTab", u"Auto (ComfyUI decides)", None))
        self.ComfyUIVRAMMode.setItemText(1, QCoreApplication.translate("SettingsTab", u"Low VRAM (--lowvram)", None))
        self.ComfyUIVRAMMode.setItemText(2, QCoreApplication.translate("SettingsTab", u"Normal VRAM (--normalvram)", None))
        self.ComfyUIVRAMMode.setItemText(3, QCoreApplication.translate("SettingsTab", u"High VRAM (--highvram)", None))

#if QT_CONFIG(tooltip)
        self.ComfyUIVRAMMode.setToolTip(QCoreApplication.translate("SettingsTab", u"Auto: let ComfyUI decide. Low (--lowvram): least VRAM, slowest. Normal (--normalvram): default memory management. High (--highvram): keep models in VRAM, needs high-end GPUs (24GB+).", None))
#endif // QT_CONFIG(tooltip)
        self.ComfyUIFastMode.setText(QCoreApplication.translate("SettingsTab", u"Fast Mode (--fast fp16_accumulation)", None))
#if QT_CONFIG(tooltip)
        self.ComfyUIFastMode.setToolTip(QCoreApplication.translate("SettingsTab", u"Enable --fast with fp16 accumulation for faster execution. May slightly reduce quality for some models.", None))
#endif // QT_CONFIG(tooltip)
        self.ComfyUIDisableSmartMemory.setText(QCoreApplication.translate("SettingsTab", u"Disable Smart Memory (--disable-smart-memory)", None))
#if QT_CONFIG(tooltip)
        self.ComfyUIDisableSmartMemory.setToolTip(QCoreApplication.translate("SettingsTab", u"Disable automatic model unloading. Maximum memory usage, but models never unload. Best for dedicated servers.", None))
#endif // QT_CONFIG(tooltip)
        self.comfyuiTimeoutLabel.setText(QCoreApplication.translate("SettingsTab", u"Job Timeout (minutes):", None))
#if QT_CONFIG(tooltip)
        self.ComfyUITimeoutSpinBox.setToolTip(QCoreApplication.translate("SettingsTab", u"Maximum time in minutes for ComfyUI workflow execution before timeout", None))
#endif // QT_CONFIG(tooltip)
        self.ComfyUITimeoutSpinBox.setSuffix(QCoreApplication.translate("SettingsTab", u" min", None))
        self.adminUsersHeader.setText(QCoreApplication.translate("SettingsTab", u"Admin Users (Full access):", None))
#if QT_CONFIG(tooltip)
        self.adminUsersHeader.setToolTip(QCoreApplication.translate("SettingsTab", u"Admins have full access to all tabs including Settings", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.AdminUsersList.setToolTip(QCoreApplication.translate("SettingsTab", u"Users with full access to all tabs including Settings", None))
#endif // QT_CONFIG(tooltip)
        self.AddAdminUserButton.setProperty(u"density", QCoreApplication.translate("SettingsTab", u"sm", None))
        self.AddAdminUserButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.AddAdminUserButton.setText(QCoreApplication.translate("SettingsTab", u"Add User", None))
#if QT_CONFIG(tooltip)
        self.AddAdminUserButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Add a username to the admin list. Admins get full access to all tabs including Settings. Applies immediately for everyone.", None))
#endif // QT_CONFIG(tooltip)
        self.RemoveAdminUserButton.setProperty(u"density", QCoreApplication.translate("SettingsTab", u"sm", None))
        self.RemoveAdminUserButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.RemoveAdminUserButton.setText(QCoreApplication.translate("SettingsTab", u"Remove User", None))
#if QT_CONFIG(tooltip)
        self.RemoveAdminUserButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Remove the selected user from the admin list. They lose admin access after restarting Luma Tools. Applies immediately.", None))
#endif // QT_CONFIG(tooltip)
        self.categoriesGroupBox.setTitle(QCoreApplication.translate("SettingsTab", u"ComfyUI Preset Categories", None))
        self.categoriesInfoLabel.setText(QCoreApplication.translate("SettingsTab", u"Manage categories used to filter presets in the model picker.", None))
#if QT_CONFIG(tooltip)
        self.CategoriesList.setToolTip(QCoreApplication.translate("SettingsTab", u"List of preset categories for filtering", None))
#endif // QT_CONFIG(tooltip)
        self.AddCategoryButton.setProperty(u"density", QCoreApplication.translate("SettingsTab", u"sm", None))
        self.AddCategoryButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.AddCategoryButton.setText(QCoreApplication.translate("SettingsTab", u"Add", None))
#if QT_CONFIG(tooltip)
        self.AddCategoryButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Add a new category", None))
#endif // QT_CONFIG(tooltip)
        self.RemoveCategoryButton.setProperty(u"density", QCoreApplication.translate("SettingsTab", u"sm", None))
        self.RemoveCategoryButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.RemoveCategoryButton.setText(QCoreApplication.translate("SettingsTab", u"Remove", None))
#if QT_CONFIG(tooltip)
        self.RemoveCategoryButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Remove selected category", None))
#endif // QT_CONFIG(tooltip)
        self.MoveCategoryUpButton.setProperty(u"density", QCoreApplication.translate("SettingsTab", u"sm", None))
        self.MoveCategoryUpButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.MoveCategoryUpButton.setText(QCoreApplication.translate("SettingsTab", u"Move Up", None))
#if QT_CONFIG(tooltip)
        self.MoveCategoryUpButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Move selected category up in the list", None))
#endif // QT_CONFIG(tooltip)
        self.MoveCategoryDownButton.setProperty(u"density", QCoreApplication.translate("SettingsTab", u"sm", None))
        self.MoveCategoryDownButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.MoveCategoryDownButton.setText(QCoreApplication.translate("SettingsTab", u"Move Down", None))
#if QT_CONFIG(tooltip)
        self.MoveCategoryDownButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Move selected category down in the list", None))
#endif // QT_CONFIG(tooltip)
        self.hdriGroupBox.setTitle(QCoreApplication.translate("SettingsTab", u"HDRI Environment Maps", None))
        self.hdriInfoLabel.setText(QCoreApplication.translate("SettingsTab", u"Manage HDRI files for 3D viewer lighting. Supported formats: .hdr, .exr", None))
#if QT_CONFIG(tooltip)
        self.HdriListWidget.setToolTip(QCoreApplication.translate("SettingsTab", u"List of configured HDRI environment maps", None))
#endif // QT_CONFIG(tooltip)
        self.AddHdriButton.setProperty(u"density", QCoreApplication.translate("SettingsTab", u"sm", None))
        self.AddHdriButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.AddHdriButton.setText(QCoreApplication.translate("SettingsTab", u"Add HDRI...", None))
#if QT_CONFIG(tooltip)
        self.AddHdriButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Add a new HDRI file to the list", None))
#endif // QT_CONFIG(tooltip)
        self.RemoveHdriButton.setProperty(u"density", QCoreApplication.translate("SettingsTab", u"sm", None))
        self.RemoveHdriButton.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"secondary", None))
        self.RemoveHdriButton.setText(QCoreApplication.translate("SettingsTab", u"Remove", None))
#if QT_CONFIG(tooltip)
        self.RemoveHdriButton.setToolTip(QCoreApplication.translate("SettingsTab", u"Remove selected HDRI from the list", None))
#endif // QT_CONFIG(tooltip)
        self.SaveGlobalSettings.setProperty(u"role", QCoreApplication.translate("SettingsTab", u"primary", None))
        self.SaveGlobalSettings.setText(QCoreApplication.translate("SettingsTab", u"Save Global Settings", None))
#if QT_CONFIG(tooltip)
        self.SaveGlobalSettings.setToolTip(QCoreApplication.translate("SettingsTab", u"Save all global settings", None))
#endif // QT_CONFIG(tooltip)
        pass
    # retranslateUi

