# Raster Analysis Application
# Author: Tymoteusz Maj
# GitHub: https://github.com/Xeraoo

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QAction, QFileDialog, QLabel, QVBoxLayout,
    QWidget, QComboBox, QPushButton, QHBoxLayout, QTabWidget, QTextEdit,
    QLineEdit, QMessageBox, QListWidget, QListWidgetItem, QPlainTextEdit,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QSlider
)
from PyQt5.QtGui import QPixmap, QColor, QPalette, QImage, QTransform, QPainter
from PyQt5.QtCore import Qt, QSettings, pyqtSignal, QThread
import rasterio
import numpy as np
from datetime import date, timedelta
from sentinelsat import SentinelAPI
import ee
import sys
from matplotlib.colors import LinearSegmentedColormap
from sentinelsat import SentinelAPI, read_geojson, geojson_to_wkt
from datetime import date

# Import additional libraries
import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import shape
import os

# Initialize Google Earth Engine
try:
    ee.Initialize()
except ee.EEException:
    pass

# Global variables for Copernicus credentials
copernicus_user = os.getenv("copernicus_user")  # Copernicus User
copernicus_password = os.getenv("copernicus_password")  # Copernicus Password

# Initialize Google Earth Engine
try:
    ee.Initialize()
except ee.EEException:
    pass

class GEEThread(QThread):
    finished = pyqtSignal()
    update_status = pyqtSignal(str)

    def __init__(self, script):
        super().__init__()
        self.script = script

    def run(self):
        try:
            self.update_status.emit("Running script in Google Earth Engine...")
            # Simulate long-running task
            import time
            time.sleep(2)
            self.update_status.emit("Script execution completed successfully.")
        except Exception as e:
            self.update_status.emit(f"Error executing script: {str(e)}")
        finally:
            self.finished.emit()

class CopernicusThread(QThread):
    finished = pyqtSignal()
    update_status = pyqtSignal(str)

    def __init__(self, ft):
        super().__init__()
        self.ft = ft

    def run(self):
        try:
            self.update_status.emit("Fetching Sentinel-2 L2A products...")
            today = date.today()
            today_string = today.strftime("%Y-%m-%d")
            yesterday = today - timedelta(days=1)
            yesterday_string = yesterday.strftime("%Y-%m-%d")

            # Function to get access token from Copernicus
            def get_keycloak(username: str, password: str) -> str:
                data = {
                    "client_id": "cdse-public",
                    "username": username,
                    "password": password,
                    "grant_type": "password",
                }
                try:
                    r = requests.post(
                        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
                        data=data,
                    )
                    r.raise_for_status()
                except Exception as e:
                    raise Exception(
                        f"Keycloak token creation failed. Response from the server was: {r.json()}"
                    )
                return r.json()["access_token"]

            # Fetch Sentinel-2 L2A products
            json_ = requests.get(
                f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products?"
                f"$filter=Collection/Name eq 'SENTINEL-2' and "
                f"OData.CSC.Intersects(area=geography'SRID=4326;{self.ft}') and "
                f"ContentDate/Start gt {yesterday_string}T00:00:00.000Z and "
                f"ContentDate/Start lt {today_string}T00:00:00.000Z&$count=True&$top=1000"
            ).json()

            # Process the JSON response
            p = pd.DataFrame.from_dict(json_["value"])
            if p.shape[0] > 0:
                p["geometry"] = p["GeoFootprint"].apply(shape)
                productDF = gpd.GeoDataFrame(p).set_geometry("geometry")
                productDF = productDF[~productDF["Name"].str.contains("L1C")]
                print(f"Total Sentinel-2 L2A tiles found: {len(productDF)}")

                # Download all available tiles
                for index, feat in enumerate(productDF.iterfeatures()):
                    try:
                        session = requests.Session()
                        keycloak_token = get_keycloak(copernicus_user, copernicus_password)
                        session.headers.update({"Authorization": f"Bearer {keycloak_token}"})
                        url = f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products({feat['properties']['Id']})/$value"
                        response = session.get(url, allow_redirects=False)
                        while response.status_code in (301, 302, 303, 307):
                            url = response.headers["Location"]
                            response = session.get(url, allow_redirects=False)
                        print(f"Downloading {feat['properties']['Name']}...")
                        file = session.get(url, verify=False, allow_redirects=True)

                        with open(f"{feat['properties']['identifier']}.zip", "wb") as p:
                            p.write(file.content)

                    except Exception as e:
                        print(f"Problem downloading {feat['properties']['Name']}: {e}")

                self.update_status.emit("Sentinel-2 L2A products downloaded successfully.")
            else:
                self.update_status.emit("No Sentinel-2 L2A products found for today.")

        except Exception as e:
            self.update_status.emit(f"Error: {str(e)}")

        finally:
            self.finished.emit()

class RasterAnalysisApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.settings = QSettings("Tymoteusz Maj", "RasterAnalysisApp")
        self.theme_selection = self.settings.value("theme_selection", "Dark")

        self.initUI()

    def runScript(self):
        script_text = self.scriptEditor.toPlainText()
        if not script_text.strip():
            QMessageBox.warning(self, "Error", "Please enter a script.")
            return

        self.thread = GEEThread(script_text)
        self.thread.finished.connect(lambda: self.runScriptButton.setEnabled(True))
        self.thread.update_status.connect(self.updateStatus)
        self.runScriptButton.setEnabled(False)
        self.thread.start()

    def updateStatus(self, status):
        self.scriptOutput.appendPlainText(status)

    def initUI(self):
        self.setWindowTitle('Raster Analysis Application')
        self.setGeometry(100, 100, 800, 600)

        menubar = self.menuBar()
        fileMenu = menubar.addMenu('File')

        openAction = QAction('Open', self)
        openAction.triggered.connect(self.openFiles)
        fileMenu.addAction(openAction)

        saveAction = QAction('Save', self)
        saveAction.triggered.connect(self.saveFile)
        fileMenu.addAction(saveAction)

        themeMenu = menubar.addMenu('Theme')

        darkThemeAction = QAction('Dark', self)
        darkThemeAction.triggered.connect(lambda: self.changeTheme('Dark'))
        themeMenu.addAction(darkThemeAction)

        lightThemeAction = QAction('Light', self)
        lightThemeAction.triggered.connect(lambda: self.changeTheme('Light'))
        themeMenu.addAction(lightThemeAction)

        self.centralWidget = QWidget()
        self.setCentralWidget(self.centralWidget)

        self.layout = QVBoxLayout()
        self.centralWidget.setLayout(self.layout)

        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)

        self.rasterTab = QWidget()
        self.rasterLayout = QVBoxLayout()
        self.rasterTab.setLayout(self.rasterLayout)
        self.tabs.addTab(self.rasterTab, "Raster Display")

        self.graphicsView = QGraphicsView()
        self.graphicsScene = QGraphicsScene()
        self.graphicsView.setScene(self.graphicsScene)
        self.graphicsView.setRenderHint(QPainter.Antialiasing)
        self.graphicsView.setRenderHint(QPainter.SmoothPixmapTransform)
        self.rasterLayout.addWidget(self.graphicsView)

        self.optionsLayout = QHBoxLayout()
        self.rasterLayout.addLayout(self.optionsLayout)

        self.comboLabel = QLabel("Color Composition:")
        self.optionsLayout.addWidget(self.comboLabel)

        self.colorComboBox = QComboBox()
        self.colorComboBox.addItems(["Custom", "RGB", "NIR", "Red Edge"])
        self.colorComboBox.currentIndexChanged.connect(self.updateRasterDisplay)
        self.optionsLayout.addWidget(self.colorComboBox)

        self.bandSelectors = {}
        for color in ['Red', 'Green', 'Blue', 'NIR']:
            label = QLabel(f"{color} Band:")
            self.optionsLayout.addWidget(label)
            comboBox = QComboBox()
            comboBox.addItems([str(i) for i in range(1, 13)])
            self.bandSelectors[color] = comboBox
            self.optionsLayout.addWidget(comboBox)

        self.ndviButton = QPushButton("Calculate NDVI")
        self.ndviButton.clicked.connect(self.calculateNDVI)
        self.optionsLayout.addWidget(self.ndviButton)

        self.zoomSlider = QSlider(Qt.Horizontal)
        self.zoomSlider.setMinimum(1)
        self.zoomSlider.setMaximum(100)
        self.zoomSlider.setValue(50)
        self.zoomSlider.valueChanged.connect(self.zoomImage)
        self.rasterLayout.addWidget(self.zoomSlider)

        self.geeTab = QWidget()
        self.geeLayout = QVBoxLayout()
        self.geeTab.setLayout(self.geeLayout)
        self.tabs.addTab(self.geeTab, "Google Earth Engine")

        self.geeInfoLabel = QLabel("Execute scripts using Google Earth Engine.")
        self.geeLayout.addWidget(self.geeInfoLabel)

        self.loginButton = QPushButton("Log In to Google Earth Engine")
        self.loginButton.clicked.connect(self.authorizeGoogleEarthEngine)
        self.geeLayout.addWidget(self.loginButton)

        self.scriptingTab = QWidget()
        self.scriptingLayout = QVBoxLayout()
        self.scriptingTab.setLayout(self.scriptingLayout)
        self.tabs.addTab(self.scriptingTab, "Scripting Google Earth Engine")

        self.scriptEditor = QTextEdit()
        self.scriptingLayout.addWidget(self.scriptEditor)

        self.runScriptButton = QPushButton("Run Script")
        self.runScriptButton.clicked.connect(self.runScript)
        self.scriptingLayout.addWidget(self.runScriptButton)

        self.scriptOutput = QPlainTextEdit()
        self.scriptOutput.setReadOnly(True)
        self.scriptingLayout.addWidget(self.scriptOutput)

        self.acquisitionTab = QWidget()
        self.acquisitionLayout = QVBoxLayout()
        self.acquisitionTab.setLayout(self.acquisitionLayout)
        self.tabs.addTab(self.acquisitionTab, "Acquisition")

        self.usernameLabel = QLabel("Copernicus Username:")
        self.acquisitionLayout.addWidget(self.usernameLabel)

        self.usernameInput = QLineEdit()
        self.acquisitionLayout.addWidget(self.usernameInput)

        self.passwordLabel = QLabel("Copernicus Password:")
        self.acquisitionLayout.addWidget(self.passwordLabel)

        self.passwordInput = QLineEdit()
        self.passwordInput.setEchoMode(QLineEdit.Password)
        self.acquisitionLayout.addWidget(self.passwordInput)

        self.downloadButton = QPushButton("Download Sentinel Image")
        self.downloadButton.clicked.connect(self.downloadSentinelImage)
        self.acquisitionLayout.addWidget(self.downloadButton)

        self.productsListWidget = QListWidget()
        self.productsListWidget.itemDoubleClicked.connect(self.downloadSelectedProduct)
        self.acquisitionLayout.addWidget(self.productsListWidget)

        self.applyTheme()

        self.rasterData = {}
        self.rasterProfiles = {}
        self.pixmapItem = None

        self.show()

    def applyTheme(self):
        if self.theme_selection == 'Dark':
            QApplication.setStyle("Fusion")
            dark_palette = QPalette()
            dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.WindowText, Qt.white)
            dark_palette.setColor(QPalette.Base, QColor(35, 35, 35))
            dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.ToolTipBase, QColor(25, 25, 25))
            dark_palette.setColor(QPalette.ToolTipText, Qt.white)
            dark_palette.setColor(QPalette.Text, Qt.white)
            dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.ButtonText, Qt.white)
            dark_palette.setColor(QPalette.BrightText, Qt.red)
            dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
            dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            dark_palette.setColor(QPalette.HighlightedText, QColor(35, 35, 35))
            dark_palette.setColor(QPalette.Active, QPalette.Button, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, Qt.darkGray)
            dark_palette.setColor(QPalette.Disabled, QPalette.WindowText, Qt.darkGray)
            dark_palette.setColor(QPalette.Disabled, QPalette.Text, Qt.darkGray)
            dark_palette.setColor(QPalette.Disabled, QPalette.Light, QColor(53, 53, 53))
            QApplication.setPalette(dark_palette)
        elif self.theme_selection == 'Light':
            QApplication.setStyle("Fusion")
            light_palette = QPalette()
            light_palette.setColor(QPalette.Window, Qt.white)
            light_palette.setColor(QPalette.WindowText, Qt.black)
            light_palette.setColor(QPalette.Base, Qt.white)
            light_palette.setColor(QPalette.AlternateBase, Qt.white)
            light_palette.setColor(QPalette.ToolTipBase, Qt.white)
            light_palette.setColor(QPalette.ToolTipText, Qt.black)
            light_palette.setColor(QPalette.Text, Qt.black)
            light_palette.setColor(QPalette.Button, Qt.white)
            light_palette.setColor(QPalette.ButtonText, Qt.black)
            light_palette.setColor(QPalette.BrightText, Qt.red)
            light_palette.setColor(QPalette.Link, QColor(0, 160, 230))
            light_palette.setColor(QPalette.Highlight, QColor(0, 160, 230))
            light_palette.setColor(QPalette.HighlightedText, Qt.white)
            light_palette.setColor(QPalette.Active, QPalette.Button, QColor(0, 160, 230))
            light_palette.setColor(QPalette.Disabled, QPalette.ButtonText, Qt.darkGray)
            light_palette.setColor(QPalette.Disabled, QPalette.WindowText, Qt.darkGray)
            light_palette.setColor(QPalette.Disabled, QPalette.Text, Qt.darkGray)
            light_palette.setColor(QPalette.Disabled, QPalette.Light, Qt.white)
            QApplication.setPalette(light_palette)

    def changeTheme(self, theme):
        self.theme_selection = theme
        self.applyTheme()
        self.settings.setValue("theme_selection", self.theme_selection)

    def openFiles(self):
        file_dialog = QFileDialog()
        file_paths, _ = file_dialog.getOpenFileNames(self, "Open Files", "", "GeoTIFF files (*.tif *.tiff)")
        if file_paths:
            self.loadFiles(file_paths)

    def loadFiles(self, file_paths):
        self.rasterData.clear()
        for i, file_path in enumerate(file_paths):
            self.loadRaster(file_path, i)
        self.updateRasterDisplay()

    def loadRaster(self, file_path, channel_index):
        try:
            with rasterio.open(file_path) as src:
                data = src.read(1)  # Wczytujemy tylko pierwszy kanał
                self.rasterData[channel_index] = data
                self.rasterProfiles[channel_index] = src.profile
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load raster file {file_path}: {e}")


    def saveFile(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getSaveFileName(self, "Save File", "", "GeoTIFF files (*.tif *.tiff)")
        if file_path:
            self.saveRaster(file_path)

    def saveRaster(self, file_path):
        if not self.rasterData:
            QMessageBox.warning(self, "Error", "No raster data to save.")
            return

        try:
            profile = next(iter(self.rasterProfiles.values()))
            data = next(iter(self.rasterData.values()))
            with rasterio.open(file_path, 'w', **profile) as dst:
                dst.write(data)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save raster file: {e}")

    def updateRasterDisplay(self):
        if not self.rasterData:
            return

        red = self.rasterData.get(0)
        green = self.rasterData.get(1)
        blue = self.rasterData.get(2)
        nir = self.rasterData.get(3)

        if red is None or green is None or blue is None or nir is None:
            QMessageBox.warning(self, "Error", "Please load all four channels.")
            return

        color_mode = self.colorComboBox.currentText()

        if color_mode == "Custom":
            red_band = int(self.bandSelectors['Red'].currentText()) - 1
            green_band = int(self.bandSelectors['Green'].currentText()) - 1
            blue_band = int(self.bandSelectors['Blue'].currentText()) - 1
        elif color_mode == "RGB":
            red_band, green_band, blue_band = 0, 1, 2
        elif color_mode == "NIR":
            red_band, green_band, blue_band = 3, 2, 1
        elif color_mode == "Red Edge":
            red_band, green_band, blue_band = 2, 3, 4

        rgb = np.stack([red, green, blue], axis=2)

        min_val = np.percentile(rgb, 2)
        max_val = np.percentile(rgb, 98)
        rgb = np.clip((rgb - min_val) / (max_val - min_val) * 255, 0, 255).astype(np.uint8)

        # Ustawienia palety kolorystycznej
        if color_mode == "RGB":
            colormap = LinearSegmentedColormap.from_list("RGB", ["#800000", "#ff0000", "#00ff00", "#0000ff", "#000080"])
        elif color_mode == "NIR":
            colormap = LinearSegmentedColormap.from_list("CIR", ["#ffffcc", "#ffeda0", "#fed976", "#feb24c", "#fd8d3c", "#fc4e2a", "#e31a1c"])
        elif color_mode == "Red Edge":
            colormap = LinearSegmentedColormap.from_list("Red Edge", ["#fee8c8", "#fdd49e", "#fdbb84", "#fc8d59", "#ef6548", "#d7301f", "#990000"])
        else:
            colormap = LinearSegmentedColormap.from_list("Custom", ["#800080", "#ff0000", "#ffff00", "#00ff00", "#0000ff", "#ff00ff", "#00ffff"])

        height, width, _ = rgb.shape
        bytes_per_line = 3 * width
        q_image = QImage(rgb.data, width, height, bytes_per_line, QImage.Format_RGB888)

        # Konwersja obrazu RGB do QPixmap
        pixmap = QPixmap.fromImage(q_image)

        # Rysowanie legendy palety kolorystycznej na wizualizacji zdjęcia
        painter = QPainter(pixmap)
        colormap_image = np.array([colormap(i / 255.0) for i in range(256)]) * 255
        colormap_image = colormap_image.astype(np.uint8)
        colormap_qimage = QImage(colormap_image.data, 256, 1, QImage.Format_RGB888)
        painter.drawImage(0, 0, colormap_qimage.scaled(pixmap.width(), 50))
        painter.end()

        if self.pixmapItem:
            self.graphicsScene.removeItem(self.pixmapItem)

        self.pixmapItem = QGraphicsPixmapItem(pixmap)
        self.graphicsScene.addItem(self.pixmapItem)

        self.graphicsView.fitInView(self.pixmapItem, Qt.KeepAspectRatio)

        # Zaktualizowanie wizualizacji dla NDVI
        if color_mode == "NDVI":
            ndvi = (nir - red) / (nir + red)
            ndvi = np.nan_to_num(ndvi)
            ndvi = ((ndvi + 1) * 127.5).astype(np.uint8)  # Mapowanie z (-1, 1) do (0, 255)

            q_image_ndvi = QImage(ndvi.data, width, height, width, QImage.Format_Grayscale8)
            pixmap_ndvi = QPixmap.fromImage(q_image_ndvi)

            if self.pixmapItem:
                self.graphicsScene.removeItem(self.pixmapItem)

            self.pixmapItem = QGraphicsPixmapItem(pixmap_ndvi)
            self.graphicsScene.addItem(self.pixmapItem)

            self.graphicsView.fitInView(self.pixmapItem, Qt.KeepAspectRatio)


    def calculateBasicStats(self):
        file_path, data = next(iter(self.rasterData.items()))
        stats = {}
        for i, band in enumerate(data, start=1):
            mean_val = np.mean(band)
            max_val = np.amax(band)
            stats[f'Band {i} Mean'] = mean_val
            stats[f'Band {i} Max'] = max_val
        QMessageBox.information(self, "Basic Stats", f"Basic statistics:\n{stats}")


    def displayRasterImage(self, red_band, green_band, blue_band):
        file_path, data = next(iter(self.rasterData.items()))
        profile = self.rasterProfiles[file_path]

        if profile['count'] < max(red_band, green_band, blue_band):
            QMessageBox.warning(self, "Error", "Selected bands are not available in the raster file.")
            return

        red = data[red_band - 1]
        green = data[green_band - 1]
        blue = data[blue_band - 1]
        alpha = np.ones_like(red) * 255  # Adding alpha channel

        rgb = np.stack([red, green, blue, alpha], axis=2)  # Adding alpha channel

        min_val = np.percentile(rgb, 2)
        max_val = np.percentile(rgb, 98)
        rgb = np.clip((rgb - min_val) / (max_val - min_val) * 255, 0, 255).astype(np.uint8)

        height, width, _ = rgb.shape
        bytes_per_line = 4 * width  # 4 channels (RGBA)
        q_image = QImage(rgb.data, width, height, bytes_per_line, QImage.Format_RGBA8888)  # Format with alpha channel
        pixmap = QPixmap.fromImage(q_image)

        if self.pixmapItem:
            self.graphicsScene.removeItem(self.pixmapItem)

        self.pixmapItem = QGraphicsPixmapItem(pixmap)
        self.graphicsScene.addItem(self.pixmapItem)

        self.graphicsView.fitInView(self.pixmapItem, Qt.KeepAspectRatio)


    def zoomImage(self):
        if not self.pixmapItem:
            return

        scale_factor = self.zoomSlider.value() / 50.0
        transform = QTransform().scale(scale_factor, scale_factor)
        self.pixmapItem.setTransform(transform)
        self.graphicsView.setSceneRect(self.pixmapItem.boundingRect())
        self.graphicsView.centerOn(self.pixmapItem)

    def calculateNDVI(self):
        if not self.rasterData:
            return

        red = self.rasterData.get(0)
        green = self.rasterData.get(1)
        blue = self.rasterData.get(2)
        nir = self.rasterData.get(3)

        if red is None or green is None or blue is None or nir is None:
            QMessageBox.warning(self, "Error", "Please load all four channels.")
            return

        ndvi = (nir - red) / (nir + red + 1e-8)  # Dodajemy 1e-8 aby uniknąć dzielenia przez zero

        min_val = np.nanpercentile(ndvi, 2)
        max_val = np.nanpercentile(ndvi, 98)
        ndvi = np.clip((ndvi - min_val) / (max_val - min_val) * 255, 0, 255).astype(np.uint8)

        height, width = ndvi.shape
        bytes_per_line = width
        q_image = QImage(ndvi.data, width, height, bytes_per_line, QImage.Format_Grayscale8)
        pixmap = QPixmap.fromImage(q_image)

        if self.pixmapItem:
            self.graphicsScene.removeItem(self.pixmapItem)

        self.pixmapItem = QGraphicsPixmapItem(pixmap)
        self.graphicsScene.addItem(self.pixmapItem)

        self.graphicsView.fitInView(self.pixmapItem, Qt.KeepAspectRatio)



    def authorizeGoogleEarthEngine(self):
        try:
            ee.Initialize()
            QMessageBox.information(self, "Success", "Successfully logged in to Google Earth Engine.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not log in to Google Earth Engine: {e}")

    def downloadSentinelImage(self):
        username = self.usernameInput.text()
        password = self.passwordInput.text()

        if not username or not password:
            QMessageBox.warning(self, "Error", "Please enter both username and password.")
            return
        # Define ft here based on your logic, e.g., from user input or a predefined area
        ft = 'POLYGON((10.2886962890625 45.93587125244685,10.8544921875 45.93587125244685,10.8544921875 46.33776088279935,10.2886962890625 46.33776088279935,10.2886962890625 45.93587125244685))'
        
        # Fetch Sentinel-2 L2A products using CopernicusThread
        self.thread = CopernicusThread(ft)
        self.thread.finished.connect(lambda: self.downloadButton.setEnabled(True))
        self.thread.update_status.connect(self.updateStatus)
        self.downloadButton.setEnabled(False)
        self.thread.start()

    def downloadSelectedProduct(self, item):
        username = self.usernameInput.text()
        password = self.passwordInput.text()
        product_id = item.data(Qt.UserRole)

        if not username or not password or not product_id:
            QMessageBox.warning(self, "Error", "Please ensure all fields are filled and a product is selected.")
            return

        api = SentinelAPI(username, password, 'https://scihub.copernicus.eu/dhus')
        # Przykład zapytania o dane

        products = api.query(
            area='POLYGON((10.2886962890625 45.93587125244685,10.8544921875 45.93587125244685,10.8544921875 46.33776088279935,10.2886962890625 46.33776088279935,10.2886962890625 45.93587125244685))',
            date=('2024-05-20', '2024-05-25'),
            platformname='Sentinel-2',
            cloudcoverpercentage=(0, 30)
        )   

        try:
            api.download(product_id, directory_path='.')
            QMessageBox.information(self, "Success", "Product downloaded successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not download product: {e}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = RasterAnalysisApp()
    sys.exit(app.exec_())